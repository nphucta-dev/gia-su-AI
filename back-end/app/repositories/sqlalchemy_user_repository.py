"""Kho người dùng MySQL, giữ cùng giao diện với repository kiểm thử."""

import asyncio
import re
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.user import User as UserModel
from app.repositories.user_repository import User, parse_user_id
from app.utils.errors import DuplicateEmailError


class SqlAlchemyUserRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def find_by_email(self, email: str) -> User | None:
        return await asyncio.to_thread(self._find_by_email, email.strip().lower())

    async def find_by_id(self, user_id: int | str) -> User | None:
        parsed_id = parse_user_id(user_id)
        if parsed_id is None:
            return None
        return await asyncio.to_thread(self._find_by_id, parsed_id)

    async def create(self, *, name: str, email: str, password_hash: str, role: str) -> User:
        return await asyncio.to_thread(
            self._create,
            name=name,
            email=email.strip().lower(),
            password_hash=password_hash,
            role=role,
        )

    async def update_profile(
        self,
        user_id: int,
        *,
        name: str | None = None,
        birth_year: int | None = None,
        update_birth_year: bool = False,
    ) -> User | None:
        parsed_id = parse_user_id(user_id)
        if parsed_id is None:
            return None
        return await asyncio.to_thread(
            self._update_profile,
            parsed_id,
            name=name,
            birth_year=birth_year,
            update_birth_year=update_birth_year,
        )

    def _find_by_email(self, email: str) -> User | None:
        with self._sessions() as db:
            user = db.scalar(select(UserModel).where(UserModel.email == email))
            return self._to_user(user) if user is not None else None

    def _find_by_id(self, user_id: int) -> User | None:
        with self._sessions() as db:
            user = db.get(UserModel, user_id)
            return self._to_user(user) if user is not None else None

    def _create(self, *, name: str, email: str, password_hash: str, role: str) -> User:
        try:
            with self._sessions.begin() as db:
                user = UserModel(
                    full_name=name,
                    email=email,
                    password_hash=password_hash,
                    role=role,
                )
                db.add(user)
                db.flush()
                db.refresh(user)
                saved_user = self._to_user(user)
            return saved_user
        except IntegrityError as exc:
            # Chỉ UNIQUE email là lỗi đăng ký trùng; CHECK/FK khác vẫn là lỗi CSDL.
            args = getattr(exc.orig, "args", ())
            if (
                len(args) >= 2
                and args[0] == 1062
                and re.search(r"['`](?:[^'`]+\.)?uq_users_email['`]$", str(args[1]))
            ):
                raise DuplicateEmailError(email) from None
            raise

    def _update_profile(
        self,
        user_id: int,
        *,
        name: str | None,
        birth_year: int | None,
        update_birth_year: bool,
    ) -> User | None:
        with self._sessions.begin() as db:
            user = db.get(UserModel, user_id, with_for_update=True)
            if user is None:
                return None
            if not user.is_active:
                return self._to_user(user)
            if name is not None:
                user.full_name = name
            if update_birth_year:
                user.birth_year = birth_year
            db.flush()
            db.refresh(user)
            saved_user = self._to_user(user)
        return saved_user

    @staticmethod
    def _to_user(user: UserModel) -> User:
        created_at = user.created_at.astimezone(timezone.utc)
        return User(
            id=user.id,
            name=user.full_name,
            email=user.email,
            password_hash=user.password_hash,
            role=user.role,
            created_at=created_at.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            is_active=user.is_active,
            birth_year=user.birth_year,
        )
