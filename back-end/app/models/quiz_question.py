from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import (
    Integer,
    CHAR,
    CheckConstraint,
    ForeignKey,
    JSON,
    SmallInteger,
    Text,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.quiz import Quiz
    from app.models.quiz_answer import QuizAnswer


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"
    __table_args__ = (
        UniqueConstraint("quiz_id", "position", name="uq_quiz_questions_quiz_id_position"),
        CheckConstraint("position BETWEEN 1 AND 5", name="ck_quiz_questions_position"),
        CheckConstraint(
            "correct_answer IN ('A', 'B', 'C', 'D')", name="ck_quiz_questions_correct_answer"
        ),
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
    quiz_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("quizzes.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    correct_answer: Mapped[str] = mapped_column(CHAR(1), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False)

    quiz: Mapped[Quiz] = relationship("Quiz", back_populates="questions")
    answer: Mapped[QuizAnswer | None] = relationship(
        "QuizAnswer",
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
        uselist=False,
    )
