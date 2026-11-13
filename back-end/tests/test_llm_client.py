"""Kiểm thử transport bằng HTTP giả lập; không gửi dữ liệu tới nhà cung cấp thật."""

import asyncio
import json
import logging
from dataclasses import replace

import httpx
import pytest

from app.config import Settings, load_settings
from app.services.llm_client import ChatCompletionsClient, LLMReply, MAX_REPLY_CHARS, MAX_RESPONSE_BYTES
from app.utils.errors import AppError

pytestmark = pytest.mark.anyio
SETTINGS = Settings(
    llm_api_url="https://provider.example.invalid/custom/chat?version=1",
    llm_api_key="private-test-api-key",
    llm_model="test-model",
)
MESSAGES = [{"role": "system", "content": "Gợi mở."}, {"role": "user", "content": "Hàm số là gì?"}]


def reply(content="Bạn đã biết đại lượng nào thay đổi chưa?", *, usage=None):
    result = {"choices": [{"message": {"role": "assistant", "content": content}}]}
    if usage is not None:
        result["usage"] = usage
    return result


async def test_full_endpoint_model_and_authorization_only_in_header():
    requests = []

    async def handle(request):
        requests.append(request)
        assert str(request.url) == SETTINGS.llm_api_url
        assert request.headers["Authorization"] == "Bearer " + SETTINGS.llm_api_key
        payload = json.loads(request.content)
        assert payload == {"model": SETTINGS.llm_model, "messages": MESSAGES}
        assert SETTINGS.llm_api_key.encode() not in request.content
        assert request.extensions["timeout"]["read"] == 30
        return httpx.Response(200, json=reply("  Một gợi ý.\nBạn thử tiếp nhé?  ", usage={"completion_tokens": 42}))

    client = ChatCompletionsClient(SETTINGS, transport=httpx.MockTransport(handle))
    result = await client.generate(MESSAGES)
    assert result == LLMReply("Một gợi ý.\nBạn thử tiếp nhé?", 42)
    assert len(requests) == 1


@pytest.mark.parametrize("changes", [
    {"llm_api_key": ""}, {"llm_api_url": ""}, {"llm_model": ""},
    {"llm_api_url": "ftp://provider.example.invalid/chat"},
    {"llm_api_url": "https://user:secret@provider.example.invalid/chat"},
    {"llm_api_url": "https://provider.example.invalid/chat#secret"},
    {"llm_api_url": "https://provider.example.invalid/chat?api-key=secret"},
    {"llm_api_url": "https://provider.example.invalid/" + SETTINGS.llm_api_key},
    {"llm_api_key": "key\r\nInjected: value"}, {"llm_api_key": "có-dấu"},
    {"llm_model": "model\x00invalid"}, {"llm_timeout_seconds": 0},
    {"llm_timeout_seconds": float("inf")}, {"llm_timeout_seconds": True},
])
async def test_missing_or_unsafe_config_never_calls_transport(changes):
    def unexpected(_):
        raise AssertionError("Transport must not be called for unusable configuration")

    client = ChatCompletionsClient(replace(SETTINGS, **changes), transport=httpx.MockTransport(unexpected))
    with pytest.raises(AppError) as failure:
        await client.generate(MESSAGES)
    assert failure.value.status_code == 503 and failure.value.code == "LLM_NOT_CONFIGURED"
    assert SETTINGS.llm_api_key not in failure.value.message


@pytest.mark.parametrize("status,expected_code", [(301, "LLM_ERROR"), (302, "LLM_ERROR"), (401, "LLM_ERROR"), (403, "LLM_ERROR"), (500, "LLM_ERROR"), (429, "LLM_RATE_LIMITED")])
async def test_provider_errors_do_not_forward_body_or_redirect_credentials(status, expected_code):
    calls = []

    def handle(request):
        calls.append(str(request.url))
        return httpx.Response(status, headers={"Location": "https://different.example.invalid/"}, text=SETTINGS.llm_api_key + SETTINGS.llm_api_url)

    client = ChatCompletionsClient(SETTINGS, transport=httpx.MockTransport(handle))
    with pytest.raises(AppError) as failure:
        await client.generate(MESSAGES)
    assert failure.value.code == expected_code
    assert failure.value.status_code == (429 if status == 429 else 502)
    assert SETTINGS.llm_api_key not in failure.value.message and SETTINGS.llm_api_url not in failure.value.message
    assert len(calls) == 1


@pytest.mark.parametrize("error,expected_code,expected_status", [
    (httpx.ConnectError, "LLM_UNAVAILABLE", 502),
    (httpx.ReadError, "LLM_UNAVAILABLE", 502),
    (httpx.ReadTimeout, "LLM_TIMEOUT", 504),
    (httpx.ConnectTimeout, "LLM_TIMEOUT", 504),
])
async def test_transport_failures_return_safe_errors(error, expected_code, expected_status):
    def handle(request):
        raise error(SETTINGS.llm_api_key + SETTINGS.llm_api_url, request=request)

    client = ChatCompletionsClient(SETTINGS, transport=httpx.MockTransport(handle))
    with pytest.raises(AppError) as failure:
        await client.generate(MESSAGES)
    assert failure.value.code == expected_code and failure.value.status_code == expected_status
    assert SETTINGS.llm_api_key not in failure.value.message and SETTINGS.llm_api_url not in failure.value.message


async def test_entire_call_timeout_cancels_slow_provider():
    cancelled = []

    async def handle(_):
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return httpx.Response(200, json=reply())

    client = ChatCompletionsClient(replace(SETTINGS, llm_timeout_seconds=1), transport=httpx.MockTransport(handle))
    with pytest.raises(AppError) as failure:
        await client.generate(MESSAGES)
    assert failure.value.code == "LLM_TIMEOUT" and cancelled == [True]


@pytest.mark.parametrize("body", [
    None, [], {}, {"choices": []}, {"choices": [None]},
    {"choices": [{"message": {"content": None}}]}, reply(" "), reply(123),
    reply("x" * (MAX_REPLY_CHARS + 1)), reply("bad\ud800"), reply("bad\x00content"),
])
async def test_invalid_response_shapes_are_rejected(body):
    client = ChatCompletionsClient(SETTINGS, transport=httpx.MockTransport(lambda _: httpx.Response(200, content=json.dumps(body).encode("utf-8"))))
    with pytest.raises(AppError) as failure:
        await client.generate(MESSAGES)
    assert failure.value.status_code == 502 and failure.value.code == "LLM_INVALID_RESPONSE"


@pytest.mark.parametrize("content", [b"not-json", b"\xff\xfe", b"x" * (MAX_RESPONSE_BYTES + 1)])
async def test_malformed_or_oversized_bytes_are_rejected(content):
    client = ChatCompletionsClient(SETTINGS, transport=httpx.MockTransport(lambda _: httpx.Response(200, content=content)))
    with pytest.raises(AppError) as failure:
        await client.generate(MESSAGES)
    assert failure.value.code == "LLM_INVALID_RESPONSE"


@pytest.mark.parametrize("count", [None, -1, True, "42", 2**31])
async def test_untrusted_optional_usage_is_not_stored_as_token_count(count):
    client = ChatCompletionsClient(SETTINGS, transport=httpx.MockTransport(lambda _: httpx.Response(200, json=reply(usage={"completion_tokens": count}))))
    assert (await client.generate(MESSAGES)).token_count is None


async def test_logging_is_private_for_this_call_and_resumes_afterwards(caplog):
    caplog.set_level(logging.DEBUG)

    class LoggedTransport(httpx.MockTransport):
        async def aclose(self):
            logging.getLogger("httpcore.connection").debug("closing %s %s", SETTINGS.llm_api_key, SETTINGS.llm_api_url)
            await super().aclose()

    def handle(_):
        logging.getLogger("httpx").info("request %s %s", SETTINGS.llm_api_key, SETTINGS.llm_api_url)
        logging.getLogger("httpcore.new_logger").debug("headers %s", SETTINGS.llm_api_key)
        return httpx.Response(200, json=reply())

    client = ChatCompletionsClient(SETTINGS, transport=LoggedTransport(handle))
    await client.generate(MESSAGES)
    assert SETTINGS.llm_api_key not in caplog.text and SETTINGS.llm_api_url not in caplog.text
    logging.getLogger("httpx").info("unrelated HTTP request")
    assert "unrelated HTTP request" in caplog.text


@pytest.mark.parametrize("raw,expected", [("", 30), (" 12.5 ", 12.5), ("1", 1), ("120", 120)])
async def test_timeout_env_is_optional_and_bounded(monkeypatch, raw, expected):
    monkeypatch.setenv("JWT_SECRET", "llm-timeout-test-" + "x" * 40)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", raw)
    assert load_settings().llm_timeout_seconds == expected


@pytest.mark.parametrize("raw", ["nan", "inf", "0", "-1", "121", "bad"])
async def test_bad_timeout_env_fails_without_echoing_config_value(monkeypatch, raw):
    monkeypatch.setenv("JWT_SECRET", "llm-timeout-test-" + "x" * 40)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", raw)
    with pytest.raises(ValueError, match="LLM_TIMEOUT_SECONDS"):
        load_settings()
