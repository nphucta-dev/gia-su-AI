"""TK-062: Cộng total_quizzes, correct_count, total_count khi quiz hoàn tất."""

from decimal import Decimal

import pytest

from app.repositories.progress_repository import InMemoryProgressRepository
from app.repositories.user_repository import User
from app.services.progress_service import ProgressService
from app.utils.errors import AppError


def make_user(user_id: int = 1) -> User:
    return User(
        id=user_id,
        email=f"user{user_id}@example.com",
        name=f"User {user_id}",
        password_hash="hash",
        role="LEARNER",
        is_active=True,
        birth_year=2002,
    )


@pytest.mark.anyio
async def test_record_completed_quiz_accumulates_stats_across_quizzes():
    repo = InMemoryProgressRepository()
    service = ProgressService(repo)
    user = make_user(1)

    first = await service.record_completed_quiz(
        user, topic_id=10, quiz_status="completed", correct_count=3, total_count=5,
    )
    assert first.progress.total_quizzes == 1
    assert first.progress.correct_count == 3
    assert first.progress.total_count == 5
    assert first.progress.mastery_percent == Decimal("60.00")
    assert first.progress.last_studied_at is not None

    second = await service.record_completed_quiz(
        user, topic_id=10, quiz_status="completed", correct_count=4, total_count=5,
    )
    assert second.progress.id == first.progress.id
    assert second.progress.total_quizzes == 2
    assert second.progress.correct_count == 7
    assert second.progress.total_count == 10
    assert second.progress.mastery_percent == Decimal("70.00")


@pytest.mark.anyio
async def test_record_completed_quiz_rejects_in_progress_and_invalid_counts():
    repo = InMemoryProgressRepository()
    service = ProgressService(repo)
    user = make_user(1)

    with pytest.raises(AppError) as exc_info:
        await service.record_completed_quiz(
            user, topic_id=10, quiz_status="in_progress", correct_count=3, total_count=5,
        )
    assert exc_info.value.status_code == 409
    assert exc_info.value.code == "QUIZ_NOT_COMPLETED"

    with pytest.raises(AppError) as invalid_exc:
        await service.record_completed_quiz(
            user, topic_id=10, quiz_status="completed", correct_count=6, total_count=5,
        )
    assert invalid_exc.value.status_code == 422
    assert invalid_exc.value.code == "VALIDATION_ERROR"

    listed = await service.list_progress(user, limit=10, offset=0)
    assert listed.progress == []
