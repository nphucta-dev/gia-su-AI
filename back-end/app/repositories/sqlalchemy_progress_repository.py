"""Every progress query filters by the current account inside MySQL."""

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.learning_progress import LearningProgress
from app.repositories.chat_repository import utc_timestamp
from app.repositories.progress_repository import ProgressRecord


class SqlAlchemyProgressRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def find_progress(self, user_id: int, progress_id: int) -> ProgressRecord | None:
        return await asyncio.to_thread(self._find_progress, user_id, progress_id)

    async def list_progress(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]:
        return await asyncio.to_thread(self._list_progress, user_id, limit=limit, offset=offset)

    async def list_review_topics(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]:
        return await asyncio.to_thread(self._list_review_topics, user_id, limit=limit, offset=offset)

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

    def _list_review_topics(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]:
        with self._sessions() as db:
            rows = db.scalars(
                select(LearningProgress).where(LearningProgress.user_id == user_id)
                .order_by(
                    LearningProgress.mastery_percent.asc(),
                    LearningProgress.last_studied_at.asc(),
                    LearningProgress.id.asc(),
                )
                .offset(offset).limit(limit)
            )
            return [self._record(row) for row in rows]
