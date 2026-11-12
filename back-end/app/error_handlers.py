"""Định dạng lỗi thống nhất cho toàn bộ API::

    {"error": {"code": "...", "message": "...", "fields": {...}}}
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.utils.errors import AppError
from app.validators.register_validator import MESSAGES as VALIDATION_MESSAGES


def error_body(code: str, message: str, fields: dict[str, str] | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if fields:
        error["fields"] = fields
    return {"error": error}


def error_response(
    status_code: int,
    code: str,
    message: str,
    fields: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(error_body(code, message, fields), status_code=status_code, headers=headers)


_HTTP_ERRORS = {
    404: ("NOT_FOUND", "Không tìm thấy đường dẫn yêu cầu."),
    405: ("METHOD_NOT_ALLOWED", "Phương thức không được hỗ trợ cho đường dẫn này."),
    413: ("PAYLOAD_TOO_LARGE", "Dữ liệu gửi lên quá lớn."),
}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return error_response(exc.status_code, exc.code, exc.message, exc.fields, exc.headers)

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Lỗi do FastAPI phát hiện trước khi tới validator riêng: chủ yếu là JSON sai cú pháp.
        if any(error.get("type") == "json_invalid" for error in exc.errors()):
            return error_response(400, "INVALID_JSON", "Nội dung JSON không hợp lệ.")
        return error_response(
            422,
            "VALIDATION_ERROR",
            "Dữ liệu gửi lên chưa hợp lệ.",
            {"body": VALIDATION_MESSAGES["body"]},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = _HTTP_ERRORS.get(exc.status_code, ("HTTP_ERROR", "Yêu cầu không hợp lệ."))
        return error_response(exc.status_code, code, message, headers=exc.headers)

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Lỗi không lường trước: không lộ chi tiết cho client. Server vẫn ghi traceback
        # vào log vì Starlette ném lại lỗi sau khi gửi phản hồi này.
        return error_response(500, "INTERNAL_ERROR", "Đã xảy ra lỗi phía máy chủ. Vui lòng thử lại sau.")
