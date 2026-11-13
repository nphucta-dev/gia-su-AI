"""Adapter HTTP cho API tương thích Chat Completions; key chỉ dùng ở server.

Không chọn sẵn nhà cung cấp hoặc gọi mạng khi khởi tạo. URL là endpoint đầy đủ
do quản trị viên cấu hình; adapter khác có thể triển khai cùng LLMClient.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import unicodedata
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Protocol

import httpx

from app.config import Settings
from app.utils.errors import AppError

MAX_RESPONSE_BYTES = 256 * 1024
MAX_REPLY_CHARS = 8000
_llm_request_active: ContextVar[bool] = ContextVar("llm_request_active", default=False)


class _PrivateHttpLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return not (_llm_request_active.get() and (record.name == "httpx" or record.name.startswith("httpcore")))


_private_http_logs = _PrivateHttpLogs()


def _protect_http_logs() -> None:
    # Giữ log của các request khác; chỉ chặn thông tin transport trong context gọi LLM.
    handlers = set(logging.getLogger().handlers)
    for value in list(logging.Logger.manager.loggerDict.values()):
        if isinstance(value, logging.Logger):
            handlers.update(value.handlers)
    if logging.lastResort is not None:
        handlers.add(logging.lastResort)
    for handler in handlers:
        if _private_http_logs not in handler.filters:
            handler.addFilter(_private_http_logs)


@dataclass(frozen=True)
class LLMReply:
    content: str = field(repr=False)
    token_count: int | None = None


class LLMClient(Protocol):
    async def generate(self, messages: list[dict[str, str]]) -> LLMReply: ...


def _not_configured() -> AppError:
    return AppError(503, "LLM_NOT_CONFIGURED", "Gia sư AI chưa được cấu hình. Vui lòng liên hệ quản trị viên.")


def _invalid_response() -> AppError:
    return AppError(502, "LLM_INVALID_RESPONSE", "Model trả về nội dung chưa hợp lệ. Vui lòng thử lại.")


class ChatCompletionsClient:
    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self._settings = settings
        self._transport = transport

    def _configuration(self) -> tuple[str, str, str, float]:
        raw_values = (self._settings.llm_api_url, self._settings.llm_api_key, self._settings.llm_model)
        if any(not isinstance(value, str) or not value.strip() for value in raw_values):
            raise _not_configured()
        endpoint, key, model = (value.strip() for value in raw_values)
        if not key.isascii() or any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in key):
            raise _not_configured()
        if any(unicodedata.category(char) in {"Cc", "Cs"} for char in model):
            raise _not_configured()
        try:
            url = httpx.URL(endpoint)
        except (httpx.InvalidURL, ValueError):
            raise _not_configured() from None
        credential_names = {"key", "api_key", "api-key", "apikey", "token", "access_token", "access-token", "authorization", "password", "secret"}
        if (
            url.scheme not in {"http", "https"} or not url.host or url.userinfo or url.fragment
            or any(name.casefold() in credential_names for name in url.params)
            or key in endpoint
        ):
            raise _not_configured()
        timeout = self._settings.llm_timeout_seconds
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 1 <= timeout <= 120:
            raise _not_configured()
        return endpoint, key, model, timeout

    async def generate(self, messages: list[dict[str, str]]) -> LLMReply:
        endpoint, key, model, timeout = self._configuration()
        try:
            # Giới hạn toàn bộ thời gian gọi, ngoài timeout từng thao tác của HTTPX.
            return await asyncio.wait_for(self._request(endpoint, key, model, messages, timeout), timeout=timeout)
        except (asyncio.TimeoutError, httpx.TimeoutException):
            raise AppError(504, "LLM_TIMEOUT", "Model phản hồi quá lâu. Vui lòng thử lại.") from None
        except httpx.HTTPError:
            raise AppError(502, "LLM_UNAVAILABLE", "Chưa thể kết nối với model. Vui lòng thử lại.") from None

    async def _request(self, endpoint: str, key: str, model: str, messages: list[dict[str, str]], timeout: float) -> LLMReply:
        client = httpx.AsyncClient(
            transport=self._transport, timeout=timeout, follow_redirects=False, trust_env=False,
        )
        _protect_http_logs()
        token = _llm_request_active.set(True)
        try:
            async with client:
                async with client.stream(
                    "POST", endpoint, headers={"Authorization": "Bearer " + key, "Accept": "application/json", "Accept-Encoding": "identity"},
                    json={"model": model, "messages": messages},
                ) as response:
                    if response.status_code == 429:
                        raise AppError(429, "LLM_RATE_LIMITED", "Dịch vụ model đang giới hạn yêu cầu. Vui lòng thử lại sau.")
                    if not 200 <= response.status_code < 300:
                        raise AppError(502, "LLM_ERROR", "Dịch vụ model chưa thể xử lý yêu cầu. Vui lòng thử lại.")
                    if response.headers.get("content-encoding", "identity").strip().lower() != "identity":
                        raise _invalid_response()
                    payload = bytearray()
                    async for chunk in response.aiter_bytes(chunk_size=16 * 1024):
                        if len(payload) + len(chunk) > MAX_RESPONSE_BYTES:
                            raise _invalid_response()
                        payload.extend(chunk)
                    return self._parse_reply(payload)
        finally:
            _llm_request_active.reset(token)

    @staticmethod
    def _parse_reply(payload: bytes | bytearray) -> LLMReply:
        try:
            body = json.loads(payload.decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
        except (UnicodeError, ValueError, TypeError, KeyError, IndexError):
            raise _invalid_response() from None
        if not isinstance(content, str) or not content.strip() or len(content) > MAX_REPLY_CHARS:
            raise _invalid_response()
        if any(unicodedata.category(char) in {"Cc", "Cs"} and char not in "\n\r\t" for char in content):
            raise _invalid_response()
        usage = body.get("usage")
        token_count = usage.get("completion_tokens") if isinstance(usage, dict) else None
        if type(token_count) is not int or not 0 <= token_count <= 2**31 - 1:
            token_count = None
        return LLMReply(content=content.strip(), token_count=token_count)
