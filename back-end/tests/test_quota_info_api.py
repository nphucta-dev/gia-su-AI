"""TK-077: API thông tin quota trả remaining và next_reset_at rõ ràng."""

from datetime import datetime, timezone

import pytest

from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.user_repository import User
from app.services.quota_service import QuotaService


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
async def test_get_quota_returns_remaining_and_next_reset_at():
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    catalog.add_topic(subject_id, "Đại số", "Phương trình bậc hai")
    repo = InMemoryChatRepository(catalog)
    service = QuotaService(repo, daily_limit=30)
    user = make_user(1)

    now = datetime(2026, 11, 19, 14, 30, 0, tzinfo=timezone.utc)
    initial = (await service.get_quota(user, now=now)).quota
    assert initial.daily_limit == 30
    assert initial.used_today == 0
    assert initial.remaining == 30
    assert initial.next_reset_at == "2026-11-20T00:00:00.000000Z"

    session = await repo.create_session(user.id, 1, None)
    u_msg = await repo.append_user_message(user.id, session.id, "Hỏi 1")
    await repo.append_assistant_message(user.id, session.id, "Đáp 1", token_count=10, expected_last_id=u_msg.id)

    after = (await service.get_quota(user, now=datetime.now(timezone.utc))).quota
    assert after.used_today == 1
    assert after.remaining == 29
    assert after.next_reset_at.endswith("T00:00:00.000000Z")
