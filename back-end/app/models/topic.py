from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, Boolean, ForeignKey, Index, String, Text, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.chat_session import ChatSession
    from app.models.document import Document
    from app.models.learning_progress import LearningProgress
    from app.models.quiz import Quiz
    from app.models.subject import Subject


class Topic(Base):
    __tablename__ = "topics"
    __table_args__ = (
        UniqueConstraint(
            "subject_id", "chapter_name", "name", name="uq_topics_subject_id_chapter_name_name"
        ),
        Index("ix_topics_subject_id", "subject_id"),
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
    subject_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("subjects.id", ondelete="RESTRICT"),
        nullable=False,
    )
    chapter_name: Mapped[str] = mapped_column(String(150), nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1")
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )

    subject: Mapped[Subject] = relationship("Subject", back_populates="topics")
    documents: Mapped[list[Document]] = relationship(
        "Document", back_populates="topic", passive_deletes="all"
    )
    chat_sessions: Mapped[list[ChatSession]] = relationship(
        "ChatSession", back_populates="topic", passive_deletes="all"
    )
    quizzes: Mapped[list[Quiz]] = relationship(
        "Quiz", back_populates="topic", passive_deletes="all"
    )
    learning_progress: Mapped[list[LearningProgress]] = relationship(
        "LearningProgress", back_populates="topic", passive_deletes="all"
    )
