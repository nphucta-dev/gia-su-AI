"""Đọc và cập nhật hồ sơ của chính tài khoản đã xác thực."""

from __future__ import annotations

from typing import Any, Protocol

from app.repositories.user_repository import User
from app.services.token_service import invalid_token_error
from app.utils.errors import AppError
from app.validators.profile_validator import validate_profile_input


class ProfileRepository(Protocol):
    async def update_profile(
        self,
        user_id: int,
        *,
        name: str | None = None,
        birth_year: int | None = None,
        update_birth_year: bool = False,
    ) -> User | None: ...


class ProfileService:
    def __init__(self, repository: ProfileRepository) -> None:
        self._users = repository

    async def update(self, user: User, payload: Any) -> User:
        validation = validate_profile_input(payload)
        if not validation.valid:
            raise AppError(422, "VALIDATION_ERROR", "Dữ liệu hồ sơ chưa hợp lệ.", validation.errors)
        data = validation.value
        assert data is not None
        updated = await self._users.update_profile(
            user.id,
            name=data.name,
            birth_year=data.birth_year,
            update_birth_year=data.update_birth_year,
        )
        if updated is None:
            raise invalid_token_error()
        if not updated.is_active:
            raise AppError(403, "FORBIDDEN", "Tài khoản đã bị vô hiệu hóa.")
        return updated
