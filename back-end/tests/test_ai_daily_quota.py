"""TK-075: Giới hạn mặc định 30 yêu cầu AI thành công/ngày/tài khoản."""

from dataclasses import replace

import pytest

from app.config import load_settings
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.user_repository import User
from app.services.chat_service import ChatService
from app.services.llm_client import LLMReply
from app.services.quota_service import DEFAULT_DAILY_AI_LIMIT, QuotaService
from app.utils.errors import AppError


class FlakyLLMClient:
    def __init__(self) -> None:
        self.calls = 0
        self.should_fail = False

    async def generate(self, messages):
        self.calls += 1
        if self.should_fail:
            raise AppError(503, "LLM_UNAVAILABLE", "Dịch vụ AI tạm gián đoạn.")
        return LLMReply(content="Gợi ý học tập.", token_count=15)


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


def test_default_daily_limit_is_30():
    assert DEFAULT_DAILY_AI_LIMIT == 30


@pytest.mark.anyio
async def test_daily_quota_counts_only_successful_ai_replies_and_isolates_users():
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    catalog.add_topic(subject_id, "Đại số", "Phương trình bậc hai")
    repo = InMemoryChatRepository(catalog)
    llm = FlakyLLMClient()
    service = ChatService(repo, llm, load_settings(), daily_ai_limit=2)
    quota = QuotaService(repo, daily_limit=2)

    user_a = make_user(1)
    user_b = make_user(2)
    session_a = (await service.create_session(user_a, 1, None)).session
    session_b = (await service.create_session(user_b, 1, None)).session

    # Lỗi AI không được tính vào hạn mức
    llm.should_fail = True
    with pytest.raises(AppError) as fail_err:
        await service.send_message(user_a, session_a.id, "Câu hỏi 1")
    assert fail_err.value.status_code == 503
    assert (await quota.get_quota_status(user_a.id)).used_today == 0

    # 2 lượt thành công dùng hết hạn mức của user A
    llm.should_fail = False
    await service.send_message(user_a, session_a.id, "Câu hỏi 2")
    await service.send_message(user_a, session_a.id, "Câu hỏi 3")
    status_a = await quota.get_quota_status(user_a.id)
    assert status_a.used_today == 2
    assert status_a.remaining == 0

    # Lượt thứ 3 của user A bị chặn 429 và không gọi LLM
    calls_before = llm.calls
    with pytest.raises(AppError) as quota_err:
        await service.send_message(user_a, session_a.id, "Câu hỏi 4")
    assert quota_err.value.status_code == 429
    assert quota_err.value.code == "AI_QUOTA_EXCEEDED"
    assert llm.calls == calls_before

    # User B vẫn còn nguyên hạn mức
    reply_b = await service.send_message(user_b, session_b.id, "Câu hỏi của user B")
    assert reply_b.assistant_message.role == "assistant"
    assert (await quota.get_quota_status(user_b.id)).remaining == 1

    # Tin nhắn của ngày cũ không tính vào hạn mức hôm nay
    for msg_id, msg in list(repo._messages.items()):
        if msg.session_id == session_a.id and msg.role == "assistant":
            repo._messages[msg_id] = replace(msg, created_at="2020-01-01T00:00:00.000000Z")
    assert (await quota.get_quota_status(user_a.id)).remaining == 2
