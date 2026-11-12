from __future__ import annotations

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Integer, CheckConstraint, ForeignKey, Index, Numeric, String, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.quiz_question import QuizQuestion
    from app.models.topic import Topic
    from app.models.user import User


class QuizDifficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class QuizStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class Quiz(Base):
    __tablename__ = "quizzes"


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
    difficulty: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(
        String(15),
        nullable=False,
        default=QuizStatus.IN_PROGRESS.value,
        server_default=text("'in_progress'"),
    )
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    __table_args__ = (
        CheckConstraint("difficulty IN ('easy', 'medium', 'hard')", name="ck_quizzes_difficulty"),
        CheckConstraint("status IN ('in_progress', 'completed')", name="ck_quizzes_status"),
        CheckConstraint("score BETWEEN 0 AND 100", name="ck_quizzes_score"),
        Index("ix_quizzes_user_completed_at", user_id, completed_at.desc()),
        {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_as_cs",
        },
    )

    user: Mapped[User] = relationship("User", back_populates="quizzes")
    topic: Mapped[Topic] = relationship("Topic", back_populates="quizzes")
    questions: Mapped[list[QuizQuestion]] = relationship(
        "QuizQuestion", back_populates="quiz", cascade="all, delete-orphan", passive_deletes=True
    )
