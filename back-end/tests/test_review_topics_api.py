"""TK-067: API gợi ý chủ đề ôn xếp theo mastery_percent tăng dần."""

from decimal import Decimal

import pytest

from app.repositories.progress_repository import InMemoryProgressRepository, ProgressRecord
from app.repositories.user_repository import User
from app.services.progress_service import ProgressService


def make_user(user_id: int) -> User:
    return User(
        id=user_id,
        email=f"user{user_id}@example.com",
        name=f"User {user_id}",
        password_hash="hash",
        role="LEARNER",
        is_active=True,
        birth_year=2002,
        created_at="2026-11-18T00:00:00Z",
    )


@pytest.mark.anyio
async def test_list_review_topics_orders_by_mastery_ascending_and_scopes_to_owner():
    repo = InMemoryProgressRepository([
        ProgressRecord(1, user_id=1, topic_id=101, total_quizzes=2, correct_count=8, total_count=10, mastery_percent=Decimal("80.00"), last_studied_at="2026-11-18T10:00:00Z"),
        ProgressRecord(2, user_id=1, topic_id=102, total_quizzes=1, correct_count=2, total_count=5, mastery_percent=Decimal("40.00"), last_studied_at="2026-11-18T11:00:00Z"),
        ProgressRecord(3, user_id=1, topic_id=103, total_quizzes=1, correct_count=3, total_count=5, mastery_percent=Decimal("60.00"), last_studied_at="2026-11-18T09:00:00Z"),
        ProgressRecord(4, user_id=2, topic_id=104, total_quizzes=1, correct_count=0, total_count=5, mastery_percent=Decimal("0.00"), last_studied_at="2026-11-18T08:00:00Z"),
    ])
    service = ProgressService(repo)

    res = await service.list_review_topics(make_user(1), limit=10, offset=0)
    assert [(item.topic_id, item.mastery_percent) for item in res.topics] == [
        (102, 40.0),
        (103, 60.0),
        (101, 80.0),
    ]
    assert res.has_more is False

    paged = await service.list_review_topics(make_user(1), limit=2, offset=0)
    assert [item.topic_id for item in paged.topics] == [102, 103]
    assert paged.has_more is True
