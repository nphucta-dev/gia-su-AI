"""Owner-scoped progress reads; creation and scoring belong to the quiz workflow."""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol


@dataclass(frozen=True)
class ProgressRecord:
    id: int
    user_id: int
    topic_id: int
    total_quizzes: int
    correct_count: int
    total_count: int
    mastery_percent: Decimal
    last_studied_at: str | None


class ProgressRepository(Protocol):
    async def find_progress(self, user_id: int, progress_id: int) -> ProgressRecord | None: ...

    async def list_progress(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]: ...

    async def list_review_topics(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]: ...


class InMemoryProgressRepository:
    def __init__(self, records: Iterable[ProgressRecord] = ()) -> None:
        self._records = {record.id: record for record in records}

    async def find_progress(self, user_id: int, progress_id: int) -> ProgressRecord | None:
        record = self._records.get(progress_id)
        return record if record is not None and record.user_id == user_id else None

    async def list_progress(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]:
        owned = (record for record in self._records.values() if record.user_id == user_id)
        records = sorted(owned, key=lambda record: (record.last_studied_at or "", record.id), reverse=True)
        return records[offset:offset + limit]

    async def list_review_topics(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]:
        """TK-067: Xếp chủ đề cần ôn của user theo mastery_percent tăng dần."""
        owned = (record for record in self._records.values() if record.user_id == user_id)
        records = sorted(owned, key=lambda record: (record.mastery_percent, record.last_studied_at or "", record.id))
        return records[offset:offset + limit]
