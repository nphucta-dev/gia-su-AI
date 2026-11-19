"""TK-077: API thông tin quota trả remaining và next_reset_at rõ ràng."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User
from app.schemas.auth import ErrorResponse
from app.schemas.quota import QuotaResponse
from app.services.quota_service import QuotaService

router = APIRouter(
    prefix="/api/quota",
    tags=["quota"],
    responses={code: {"model": ErrorResponse} for code in (401, 403)},
)
CurrentUser = Annotated[User, Depends(get_current_user)]


def get_service(request: Request) -> QuotaService:
    return request.app.state.quota_service


@router.get("", response_model=QuotaResponse, summary="Xem số lượt AI còn lại trong ngày và thời điểm reset")
async def get_quota(
    user: CurrentUser,
    service: Annotated[QuotaService, Depends(get_service)],
) -> QuotaResponse:
    return await service.get_quota(user)
