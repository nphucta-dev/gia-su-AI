"""API xem tài liệu học tập dành cho người học đã đăng nhập (LEARNER và ADMIN)."""

from __future__ import annotations

import re
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import FileResponse

from app.dependencies.auth import get_current_user
from app.schemas.auth import ErrorResponse
from app.schemas.learning_document import (
    LearningDocumentDetailResponse,
    LearningDocumentListResponse,
    TopicDocumentListResponse,
)
from app.services.learning_document_service import LearningDocumentService
from app.utils.errors import AppError

router = APIRouter(
    prefix="/api/documents",
    tags=["learning-documents"],
    dependencies=[Depends(get_current_user)],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422, 503)},
)

topic_documents_router = APIRouter(
    prefix="/api/catalog",
    tags=["catalog"],
    dependencies=[Depends(get_current_user)],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422, 503)},
)

DocumentId = Annotated[int, Path(ge=1, le=2**31 - 1)]
TopicIdPath = Annotated[int, Path(ge=1, le=2**31 - 1)]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageOffset = Annotated[int, Query(ge=0, le=100000)]


def get_learning_document_service(request: Request) -> LearningDocumentService:
    repository = getattr(request.app.state, "document_repository", None)
    if repository is None:
        raise AppError(503, "DATABASE_UNAVAILABLE", "Chưa có kết nối database cho tài liệu.")
    return LearningDocumentService(repository, request.app.state.upload_dir)


Service = Annotated[LearningDocumentService, Depends(get_learning_document_service)]


def _content_disposition(file_name: str, *, download: bool) -> str:
    disposition = "attachment" if download else "inline"
    ascii_fallback = re.sub(r'[^A-Za-z0-9._ -]+', "_", file_name).strip(" ._") or "document"
    encoded = quote(file_name, safe="")
    return f'{disposition}; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded}'


@router.get(
    "",
    response_model=LearningDocumentListResponse,
    summary="Danh sách tài liệu học tập đang mở",
    description="Chỉ trả tài liệu có status=ready, is_active=true thuộc chủ đề và môn học đang active.",
)
async def list_learning_documents(
    service: Service,
    topic_id: Annotated[int | None, Query(alias="topicId", ge=1, le=2**31 - 1)] = None,
    subject_id: Annotated[int | None, Query(alias="subjectId", ge=1, le=2**31 - 1)] = None,
    grade_level: Annotated[str | None, Query(alias="gradeLevel", max_length=50)] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    limit: PageLimit = 20,
    offset: PageOffset = 0,
) -> LearningDocumentListResponse:
    return await service.list_documents(
        topic_id=topic_id,
        subject_id=subject_id,
        grade_level=grade_level,
        query=q,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/{document_id}",
    response_model=LearningDocumentDetailResponse,
    summary="Xem chi tiết và nội dung tài liệu học tập",
    description="Trả thông tin tài liệu, toàn văn đã trích xuất và danh sách các đoạn theo thứ tự.",
)
async def get_learning_document(
    document_id: DocumentId,
    service: Service,
) -> LearningDocumentDetailResponse:
    document = await service.get_document(document_id)
    return LearningDocumentDetailResponse(document=document)


@router.get(
    "/{document_id}/file",
    summary="Xem hoặc tải tệp gốc (PDF/TXT) của tài liệu học tập",
    responses={
        200: {
            "description": "Tệp PDF hoặc TXT gốc của tài liệu học tập",
            "content": {"application/pdf": {}, "text/plain": {}},
        }
    },
)
async def get_learning_document_file(
    document_id: DocumentId,
    service: Service,
    download: Annotated[bool, Query(description="Đặt true để tải tệp về máy thay vì xem trực tiếp.")] = False,
) -> FileResponse:
    resolved = await service.get_document_file(document_id)
    return FileResponse(
        path=resolved.path,
        media_type=resolved.media_type,
        headers={"Content-Disposition": _content_disposition(resolved.file_name, download=download)},
    )


@topic_documents_router.get(
    "/topics/{topic_id}/documents",
    response_model=TopicDocumentListResponse,
    summary="Danh sách tài liệu học tập đang mở theo chủ đề",
)
async def list_topic_documents(
    topic_id: TopicIdPath,
    service: Service,
    limit: PageLimit = 20,
    offset: PageOffset = 0,
) -> TopicDocumentListResponse:
    return await service.list_topic_documents(topic_id, limit=limit, offset=offset)
