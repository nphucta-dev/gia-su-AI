"""Kiểm tra thứ tự, phân trang và ghi chat nguyên vẹn bằng kho độc lập."""

import asyncio
from datetime import datetime, timedelta

import pytest

from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import ChatChangedError, InMemoryChatRepository

pytestmark = pytest.mark.anyio


def chat_repository():
    catalog = InMemoryCatalogRepository()
    subject = catalog.add_subject("Toán", "THPT")
    topic = catalog.add_topic(subject, "Đại số", "Phương trình", "Phương trình bậc hai")
    return InMemoryChatRepository(catalog), catalog, subject, topic


async def test_create_session_has_numeric_id_and_only_active_catalog_is_accepted():
    repository, catalog, subject, topic = chat_repository()
    first = await repository.create_session(1, topic)
    second = await repository.create_session(1, topic, "Phiên tự đặt tên")
    assert first.id > 0 and isinstance(first.id, int) and second.id > first.id
    assert first.title is None and second.title == "Phiên tự đặt tên"
    assert first.user_id == 1 and first.topic_id == topic
    assert (first.subject_name, first.topic_name, first.chapter_name, first.grade_level) == (
        "Toán", "Phương trình", "Đại số", "THPT",
    )
    assert datetime.fromisoformat(first.created_at).utcoffset() == timedelta(0)
    catalog._topics[topic]["is_active"] = False
    assert await repository.create_session(1, topic) is None
    catalog._topics[topic]["is_active"] = True
    catalog._subjects[subject]["is_active"] = False
    assert await repository.create_session(1, topic) is None
    assert await repository.create_session(1, 999) is None


async def test_existing_history_remains_available_and_uses_current_catalog_names_and_flags():
    repository, catalog, subject, topic = chat_repository()
    session = await repository.create_session(1, topic)
    message = await repository.append_user_message(1, session.id, "Câu hỏi cũ")
    catalog._subjects[subject].update(name="Toán học", grade_level="THCS", is_active=False)
    catalog._topics[topic].update(name="Phương trình mới", is_active=False)
    current = await repository.find_session(1, session.id)
    assert current.subject_name == "Toán học" and current.grade_level == "THCS"
    assert current.topic_name == "Phương trình mới"
    assert current.subject_active is current.topic_active is False
    assert await repository.list_messages(1, session.id, limit=20, offset=0) == [message]


async def test_sessions_are_filtered_by_user_sorted_by_activity_and_paginated():
    repository, _, _, topic = chat_repository()
    first = await repository.create_session(1, topic)
    second = await repository.create_session(1, topic)
    outsider = await repository.create_session(2, topic)
    message = await repository.append_user_message(1, first.id, "  Câu hỏi\nđầu tiên   ")
    records = await repository.list_sessions(1, limit=20, offset=0)
    assert [record.id for record in records] == [first.id, second.id]
    assert outsider.id not in {record.id for record in records}
    assert records[0].title == "Câu hỏi đầu tiên"
    assert records[0].updated_at == message.created_at
    assert await repository.list_sessions(1, limit=1, offset=1) == [records[1]]
    await repository.append_user_message(1, first.id, "Nội dung sau không đổi tiêu đề")
    assert (await repository.find_session(1, first.id)).title == "Câu hỏi đầu tiên"


async def test_messages_have_chronological_order_and_recent_window_keeps_newest_messages():
    repository, _, _, topic = chat_repository()
    session = await repository.create_session(1, topic)
    other_session = await repository.create_session(1, topic)
    saved = []
    for index in range(16):
        saved.append(await repository.append_user_message(1, session.id, f"Câu hỏi {index}"))
        await repository.append_user_message(1, other_session.id, "Không thuộc phiên được hỏi")
    assert await repository.list_messages(1, session.id, limit=3, offset=4) == saved[4:7]
    assert await repository.recent_messages(1, session.id, limit=12) == saved[-12:]
    assert await repository.recent_messages(1, session.id, limit=0) == []
    assert saved == sorted(saved, key=lambda message: message.id)
    assert all(message.role == "user" and message.hint_level is None for message in saved)


async def test_other_users_cannot_find_read_or_append_to_an_owned_session():
    repository, _, _, topic = chat_repository()
    session = await repository.create_session(1, topic)
    original = await repository.append_user_message(1, session.id, "Riêng tư")
    assert await repository.find_session(2, session.id) is None
    assert await repository.list_messages(2, session.id, limit=20, offset=0) == []
    assert await repository.recent_messages(2, session.id) == []
    assert await repository.append_user_message(2, session.id, "Không được ghi") is None
    assert await repository.append_assistant_message(
        2, session.id, "Không được ghi", hint_level=1, token_count=10, expected_last_id=original.id,
    ) is None
    assert await repository.list_messages(1, session.id, limit=20, offset=0) == [original]
    assert await repository.find_session(1, 999) is None


async def test_stale_generated_reply_does_not_insert_or_touch_session():
    repository, _, _, topic = chat_repository()
    session = await repository.create_session(1, topic)
    first = await repository.append_user_message(1, session.id, "Câu hỏi trước")
    latest = await repository.append_user_message(1, session.id, "Câu hỏi mới")
    before = await repository.find_session(1, session.id)
    with pytest.raises(ChatChangedError):
        await repository.append_assistant_message(
            1, session.id, "Trả lời đã cũ", hint_level=1, token_count=17, expected_last_id=first.id,
        )
    assert await repository.find_session(1, session.id) == before
    reply = await repository.append_assistant_message(
        1, session.id, "Gợi ý đúng lượt", hint_level=1, token_count=17, expected_last_id=latest.id,
    )
    assert reply.role == "assistant" and reply.hint_level == 1 and reply.token_count == 17
    assert reply.is_full_solution is False
    assert (await repository.find_session(1, session.id)).updated_at == reply.created_at
    with pytest.raises(ChatChangedError):
        await repository.append_assistant_message(
            1, session.id, "Không nhân đôi lời gợi ý", hint_level=1, token_count=None, expected_last_id=latest.id,
        )


async def test_concurrent_assistant_writes_accept_only_one_reply_for_the_same_snapshot():
    repository, _, _, topic = chat_repository()
    session = await repository.create_session(1, topic)
    question = await repository.append_user_message(1, session.id, "Câu hỏi")
    results = await asyncio.gather(*[
        repository.append_assistant_message(
            1, session.id, f"Gợi ý {index}", hint_level=1, token_count=None, expected_last_id=question.id,
        ) for index in range(2)
    ], return_exceptions=True)
    assert sum(isinstance(result, ChatChangedError) for result in results) == 1
    assert len(await repository.list_messages(1, session.id, limit=20, offset=0)) == 2
