"""Dữ liệu người dùng dùng chung và repository trong bộ nhớ cho kiểm thử.

Ứng dụng dùng ``SqlAlchemyUserRepository`` để lưu MySQL. Repository trong
bộ nhớ có thể truyền vào ``create_app`` cho các test không cần database.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.utils.errors import DuplicateEmailError


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str
    password_hash: str
    role: str
    created_at: str
    is_active: bool = True


def parse_user_id(user_id: int | str) -> int | None:
    """Nhận ID số hoặc subject JWT; chỉ chấp nhận số nguyên dương trong miền INT."""
    if isinstance(user_id, bool):
        return None
    if isinstance(user_id, str):
        if not user_id or len(user_id) > 10 or not all("0" <= char <= "9" for char in user_id):
            return None
        user_id = int(user_id)
    if not isinstance(user_id, int) or not 1 <= user_id <= 2**31 - 1:
        return None
    return user_id


class InMemoryUserRepository:
    def __init__(self) -> None:
        self._users: dict[int, User] = {}  # id -> user
        self._id_by_email: dict[str, int] = {}  # email -> id
        self._next_id = 1

    async def find_by_email(self, email: str) -> User | None:
        user_id = self._id_by_email.get(email)
        return self._users.get(user_id) if user_id else None

    async def find_by_id(self, user_id: int | str) -> User | None:
        parsed_id = parse_user_id(user_id)
        return self._users.get(parsed_id) if parsed_id is not None else None

    async def create(self, *, name: str, email: str, password_hash: str, role: str) -> User:
        # Kiểm tra và ghi không có điểm ``await`` ở giữa nên hai request đăng ký
        # cùng email đồng thời không thể cùng thành công.
        if email in self._id_by_email:
            raise DuplicateEmailError(email)
        user = User(
            id=self._next_id,
            name=name,
            email=email,
            password_hash=password_hash,
            role=role,
            created_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        )
        self._next_id += 1
        self._users[user.id] = user
        self._id_by_email[email] = user.id
        return user
