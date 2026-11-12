from typing import Annotated

from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User
from app.schemas.auth import ErrorResponse, PublicUser
from app.schemas.session import MeResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get(
    "/me",
    response_model=MeResponse,
    summary="Thông tin người dùng đang đăng nhập",
    responses={
        401: {
            "model": ErrorResponse,
            "description": "NOT_AUTHENTICATED (thiếu token), TOKEN_EXPIRED (hết hạn) hoặc INVALID_TOKEN",
        },
    },
)
async def me(user: Annotated[User, Depends(get_current_user)]) -> MeResponse:
    """Dùng để kiểm tra token còn hiệu lực và lấy hồ sơ cơ bản, ví dụ khi mở lại trang."""
    return MeResponse(
        user=PublicUser(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            created_at=user.created_at,
        )
    )
