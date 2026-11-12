"""Các lỗi dùng chung giữa service, repository và tầng HTTP."""

from __future__ import annotations


class AppError(Exception):
    """Lỗi nghiệp vụ có mã HTTP và mã lỗi ổn định để front-end xử lý.

    ``fields`` (tuỳ chọn) là map ``{tên trường: thông báo}`` để hiển thị cạnh ô nhập.
    ``headers`` (tuỳ chọn) là header HTTP đi kèm phản hồi, ví dụ ``WWW-Authenticate``.
    """

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        fields: dict[str, str] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.fields = fields
        self.headers = headers


class DuplicateEmailError(Exception):
    """Repository ném lỗi này khi email đã tồn tại (ràng buộc duy nhất)."""

    def __init__(self, email: str) -> None:
        super().__init__(f"Email đã tồn tại: {email}")
        self.email = email
