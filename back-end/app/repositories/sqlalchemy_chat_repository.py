"""Kho chat MySQL: lưu tin bằng transaction ngắn, không giữ khóa lúc gọi model."""

from __future__ import annotations

import asyncio
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.subject import Subject
from app.models.topic import Topic
from app.repositories.chat_repository import ChatChangedError, ChatMessageRecord, ChatSessionRecord, utc_timestamp


class SqlAlchemyChatRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def create_session(self, user_id: int, topic_id: int, title: str | None = None) -> ChatSessionRecord | None:
        return await asyncio.to_thread(self._create_session, user_id, topic_id, title)

    async def find_session(self, user_id: int, session_id: int) -> ChatSessionRecord | None:
        return await asyncio.to_thread(self._find_session, user_id, session_id)

    async def list_sessions(self, user_id: int, *, limit: int, offset: int) -> list[ChatSessionRecord]:
        return await asyncio.to_thread(self._list_sessions, user_id, limit=limit, offset=offset)

    async def list_messages(self, user_id: int, session_id: int, *, limit: int, offset: int) -> list[ChatMessageRecord]:
        return await asyncio.to_thread(self._list_messages, user_id, session_id, limit=limit, offset=offset)

    async def recent_messages(self, user_id: int, session_id: int, *, limit: int = 12) -> list[ChatMessageRecord]:
        return await asyncio.to_thread(self._recent_messages, user_id, session_id, limit=limit)

    async def append_user_message(self, user_id: int, session_id: int, content: str) -> ChatMessageRecord | None:
        return await asyncio.to_thread(self._append_message, user_id, session_id, content, role="user")

    async def append_assistant_message(
        self, user_id: int, session_id: int, content: str, *, hint_level: int,
        token_count: int | None, expected_last_id: int,
    ) -> ChatMessageRecord | None:
        return await asyncio.to_thread(
            self._append_message, user_id, session_id, content, role="assistant",
            hint_level=hint_level, token_count=token_count, expected_last_id=expected_last_id,
        )

    @staticmethod
    def _session_query(user_id: int):
        return (
            select(ChatSession, Topic, Subject)
            .join(Topic, Topic.id == ChatSession.topic_id)
            .join(Subject, Subject.id == Topic.subject_id)
            .where(ChatSession.user_id == user_id)
        )

    @staticmethod
    def _message_query(user_id: int, session_id: int):
        return (
            select(ChatMessage)
            .join(ChatSession, ChatSession.id == ChatMessage.session_id)
            .where(ChatSession.user_id == user_id, ChatSession.id == session_id)
        )

    @staticmethod
    def _session_record(session: ChatSession, topic: Topic, subject: Subject) -> ChatSessionRecord:
        return ChatSessionRecord(
            id=session.id, user_id=session.user_id, topic_id=session.topic_id, title=session.title,
            created_at=utc_timestamp(session.created_at), updated_at=utc_timestamp(session.updated_at),
            topic_name=topic.name, subject_name=subject.name, grade_level=subject.grade_level,
            chapter_name=topic.chapter_name, topic_description=topic.description,
            topic_active=topic.is_active, subject_active=subject.is_active,
        )

    @staticmethod
    def _message_record(message: ChatMessage) -> ChatMessageRecord:
        return ChatMessageRecord(
            id=message.id, session_id=message.session_id, role=message.role, content=message.content,
            created_at=utc_timestamp(message.created_at), hint_level=message.hint_level,
            is_full_solution=message.is_full_solution, token_count=message.token_count,
        )

    def _create_session(self, user_id: int, topic_id: int, title: str | None) -> ChatSessionRecord | None:
        with self._sessions.begin() as db:
            row = db.execute(
                select(Topic, Subject).join(Subject, Subject.id == Topic.subject_id)
                .where(Topic.id == topic_id).with_for_update()
            ).first()
            if row is None:
                return None
            topic, subject = row
            if not topic.is_active or not subject.is_active:
                return None
            now = db.scalar(select(func.utc_timestamp(6)))
            session = ChatSession(user_id=user_id, topic_id=topic_id, title=title, created_at=now, updated_at=now)
            db.add(session)
            db.flush()
            return self._session_record(session, topic, subject)

    def _find_session(self, user_id: int, session_id: int) -> ChatSessionRecord | None:
        with self._sessions() as db:
            row = db.execute(self._session_query(user_id).where(ChatSession.id == session_id)).first()
            return self._session_record(*row) if row is not None else None

    def _list_sessions(self, user_id: int, *, limit: int, offset: int) -> list[ChatSessionRecord]:
        with self._sessions() as db:
            rows = db.execute(
                self._session_query(user_id)
                .order_by(ChatSession.updated_at.desc(), ChatSession.id.desc()).offset(offset).limit(limit)
            )
            return [self._session_record(*row) for row in rows]

    def _list_messages(self, user_id: int, session_id: int, *, limit: int, offset: int) -> list[ChatMessageRecord]:
        with self._sessions() as db:
            rows = db.scalars(self._message_query(user_id, session_id).order_by(ChatMessage.id).offset(offset).limit(limit))
            return [self._message_record(message) for message in rows]

    def _recent_messages(self, user_id: int, session_id: int, *, limit: int) -> list[ChatMessageRecord]:
        with self._sessions() as db:
            rows = list(db.scalars(self._message_query(user_id, session_id).order_by(ChatMessage.id.desc()).limit(limit)))
            return [self._message_record(message) for message in reversed(rows)]

    def _append_message(
        self, user_id: int, session_id: int, content: str, *, role: str,
        hint_level: int | None = None, token_count: int | None = None,
        expected_last_id: int | None = None,
    ) -> ChatMessageRecord | None:
        with self._sessions.begin() as db:
            session = db.scalar(
                select(ChatSession).where(ChatSession.id == session_id, ChatSession.user_id == user_id).with_for_update()
            )
            if session is None:
                return None
            if role == "assistant":
                last_id = db.scalar(select(func.max(ChatMessage.id)).where(ChatMessage.session_id == session_id)) or 0
                if last_id != expected_last_id:
                    raise ChatChangedError()
            now = db.scalar(select(func.utc_timestamp(6)))
            message = ChatMessage(
                session_id=session_id, role=role, content=content, created_at=now,
                hint_level=hint_level, token_count=token_count, is_full_solution=False,
            )
            if session.title is None and role == "user":
                session.title = " ".join(content.split())[:120] or None
            session.updated_at = now
            db.add(message)
            db.flush()
            return self._message_record(message)
