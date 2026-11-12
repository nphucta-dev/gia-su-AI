from __future__ import annotations

import enum
from datetime import datetime
from typing import Any, TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    JSON,
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession


class ChatMessageRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),
        CheckConstraint("hint_level BETWEEN 1 AND 3", name="ck_chat_messages_hint_level"),
        CheckConstraint("feedback IN (-1, 1)", name="ck_chat_messages_feedback"),
        CheckConstraint("token_count >= 0", name="ck_chat_messages_token_count"),
        Index("ix_chat_messages_session_created_at", "session_id", "created_at"),
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
    session_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    hint_level: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    is_full_solution: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0")
    )
    feedback: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    source_refs: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, nullable=False, default=list, server_default=text("(JSON_ARRAY())")
    )
    token_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )

    session: Mapped[ChatSession] = relationship("ChatSession", back_populates="messages")
