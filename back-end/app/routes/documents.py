"""Tải và liệt kê tài liệu nguồn dành cho ADMIN."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from app.dependencies.auth import require_roles
from app.repositories.user_repository import User
from app.schemas.auth import ErrorResponse
from app.schemas.document import DocumentListResponse, DocumentOptionsResponse, DocumentResponse
from app.services.document_service import DocumentService, invalid_field
from app.utils.errors import AppError

router = APIRouter(prefix="/api/admin/documents", tags=["documents"])
AdminUser = Annotated[User, Depends(require_roles("ADMIN"))]


def get_document_service(request: Request) -> DocumentService:
    repository = getattr(request.app.state, "document_repository", None)
    if repository is None:
        raise AppError(503, "DATABASE_UNAVAILABLE", "Chưa có kết nối database cho tài liệu.")
    return DocumentService(repository, request.app.state.upload_dir)


@router.get("/options", response_model=DocumentOptionsResponse, summary="Môn và chủ đề để ADMIN tải tài liệu")
async def options(user: AdminUser, service: Annotated[DocumentService, Depends(get_document_service)]) -> DocumentOptionsResponse:
    return DocumentOptionsResponse(subjects=await service.options())


@router.get("", response_model=DocumentListResponse, summary="Danh sách tài liệu đã tải")
async def list_documents(user: AdminUser, service: Annotated[DocumentService, Depends(get_document_service)]) -> DocumentListResponse:
    return DocumentListResponse(documents=await service.list_documents())


@router.post(
    "",
    status_code=201,
    response_model=DocumentResponse,
    summary="ADMIN tải tài liệu PDF/TXT theo chủ đề",
    responses={
        401: {"model": ErrorResponse, "description": "Chưa đăng nhập"},
        403: {"model": ErrorResponse, "description": "Không phải ADMIN hoặc tài khoản bị vô hiệu hóa"},
        404: {"model": ErrorResponse, "description": "Chủ đề không tồn tại hoặc đã bị tắt"},
        413: {"model": ErrorResponse, "description": "Tệp lớn hơn 10 MB"},
        415: {"model": ErrorResponse, "description": "Body không phải multipart/form-data"},
        422: {"model": ErrorResponse, "description": "Tiêu đề, chủ đề hoặc tệp chưa hợp lệ"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {"multipart/form-data": {"schema": {
                "type": "object",
                "required": ["topic_id", "title", "file"],
                "properties": {
                    "topic_id": {"type": "integer", "minimum": 1},
                    "title": {"type": "string", "minLength": 1, "maxLength": 200},
                    "file": {"type": "string", "format": "binary"},
                },
            }}},
        }
    },
)
async def upload(
    user: AdminUser,
    request: Request,
    service: Annotated[DocumentService, Depends(get_document_service)],
) -> DocumentResponse:
    # Chỉ parse multipart sau khi dependency đã xác thực tài khoản và quyền ADMIN.
    media_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if media_type != "multipart/form-data":
        raise AppError(415, "UNSUPPORTED_MEDIA_TYPE", "Yêu cầu phải gửi multipart/form-data.")
    try:
        form = await request.form(max_files=1, max_fields=2, max_part_size=64 * 1024)
    except HTTPException as error:
        if error.status_code == 413:
            raise
        raise AppError(400, "INVALID_MULTIPART", "Biểu mẫu tải tài liệu không hợp lệ.") from None
    try:
        if set(form) - {"file", "topic_id", "title"}:
            raise invalid_field("body", "Chỉ gửi tệp, chủ đề và tiêu đề tài liệu.")
        file = form.get("file")
        if not isinstance(file, UploadFile):
            raise invalid_field("file", "Vui lòng chọn tệp PDF hoặc TXT.")
        if len(form.getlist("topic_id")) != 1 or len(form.getlist("title")) != 1:
            raise invalid_field("body", "Vui lòng gửi đúng một chủ đề và một tiêu đề tài liệu.")
        document = await service.upload(topic_id=form.get("topic_id"), title=form.get("title"), file=file)
        return DocumentResponse(message="Tải tài liệu thành công. Tài liệu đang chờ xử lý.", document=document)
    finally:
        await form.close()
