from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.chat_message import ChatMessage
    from app.models.topic import Topic
    from app.models.user import User


class ChatSession(Base):
    __tablename__ = "chat_sessions"


    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("topics.id", ondelete="RESTRICT"),
        nullable=False,
    )
    title: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP(6)"),
        onupdate=text("CURRENT_TIMESTAMP(6)"),
    )

    __table_args__ = (
        Index("ix_chat_sessions_user_updated_at", user_id, updated_at.desc()),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_as_cs",
        },
    )

    user: Mapped[User] = relationship("User", back_populates="chat_sessions")
    topic: Mapped[Topic] = relationship("Topic", back_populates="chat_sessions")
    messages: Mapped[list[ChatMessage]] = relationship(
        "ChatMessage", back_populates="session", cascade="all, delete-orphan", passive_deletes=True
    )
