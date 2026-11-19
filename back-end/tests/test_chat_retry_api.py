"""TK-029: Xử lý lỗi timeout/429/mất mạng, giữ tin nhắn đã lưu và cho phép retry."""

import pytest

from app.config import load_settings
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.user_repository import User
from app.services.chat_service import ChatService
from app.services.llm_client import LLMReply
from app.utils.errors import AppError


class ScriptedLLMClient:
    def __init__(self, outcomes):
        self._outcomes = list(outcomes)

    async def generate(self, messages):
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


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
async def test_llm_errors_preserve_user_message_and_allow_retry_without_duplication():
    repo = InMemoryChatRepository(InMemoryCatalogRepository())
    llm = ScriptedLLMClient([
        AppError(504, "LLM_TIMEOUT", "Model phản hồi quá lâu."),
        AppError(429, "LLM_RATE_LIMITED", "Dịch vụ model đang giới hạn yêu cầu."),
        AppError(502, "LLM_UNAVAILABLE", "Chưa thể kết nối với model."),
        LLMReply(content="Gợi ý thành công sau khi thử lại.", token_count=18),
    ])
    service = ChatService(repo, llm, load_settings())
    user = make_user(1)

    session = (await service.create_session(user, 1, None)).session

    # Lần gửi đầu gặp timeout -> tin nhắn user vẫn được lưu
    with pytest.raises(AppError) as timeout_err:
        await service.send_message(user, session.id, "Giải thích phương trình bậc hai")
    assert timeout_err.value.status_code == 504
    assert timeout_err.value.code == "LLM_TIMEOUT"
    assert timeout_err.value.details == {"retryable": True}

    msgs_after_fail = (await service.list_messages(user, session.id, limit=10, offset=0)).messages
    assert len(msgs_after_fail) == 1
    assert msgs_after_fail[0].role == "user"

    # Retry gặp 429 rồi mất mạng -> vẫn không tạo trùng tin nhắn user
    with pytest.raises(AppError) as rate_err:
        await service.retry_last_message(user, session.id)
    assert rate_err.value.status_code == 429
    assert rate_err.value.details == {"retryable": True}

    with pytest.raises(AppError) as net_err:
        await service.retry_last_message(user, session.id)
    assert net_err.value.status_code == 502
    assert net_err.value.details == {"retryable": True}

    # Retry lần tiếp theo thành công, chỉ có đúng 1 tin user và 1 tin assistant
    retried = await service.retry_last_message(user, session.id)
    assert retried.user_message.id == msgs_after_fail[0].id
    assert retried.assistant_message.content == "Gợi ý thành công sau khi thử lại."

    final_msgs = (await service.list_messages(user, session.id, limit=10, offset=0)).messages
    assert [(m.role, m.content) for m in final_msgs] == [
        ("user", "Giải thích phương trình bậc hai"),
        ("assistant", "Gợi ý thành công sau khi thử lại."),
    ]

    # Khi đã có phản hồi assistant, retry bị từ chối 409
    with pytest.raises(AppError) as no_retry_err:
        await service.retry_last_message(user, session.id)
    assert no_retry_err.value.status_code == 409
    assert no_retry_err.value.code == "CHAT_RETRY_NOT_NEEDED"
