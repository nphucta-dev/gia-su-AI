"""Dữ liệu phiên/tin nhắn và kho trong bộ nhớ dùng cho kiểm thử chat."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from typing import Protocol

from app.repositories.catalog_repository import InMemoryCatalogRepository


def utc_timestamp(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class ChatSessionRecord:
    id: int
    user_id: int
    topic_id: int
    title: str | None
    created_at: str
    updated_at: str
    topic_name: str
    subject_name: str
    grade_level: str
    chapter_name: str
    topic_description: str | None
    topic_active: bool
    subject_active: bool


@dataclass(frozen=True)
class ChatMessageRecord:
    id: int
    session_id: int
    role: str
    content: str
    created_at: str
    hint_level: int | None = None
    is_full_solution: bool = False
    token_count: int | None = None


# Tên ngắn dùng được ở các service không cần nhắc lại tiền tố Chat.
SessionRecord = ChatSessionRecord
MessageRecord = ChatMessageRecord


class ChatChangedError(Exception):
    """Phiên đã có tin mới trong lúc phản hồi AI đang được tạo."""


class ChatRepository(Protocol):
    async def create_session(self, user_id: int, topic_id: int, title: str | None = None) -> ChatSessionRecord | None: ...

    async def find_session(self, user_id: int, session_id: int) -> ChatSessionRecord | None: ...

    async def list_sessions(self, user_id: int, *, limit: int, offset: int) -> list[ChatSessionRecord]: ...

    async def list_messages(self, user_id: int, session_id: int, *, limit: int, offset: int) -> list[ChatMessageRecord]: ...

    async def recent_messages(self, user_id: int, session_id: int, *, limit: int = 12) -> list[ChatMessageRecord]: ...

    async def append_user_message(self, user_id: int, session_id: int, content: str) -> ChatMessageRecord | None: ...

    async def append_assistant_message(
        self, user_id: int, session_id: int, content: str, *, hint_level: int,
        token_count: int | None, expected_last_id: int,
    ) -> ChatMessageRecord | None: ...


class InMemoryChatRepository:
    def __init__(self, catalog_repository: InMemoryCatalogRepository | None = None) -> None:
        self._catalog = catalog_repository if catalog_repository is not None else InMemoryCatalogRepository()
        self._sessions: dict[int, ChatSessionRecord] = {}
        self._messages: dict[int, ChatMessageRecord] = {}
        self._next_session_id = 1
        self._next_message_id = 1
        self._last_timestamp: datetime | None = None

    def _timestamp(self) -> str:
        now = datetime.now(timezone.utc)
        # Đồng hồ Windows có thể trả cùng thời điểm cho nhiều thao tác liên tiếp.
        # Thứ tự hoạt động trong kho kiểm thử vẫn phải giữ được các lần ghi mới.
        if self._last_timestamp is not None and now <= self._last_timestamp:
            now = self._last_timestamp + timedelta(microseconds=1)
        self._last_timestamp = now
        return utc_timestamp(now)

    def _topic_context(self, topic_id: int) -> dict | None:
        topic = self._catalog._topics.get(topic_id)
        subject = self._catalog._subjects.get(topic["subject_id"]) if topic else None
        if topic is None or subject is None:
            return None
        return {
            "topic_name": topic["name"], "subject_name": subject["name"],
            "grade_level": subject["grade_level"], "chapter_name": topic["chapter_name"],
            "topic_description": topic["description"], "topic_active": topic["is_active"],
            "subject_active": subject["is_active"],
        }

    def _find_session(self, user_id: int, session_id: int) -> ChatSessionRecord | None:
        session = self._sessions.get(session_id)
        if session is None or session.user_id != user_id:
            return None
        context = self._topic_context(session.topic_id)
        return replace(session, **context) if context is not None else None

    async def create_session(self, user_id: int, topic_id: int, title: str | None = None) -> ChatSessionRecord | None:
        context = self._topic_context(topic_id)
        if context is None or not context["topic_active"] or not context["subject_active"]:
            return None
        now = self._timestamp()
        record = ChatSessionRecord(
            id=self._next_session_id, user_id=user_id, topic_id=topic_id, title=title,
            created_at=now, updated_at=now, **context,
        )
        self._sessions[record.id] = record
        self._next_session_id += 1
        return record

    async def find_session(self, user_id: int, session_id: int) -> ChatSessionRecord | None:
        return self._find_session(user_id, session_id)

    async def list_sessions(self, user_id: int, *, limit: int, offset: int) -> list[ChatSessionRecord]:
        records = [record for key in self._sessions if (record := self._find_session(user_id, key)) is not None]
        records.sort(key=lambda record: (record.updated_at, record.id), reverse=True)
        return records[offset:offset + limit]

    def _owned_messages(self, user_id: int, session_id: int) -> list[ChatMessageRecord]:
        if self._find_session(user_id, session_id) is None:
            return []
        return sorted((item for item in self._messages.values() if item.session_id == session_id), key=lambda item: item.id)

    async def list_messages(self, user_id: int, session_id: int, *, limit: int, offset: int) -> list[ChatMessageRecord]:
        return self._owned_messages(user_id, session_id)[offset:offset + limit]

    async def recent_messages(self, user_id: int, session_id: int, *, limit: int = 12) -> list[ChatMessageRecord]:
        if limit <= 0:
            return []
        return self._owned_messages(user_id, session_id)[-limit:]

    def _append(
        self, session: ChatSessionRecord, content: str, *, role: str,
        hint_level: int | None = None, token_count: int | None = None,
    ) -> ChatMessageRecord:
        now = self._timestamp()
        message = ChatMessageRecord(
            id=self._next_message_id, session_id=session.id, role=role, content=content,
            created_at=now, hint_level=hint_level, token_count=token_count,
        )
        title = session.title
        if title is None and role == "user":
            title = " ".join(content.split())[:120] or None
        self._messages[message.id] = message
        self._next_message_id += 1
        self._sessions[session.id] = replace(session, updated_at=now, title=title)
        return message

    async def append_user_message(self, user_id: int, session_id: int, content: str) -> ChatMessageRecord | None:
        session = self._find_session(user_id, session_id)
        return self._append(session, content, role="user") if session is not None else None

    async def append_assistant_message(
        self, user_id: int, session_id: int, content: str, *, hint_level: int,
        token_count: int | None, expected_last_id: int,
    ) -> ChatMessageRecord | None:
        session = self._find_session(user_id, session_id)
        if session is None:
            return None
        messages = self._owned_messages(user_id, session_id)
        last_id = messages[-1].id if messages else 0
        if last_id != expected_last_id:
            raise ChatChangedError()
        return self._append(session, content, role="assistant", hint_level=hint_level, token_count=token_count)
