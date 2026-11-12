from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Integer, Boolean, CHAR, CheckConstraint, ForeignKey, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.quiz_question import QuizQuestion


class QuizAnswer(Base):
    __tablename__ = "quiz_answers"
    __table_args__ = (
        UniqueConstraint("question_id", name="uq_quiz_answers_question_id"),
        CheckConstraint("user_answer IN ('A', 'B', 'C', 'D')", name="ck_quiz_answers_user_answer"),
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
    question_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("quiz_questions.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_answer: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    is_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)")
    )

    question: Mapped[QuizQuestion] = relationship("QuizQuestion", back_populates="answer")
