"""Giới hạn kích thước body request (mặc định 10 KB cho API JSON)."""

from __future__ import annotations

from starlette.exceptions import HTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.error_handlers import error_response


class BodySizeLimitMiddleware:
    """Từ chối body lớn hơn ``max_bytes`` bằng 413.

    Kiểm tra header ``Content-Length`` trước để từ chối sớm, đồng thời đếm số byte
    thực nhận để chặn cả request gửi theo kiểu chunked không có Content-Length.
    """

    def __init__(self, app: ASGIApp, max_bytes: int, upload_max_bytes: int | None = None) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.upload_max_bytes = upload_max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes = self.max_bytes
        if (
            self.upload_max_bytes is not None
            and scope.get("method") == "POST"
            and scope.get("path", "").rstrip("/") == "/api/admin/documents"
        ):
            # Chừa chỗ cho multipart; service vẫn giới hạn riêng file ở 10 MiB.
            max_bytes = self.upload_max_bytes

        declared = dict(scope.get("headers", [])).get(b"content-length")
        if declared is not None:
            try:
                too_large = int(declared) > max_bytes
            except ValueError:
                too_large = False
            if too_large:
                response = error_response(413, "PAYLOAD_TOO_LARGE", "Dữ liệu gửi lên quá lớn.")
                await response(scope, receive, send)
                return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > max_bytes:
                    # Được ExceptionMiddleware của Starlette đổi thành phản hồi 413 JSON.
                    raise HTTPException(status_code=413)
            return message

        await self.app(scope, limited_receive, send)
