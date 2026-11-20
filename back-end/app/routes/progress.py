"""Stored progress is private to each account, including accounts with ADMIN role."""

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User
from app.schemas.auth import ErrorResponse
from app.schemas.progress import ProgressListResponse, ProgressResponse, ReviewTopicsResponse
from app.services.progress_service import ProgressService

router = APIRouter(
    prefix="/api/progress", tags=["progress"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 404, 422)},
)
CurrentUser = Annotated[User, Depends(get_current_user)]
ProgressId = Annotated[int, Path(ge=1, le=2**31 - 1)]
Offset = Annotated[int, Query(ge=0, le=100000)]


def get_service(request: Request) -> ProgressService:
    return request.app.state.progress_service


Service = Annotated[ProgressService, Depends(get_service)]


@router.get("", response_model=ProgressListResponse, summary="Tiến độ đã lưu của tài khoản hiện tại")
async def list_progress(
    user: CurrentUser, service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Offset = 0,
) -> ProgressListResponse:
    return await service.list_progress(user, limit=limit, offset=offset)


@router.get("/review-topics", response_model=ReviewTopicsResponse, summary="Gợi ý chủ đề cần ôn theo mastery_percent tăng dần")
async def list_review_topics(
    user: CurrentUser, service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20, offset: Offset = 0,
) -> ReviewTopicsResponse:
    return await service.list_review_topics(user, limit=limit, offset=offset)


@router.get("/{progress_id}", response_model=ProgressResponse, summary="Xem một tiến độ học tập của chính mình")
async def get_progress(
    progress_id: ProgressId, user: CurrentUser, service: Service,
) -> ProgressResponse:
    return await service.get_progress(user, progress_id)
