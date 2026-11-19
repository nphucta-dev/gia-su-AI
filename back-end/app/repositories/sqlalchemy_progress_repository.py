"""Every progress query filters by the current account inside MySQL."""

import asyncio
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.learning_progress import LearningProgress
from app.repositories.chat_repository import utc_timestamp
from app.repositories.progress_repository import ProgressRecord


def update_progress_in_session(
    db: Session,
    *,
    user_id: int,
    topic_id: int,
    correct_count: int,
    total_count: int,
    studied_at: datetime | None = None,
) -> LearningProgress:
    """Cộng dồn thống kê học (total_quizzes, correct_count, total_count) trong cùng transaction."""
    if correct_count < 0 or total_count <= 0 or correct_count > total_count:
        raise ValueError("Invalid quiz statistics counts.")
    now = studied_at if studied_at is not None else db.scalar(select(func.utc_timestamp(6)))
    row = db.scalar(
        select(LearningProgress)
        .where(LearningProgress.user_id == user_id, LearningProgress.topic_id == topic_id)
        .with_for_update()
    )
    if row is None:
        new_correct = correct_count
        new_total = total_count
        mastery = (Decimal(new_correct) * Decimal("100") / Decimal(new_total)).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        row = LearningProgress(
            user_id=user_id,
            topic_id=topic_id,
            total_quizzes=1,
            correct_count=new_correct,
            total_count=new_total,
            mastery_percent=mastery,
            last_studied_at=now,
        )
        db.add(row)
        db.flush()
        return row

    row.total_quizzes += 1
    row.correct_count += correct_count
    row.total_count += total_count
    row.mastery_percent = (Decimal(row.correct_count) * Decimal("100") / Decimal(row.total_count)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )
    row.last_studied_at = now
    db.flush()
    return row


class SqlAlchemyProgressRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def find_progress(self, user_id: int, progress_id: int) -> ProgressRecord | None:
        return await asyncio.to_thread(self._find_progress, user_id, progress_id)

    async def list_progress(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]:
        return await asyncio.to_thread(self._list_progress, user_id, limit=limit, offset=offset)

    async def record_completed_quiz(
        self,
        user_id: int,
        topic_id: int,
        *,
        correct_count: int,
        total_count: int,
        studied_at: datetime | None = None,
    ) -> ProgressRecord:
        return await asyncio.to_thread(
            self._record_completed_quiz,
            user_id,
            topic_id,
            correct_count=correct_count,
            total_count=total_count,
            studied_at=studied_at,
        )

    @staticmethod
    def _record(row: LearningProgress) -> ProgressRecord:
        return ProgressRecord(
            id=row.id, user_id=row.user_id, topic_id=row.topic_id,
            total_quizzes=row.total_quizzes, correct_count=row.correct_count,
            total_count=row.total_count, mastery_percent=row.mastery_percent,
            last_studied_at=utc_timestamp(row.last_studied_at) if row.last_studied_at is not None else None,
        )

    def _find_progress(self, user_id: int, progress_id: int) -> ProgressRecord | None:
        with self._sessions() as db:
            row = db.scalar(select(LearningProgress).where(
                LearningProgress.user_id == user_id, LearningProgress.id == progress_id,
            ))
            return self._record(row) if row is not None else None

    def _list_progress(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]:
        with self._sessions() as db:
            rows = db.scalars(
                select(LearningProgress).where(LearningProgress.user_id == user_id)
                .order_by(LearningProgress.last_studied_at.desc(), LearningProgress.id.desc())
                .offset(offset).limit(limit)
            )
            return [self._record(row) for row in rows]

    def _record_completed_quiz(
        self,
        user_id: int,
        topic_id: int,
        *,
        correct_count: int,
        total_count: int,
        studied_at: datetime | None = None,
    ) -> ProgressRecord:
        with self._sessions.begin() as db:
            row = update_progress_in_session(
                db,
                user_id=user_id,
                topic_id=topic_id,
                correct_count=correct_count,
                total_count=total_count,
                studied_at=studied_at,
            )
            return self._record(row)
