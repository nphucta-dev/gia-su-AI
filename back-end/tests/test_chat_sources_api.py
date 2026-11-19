"""TK-049: API gửi source_refs hợp lệ và ghi rõ khi không có chunk."""

from dataclasses import replace

import pytest

from app.config import load_settings
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.user_repository import User
from app.services.chat_service import ChatService, NO_SOURCE_NOTICE, sanitize_source_refs
from app.services.llm_client import LLMReply
from app.utils.errors import AppError


class FakeLLMClient:
    async def generate(self, messages):
        return LLMReply(content="Gợi ý học tập.", token_count=12)


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


def test_sanitize_source_refs_filters_invalid_and_duplicate_entries():
    raw = [
        {"document_id": 1, "chunk_id": 10, "title": "SGK Toán", "chunk_index": 0, "source_url": "https://example.edu/1"},
        {"document_id": 1, "chunk_id": 10, "title": "Trùng lặp"},
        {"document_id": -1, "chunk_id": 11, "title": "ID âm"},
        {"document_id": 2, "chunk_id": 12, "title": "   "},
        "invalid",
    ]
    cleaned = sanitize_source_refs(raw)
    assert len(cleaned) == 1
    assert cleaned[0].document_id == 1
    assert cleaned[0].chunk_id == 10
    assert cleaned[0].title == "SGK Toán"


@pytest.mark.anyio
async def test_get_message_sources_returns_valid_refs_or_no_source_notice():
    catalog = InMemoryCatalogRepository()
    repo = InMemoryChatRepository(catalog)
    service = ChatService(repo, FakeLLMClient(), load_settings())
    owner = make_user(1)
    other = make_user(2)

    session = (await service.create_session(owner, 1, None)).session
    reply = await service.send_message(owner, session.id, "Giải thích định lý Vi-ét")
    assistant_id = reply.assistant_message.id

    empty_res = await service.get_message_sources(owner, assistant_id)
    assert empty_res.has_sources is False
    assert empty_res.source_refs == []
    assert empty_res.notice == NO_SOURCE_NOTICE

    repo._messages[assistant_id] = replace(
        repo._messages[assistant_id],
        source_refs=[
            {"document_id": 5, "chunk_id": 21, "title": "Bài giảng Đại số", "chunk_index": 0},
        ],
    )
    filled_res = await service.get_message_sources(owner, assistant_id)
    assert filled_res.has_sources is True
    assert len(filled_res.source_refs) == 1
    assert filled_res.source_refs[0].document_id == 5
    assert filled_res.notice is None

    with pytest.raises(AppError) as err:
        await service.get_message_sources(other, assistant_id)
    assert err.value.status_code == 404
