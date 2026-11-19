"""TK-074: Cập nhật feedback (-1/1) trên cùng tin nhắn assistant, không tạo bản ghi mới."""

import pytest

from app.config import load_settings
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.user_repository import User
from app.services.chat_service import ChatService
from app.services.llm_client import LLMReply
from app.utils.errors import AppError


class FakeLLMClient:
    async def generate(self, messages):
        return LLMReply(content="Gợi ý: Hãy thử rút gọn biểu thức trước.", token_count=20)


def make_user(user_id: int) -> User:
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
async def test_update_message_feedback_mutates_in_place_without_creating_new_record():
    catalog = InMemoryCatalogRepository()
    repo = InMemoryChatRepository(catalog)
    service = ChatService(repo, FakeLLMClient(), load_settings())
    owner = make_user(1)
    other = make_user(2)

    session = (await service.create_session(owner, 1, None)).session
    reply = await service.send_message(owner, session.id, "Giải giúp mình bài này")
    user_msg_id = reply.user_message.id
    assistant_msg_id = reply.assistant_message.id

    initial_count = len(repo._messages)
    assert initial_count == 2

    first = await service.update_message_feedback(owner, assistant_msg_id, 1)
    assert first.message.id == assistant_msg_id
    assert first.message.feedback == 1
    assert len(repo._messages) == initial_count

    switched = await service.update_message_feedback(owner, assistant_msg_id, -1)
    assert switched.message.id == assistant_msg_id
    assert switched.message.feedback == -1
    assert len(repo._messages) == initial_count

    with pytest.raises(AppError) as user_msg_err:
        await service.update_message_feedback(owner, user_msg_id, 1)
    assert user_msg_err.value.status_code == 409
    assert user_msg_err.value.code == "FEEDBACK_ASSISTANT_ONLY"

    with pytest.raises(AppError) as other_user_err:
        await service.update_message_feedback(other, assistant_msg_id, 1)
    assert other_user_err.value.status_code == 404
    assert other_user_err.value.code == "CHAT_MESSAGE_NOT_FOUND"
