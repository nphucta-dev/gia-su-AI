"""Luồng đăng ký và đăng nhập tài khoản."""

from __future__ import annotations

import asyncio
import secrets
from functools import lru_cache
from typing import Any, Callable, Protocol

from app.repositories.user_repository import User
from app.utils.errors import AppError, DuplicateEmailError
from app.utils.password import hash_password, verify_password
from app.validators.login_validator import validate_login_input
from app.validators.register_validator import validate_register_input

DEFAULT_ROLE = "LEARNER"
EMAIL_TAKEN_MESSAGE = "Email này đã được đăng ký. Vui lòng đăng nhập hoặc dùng email khác."
INVALID_CREDENTIALS_MESSAGE = "Email hoặc mật khẩu không chính xác."


class UserRepository(Protocol):
    async def find_by_email(self, email: str) -> User | None: ...

    async def find_by_id(self, user_id: int | str) -> User | None: ...

    async def create(self, *, name: str, email: str, password_hash: str, role: str) -> User: ...


def _email_taken() -> AppError:
    return AppError(409, "EMAIL_ALREADY_EXISTS", EMAIL_TAKEN_MESSAGE, {"email": EMAIL_TAKEN_MESSAGE})


@lru_cache(maxsize=1)
def _dummy_password_hash() -> str:
    # Chỉ tính một lần khi cần; không băm thêm lúc khởi tạo app hoặc đăng ký.
    return hash_password(secrets.token_urlsafe(32))


def _verify_login_password(password: str, password_hash: str | None) -> bool:
    # Email không tồn tại vẫn thực hiện phép băm như một lần đăng nhập sai.
    return verify_password(password, password_hash if password_hash is not None else _dummy_password_hash())


class AuthService:
    def __init__(
        self,
        user_repository: UserRepository,
        password_hasher: Callable[[str], str] = hash_password,
    ) -> None:
        self._users = user_repository
        self._hash = password_hasher

    async def register(self, payload: Any) -> User:
        """Kiểm tra dữ liệu -> kiểm tra email trùng -> băm mật khẩu -> lưu.

        Raises:
            AppError: 422 khi dữ liệu sai, 409 khi email đã đăng ký.
        """
        result = validate_register_input(payload)
        if not result.valid:
            raise AppError(422, "VALIDATION_ERROR", "Dữ liệu đăng ký chưa hợp lệ.", result.errors)
        data = result.value
        assert data is not None

        # Kiểm tra sớm để không tốn CPU băm mật khẩu cho email đã có.
        if await self._users.find_by_email(data.email):
            raise _email_taken()

        # scrypt tốn CPU và chạy đồng bộ, đưa ra thread pool để không chặn event loop.
        password_hash = await asyncio.to_thread(self._hash, data.password)
        try:
            return await self._users.create(
                name=data.name,
                email=data.email,
                password_hash=password_hash,
                role=DEFAULT_ROLE,
            )
        except DuplicateEmailError:
            # Hai request cùng email chạy đồng thời: request đến sau thua ở bước lưu.
            raise _email_taken() from None

    async def login(self, payload: Any) -> User:
        result = validate_login_input(payload)
        if not result.valid:
            raise AppError(422, "VALIDATION_ERROR", "Dữ liệu đăng nhập chưa hợp lệ.", result.errors)
        data = result.value
        assert data is not None

        user = await self._users.find_by_email(data.email)
        password_matches = await asyncio.to_thread(
            _verify_login_password, data.password, user.password_hash if user is not None else None
        )
        if user is None or not password_matches:
            raise AppError(
                401,
                "INVALID_CREDENTIALS",
                INVALID_CREDENTIALS_MESSAGE,
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not user.is_active:
            raise AppError(403, "FORBIDDEN", "Tài khoản đã bị vô hiệu hóa.")
        return user
