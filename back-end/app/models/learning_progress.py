from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, ForeignKey, Integer, Numeric, text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.types import UTCDateTime

if TYPE_CHECKING:
    from app.models.topic import Topic
    from app.models.user import User


class LearningProgress(Base):
    __tablename__ = "learning_progress"
    __table_args__ = (
        UniqueConstraint("user_id", "topic_id", name="uq_learning_progress_user_id_topic_id"),
        CheckConstraint("total_quizzes >= 0", name="ck_learning_progress_total_quizzes"),
        CheckConstraint("correct_count >= 0", name="ck_learning_progress_correct_count"),
        CheckConstraint("total_count >= 0", name="ck_learning_progress_total_count"),
        CheckConstraint(
            "correct_count <= total_count", name="ck_learning_progress_correct_count_total_count"
        ),
        CheckConstraint(
            "mastery_percent BETWEEN 0 AND 100", name="ck_learning_progress_mastery_percent"
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
    total_quizzes: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    correct_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    total_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    mastery_percent: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), nullable=False, default=Decimal("0.00"), server_default=text("0.00")
    )
    last_studied_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)

    user: Mapped[User] = relationship("User", back_populates="learning_progress")
    topic: Mapped[Topic] = relationship("Topic", back_populates="learning_progress")
