"""TK-079: Tách kiểm tra quota khỏi các endpoint GET lịch sử và GET dashboard/tiến độ.

Dependency `require_ai_quota` chỉ được gắn vào các endpoint phát sinh yêu cầu AI (POST chat/hint/solution),
không bao giờ gắn vào các endpoint đọc lịch sử chat hoặc dashboard/tiến độ.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User


async def require_ai_quota(
    user: Annotated[User, Depends(get_current_user)],
    request: Request,
) -> User:
    quota_service = getattr(request.app.state, "quota_service", None)
    if quota_service is not None:
        await quota_service.ensure_within_quota(user)
    return user
