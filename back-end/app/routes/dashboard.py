"""TK-065: only the current account's completed quizzes and chat sessions."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User
from app.schemas.auth import ErrorResponse
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter(
    prefix="/api/dashboard", tags=["dashboard"],
    responses={code: {"model": ErrorResponse} for code in (401, 403, 503)},
)


def get_service(request: Request) -> DashboardService:
    return request.app.state.dashboard_service


@router.get("", response_model=DashboardResponse, summary="Thống kê quiz hoàn tất và số phiên chat của chính mình")
async def get_dashboard(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[DashboardService, Depends(get_service)],
) -> DashboardResponse:
    return await service.get_dashboard(user)
