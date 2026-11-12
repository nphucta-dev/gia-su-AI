from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, Boolean, CheckConstraint, SmallInteger, String, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession
    from app.models.learning_progress import LearningProgress
    from app.models.quiz import Quiz


class UserRole(str, enum.Enum):
    LEARNER = "LEARNER"
    ADMIN = "ADMIN"


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("email", name="uq_users_email"),
        CheckConstraint("role IN ('LEARNER', 'ADMIN')", name="ck_users_role"),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_as_cs",
        },
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(120), nullable=False)
    birth_year: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    role: Mapped[str] = mapped_column(
        String(10), nullable=False, default=UserRole.LEARNER.value, server_default=text("'LEARNER'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        onupdate=text("CURRENT_TIMESTAMP(6)"),
    )

    chat_sessions: Mapped[list[ChatSession]] = relationship(
        "ChatSession", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    quizzes: Mapped[list[Quiz]] = relationship(
        "Quiz", back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    learning_progress: Mapped[list[LearningProgress]] = relationship(
        "LearningProgress",
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
