from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request

from app.dependencies.auth import get_current_user
from app.schemas.auth import ErrorResponse
from app.schemas.catalog import OpenTopicResponse, SubjectListResponse
from app.services.catalog_service import CatalogService

# Mọi API danh mục đều cần đăng nhập (LEARNER hoặc ADMIN).
router = APIRouter(
    prefix="/api/catalog",
    tags=["catalog"],
    dependencies=[Depends(get_current_user)],
    responses={
        401: {"model": ErrorResponse, "description": "NOT_AUTHENTICATED, TOKEN_EXPIRED hoặc INVALID_TOKEN"},
        403: {"model": ErrorResponse, "description": "FORBIDDEN: tài khoản bị vô hiệu hóa"},
    },
)


def get_catalog_service(request: Request) -> CatalogService:
    return request.app.state.catalog_service


@router.get(
    "/subjects",
    response_model=SubjectListResponse,
    summary="Môn học, chương và chủ đề đang mở",
)
async def list_subjects(
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> SubjectListResponse:
    """Chỉ trả môn active và chủ đề active; môn chưa có chủ đề active nào bị ẩn."""
    return await service.list_subjects()


@router.get(
    "/topics/{topic_id}",
    response_model=OpenTopicResponse,
    summary="Kiểm tra chủ đề có mở được luồng học không",
    responses={404: {"model": ErrorResponse, "description": "TOPIC_NOT_FOUND: chủ đề/môn không tồn tại hoặc đã tắt"}},
)
async def get_open_topic(
    topic_id: Annotated[int, Path(ge=1, le=2**31 - 1)],
    service: Annotated[CatalogService, Depends(get_catalog_service)],
) -> OpenTopicResponse:
    return OpenTopicResponse(topic=await service.get_open_topic(topic_id))
