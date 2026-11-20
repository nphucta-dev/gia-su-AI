"""Per-account model admission, without keeping a row transaction open over HTTP."""

from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from datetime import datetime, timezone
import hashlib
from typing import Protocol

from sqlalchemy import func, select, text
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from app.models.quiz import Quiz
from app.utils.errors import AppError
from app.utils.async_tasks import finish_pending_task


def ai_busy() -> AppError:
    return AppError(409, "AI_REQUEST_BUSY", "Tài khoản đang chờ một phản hồi AI. Vui lòng thử lại sau.")


class AiQuotaRepository(Protocol):
    def request_guard(self, user_id: int) -> AbstractAsyncContextManager[None]: ...

    async def count_successes(self, user_id: int, start: datetime, end: datetime) -> int: ...


class InMemoryAiQuotaRepository:
    def __init__(self, chat_repository, quiz_repository=None) -> None:
        self._chat = chat_repository
        self._quiz = quiz_repository
        self._busy_users: set[int] = set()

    @asynccontextmanager
    async def request_guard(self, user_id: int):
        if user_id in self._busy_users:
            raise ai_busy()
        self._busy_users.add(user_id)
        try:
            yield
        finally:
            self._busy_users.discard(user_id)

    @staticmethod
    def _within(raw: str, start: datetime, end: datetime) -> bool:
        stamp = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return start <= stamp < end

    async def count_successes(self, user_id: int, start: datetime, end: datetime) -> int:
        sessions = getattr(self._chat, "_sessions", {})
        messages = getattr(self._chat, "_messages", {})
        replies = sum(
            item.role == "assistant" and item.session_id in sessions
            and sessions[item.session_id].user_id == user_id and self._within(item.created_at, start, end)
            for item in messages.values()
        )
        quizzes = sum(
            item.user_id == user_id and self._within(item.created_at, start, end)
            for item in getattr(self._quiz, "_quizzes", {}).values()
        )
        return replies + quizzes


class SqlAlchemyAiQuotaRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    def _acquire(self, user_id: int) -> tuple[Connection, str]:
        engine = self._sessions.kw["bind"]
        namespace = f"{engine.url.database}:{user_id}".encode("utf-8")
        name = "gsaichat:" + hashlib.sha256(namespace).hexdigest()[:52]
        connection = engine.connect()
        try:
            obtained = connection.scalar(text("SELECT GET_LOCK(:name, 0)"), {"name": name})
            # Advisory locks belong to the connection and survive transaction end.
            connection.commit()
            if obtained != 1:
                connection.close()
                if obtained == 0:
                    raise ai_busy()
                raise AppError(503, "AI_QUOTA_UNAVAILABLE", "Chưa thể kiểm tra hạn mức AI. Vui lòng thử lại.")
            return connection, name
        except BaseException:
            # Never return a connection carrying an unreleased advisory lock to its pool.
            if not connection.closed:
                connection.invalidate()
                connection.close()
            raise

    @staticmethod
    def _release(lease: tuple[Connection, str]) -> None:
        connection, name = lease
        try:
            connection.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})
            connection.commit()
        except SQLAlchemyError:
            connection.invalidate()
        finally:
            connection.close()

    @staticmethod
    async def _finish_release(lease: tuple[Connection, str]) -> None:
        pending = asyncio.create_task(asyncio.to_thread(SqlAlchemyAiQuotaRepository._release, lease))
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            await finish_pending_task(pending)
            raise

    @asynccontextmanager
    async def request_guard(self, user_id: int):
        acquiring = asyncio.create_task(asyncio.to_thread(self._acquire, user_id))
        try:
            lease = await asyncio.shield(acquiring)
        except asyncio.CancelledError:
            # The worker can acquire after its awaiter is cancelled; release that lease too.
            try:
                lease = await finish_pending_task(acquiring)
            except Exception:
                pass
            else:
                await self._finish_release(lease)
            raise
        try:
            yield
        finally:
            await self._finish_release(lease)

    async def count_successes(self, user_id: int, start: datetime, end: datetime) -> int:
        return await asyncio.to_thread(self._count_successes, user_id, start, end)

    def _count_successes(self, user_id: int, start: datetime, end: datetime) -> int:
        with self._sessions() as db:
            replies = db.scalar(
                select(func.count(ChatMessage.id)).join(ChatSession, ChatSession.id == ChatMessage.session_id)
                .where(ChatSession.user_id == user_id, ChatMessage.role == "assistant",
                       ChatMessage.created_at >= start, ChatMessage.created_at < end)
            )
            quizzes = db.scalar(select(func.count(Quiz.id)).where(
                Quiz.user_id == user_id, Quiz.created_at >= start, Quiz.created_at < end,
            ))
            return int(replies or 0) + int(quizzes or 0)
