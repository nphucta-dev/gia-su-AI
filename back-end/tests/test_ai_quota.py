"""Quota counts successes only and preserves independent reads during exhaustion."""

from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.repositories.ai_quota_repository import InMemoryAiQuotaRepository
from app.repositories.chat_repository import ChatMessageRecord
from app.services.ai_quota import AiQuotaService
from app.utils.errors import AppError
from test_chat_repository import chat_repository

pytestmark = pytest.mark.anyio


async def test_quota_uses_utc_calendar_and_counts_only_the_current_owner_and_day():
    chat, _, _, topic = chat_repository()
    own = await chat.create_session(1, topic)
    other = await chat.create_session(2, topic)
    dates = [(own.id, "2026-11-19T23:59:59Z"), (own.id, "2026-11-20T00:00:00Z"),
             (own.id, "2026-11-21T00:00:00Z"), (other.id, "2026-11-20T00:00:00Z")]
    for number, (session_id, stamp) in enumerate(dates, start=1):
        chat._messages[number] = ChatMessageRecord(number, session_id, "assistant", "Gợi ý", stamp)
    quota = AiQuotaService(InMemoryAiQuotaRepository(chat), clock=lambda: datetime(2026, 11, 20, 12, tzinfo=timezone.utc))
    state = await quota.get_quota(1)
    assert state.used == 1 and state.remaining == 29 and state.next_reset_at == "2026-11-21T00:00:00.000000Z"


async def test_body_database_error_is_not_mislabeled_as_quota_error_and_guard_releases():
    chat, _, _, _ = chat_repository()
    quota = AiQuotaService(InMemoryAiQuotaRepository(chat))
    with pytest.raises(SQLAlchemyError):
        async with quota.generation(1):
            raise SQLAlchemyError("simulated write failure")
    async with quota.generation(1):
        pass


async def test_count_outage_releases_admission_guard_and_uses_safe_error():
    chat, _, _, _ = chat_repository()
    repository = InMemoryAiQuotaRepository(chat)
    original = repository.count_successes
    async def fail(*args):
        raise SQLAlchemyError("private db host")
    repository.count_successes = fail
    quota = AiQuotaService(repository)
    with pytest.raises(AppError) as caught:
        async with quota.generation(1):
            pytest.fail("Must not call model when usage cannot be checked")
    assert caught.value.code == "AI_QUOTA_UNAVAILABLE" and "private" not in caught.value.message
    repository.count_successes = original
    async with quota.generation(1):
        pass
