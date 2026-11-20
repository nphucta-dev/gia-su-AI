"""Read-only daily quota does not block private history or other read APIs."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User
from app.schemas.ai_quota import AiQuotaItem

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/quota", response_model=AiQuotaItem)
async def quota(request: Request, user: Annotated[User, Depends(get_current_user)]) -> AiQuotaItem:
    return await request.app.state.ai_quota_service.get_quota(user.id)
