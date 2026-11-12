from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, Request, Response

from app.dependencies.auth import get_current_user
from app.repositories.user_repository import User
from app.routes.auth import require_json
from app.schemas.auth import ErrorResponse
from app.schemas.profile import ProfileResponse, ProfileUpdateResponse, ProfileUser
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/api/profile", tags=["profile"])


def get_profile_service(request: Request) -> ProfileService:
    return ProfileService(request.app.state.user_repository)


def public_profile(user: User) -> ProfileUser:
    return ProfileUser(
        id=user.id,
        name=user.name,
        email=user.email,
        role=user.role,
        created_at=user.created_at,
        birth_year=user.birth_year,
    )


@router.get(
    "",
    response_model=ProfileResponse,
    summary="Xem hồ sơ cá nhân của tài khoản đang đăng nhập",
    responses={401: {"model": ErrorResponse}, 403: {"model": ErrorResponse}},
)
async def get_profile(
    user: Annotated[User, Depends(get_current_user)],
    response: Response,
) -> ProfileResponse:
    response.headers["Cache-Control"] = "no-store"
    return ProfileResponse(user=public_profile(user))


@router.patch(
    "",
    response_model=ProfileUpdateResponse,
    summary="Cập nhật họ tên và năm sinh của chính mình",
    dependencies=[Depends(require_json)],
    responses={
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        415: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "minProperties": 1,
                        "additionalProperties": False,
                        "properties": {
                            "name": {"type": "string", "minLength": 1, "maxLength": 120},
                            "birthYear": {
                                "anyOf": [
                                    {"type": "integer", "minimum": 1900, "maximum": datetime.now(timezone.utc).year},
                                    {"type": "null"},
                                ],
                                "description": "Bỏ qua để giữ nguyên; null để xóa năm sinh.",
                            },
                        },
                    }
                }
            },
        }
    },
)
async def update_profile(
    user: Annotated[User, Depends(get_current_user)],
    service: Annotated[ProfileService, Depends(get_profile_service)],
    response: Response,
    payload: Annotated[Any, Body()] = None,
) -> ProfileUpdateResponse:
    updated = await service.update(user, payload)
    response.headers["Cache-Control"] = "no-store"
    return ProfileUpdateResponse(message="Cập nhật hồ sơ thành công.", user=public_profile(updated))
