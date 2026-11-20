"""Owner-scoped progress reads and completed-quiz learning statistics updates."""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Protocol


def _utc_iso(value: datetime | None) -> str:
    dt = value if value is not None else datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _compute_mastery(correct_count: int, total_count: int) -> Decimal:
    if total_count <= 0:
        return Decimal("0.00")
    return (Decimal(correct_count) * Decimal("100") / Decimal(total_count)).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP,
    )


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

    async def record_completed_quiz(
        self,
        user_id: int,
        topic_id: int,
        *,
        correct_count: int,
        total_count: int,
        studied_at: datetime | None = None,
    ) -> ProgressRecord: ...

    async def list_review_topics(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]: ...


class InMemoryProgressRepository:
    def __init__(self, records: Iterable[ProgressRecord] = ()) -> None:
        self._records = {record.id: record for record in records}
        self._next_id = max(self._records, default=0) + 1

    async def find_progress(self, user_id: int, progress_id: int) -> ProgressRecord | None:
        record = self._records.get(progress_id)
        return record if record is not None and record.user_id == user_id else None

    async def list_progress(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]:
        owned = (record for record in self._records.values() if record.user_id == user_id)
        records = sorted(owned, key=lambda record: (record.last_studied_at or "", record.id), reverse=True)
        return records[offset:offset + limit]

    async def record_completed_quiz(
        self,
        user_id: int,
        topic_id: int,
        *,
        correct_count: int,
        total_count: int,
        studied_at: datetime | None = None,
    ) -> ProgressRecord:
        if correct_count < 0 or total_count <= 0 or correct_count > total_count:
            raise ValueError("Invalid quiz statistics counts.")
        timestamp = _utc_iso(studied_at)
        existing = next(
            (r for r in self._records.values() if r.user_id == user_id and r.topic_id == topic_id),
            None,
        )
        if existing is None:
            record = ProgressRecord(
                id=self._next_id,
                user_id=user_id,
                topic_id=topic_id,
                total_quizzes=1,
                correct_count=correct_count,
                total_count=total_count,
                mastery_percent=_compute_mastery(correct_count, total_count),
                last_studied_at=timestamp,
            )
            self._records[record.id] = record
            self._next_id += 1
            return record

        new_correct = existing.correct_count + correct_count
        new_total = existing.total_count + total_count
        updated = replace(
            existing,
            total_quizzes=existing.total_quizzes + 1,
            correct_count=new_correct,
            total_count=new_total,
            mastery_percent=_compute_mastery(new_correct, new_total),
            last_studied_at=timestamp,
        )
        self._records[updated.id] = updated
        return updated

    async def list_review_topics(self, user_id: int, *, limit: int, offset: int) -> list[ProgressRecord]:
        """TK-067: Xếp chủ đề cần ôn của user theo mastery_percent tăng dần."""
        owned = (record for record in self._records.values() if record.user_id == user_id)
        records = sorted(owned, key=lambda record: (record.mastery_percent, record.last_studied_at or "", record.id))
        return records[offset:offset + limit]
