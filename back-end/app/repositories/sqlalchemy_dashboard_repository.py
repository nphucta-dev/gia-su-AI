"""Read all dashboard counters in one statement without multiplying joined rows."""

import asyncio
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.chat_session import ChatSession
from app.models.quiz import Quiz, QuizStatus
from app.repositories.dashboard_repository import DashboardRecord


class SqlAlchemyDashboardRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def get_stats(self, user_id: int) -> DashboardRecord:
        return await asyncio.to_thread(self._get_stats, user_id)

    def _get_stats(self, user_id: int) -> DashboardRecord:
        completed = select(
            func.count(Quiz.id).label("total_quizzes"),
            func.coalesce(func.avg(Quiz.score), 0).label("average_score"),
        ).where(Quiz.user_id == user_id, Quiz.status == QuizStatus.COMPLETED.value).subquery()
        sessions = select(func.count(ChatSession.id)).where(ChatSession.user_id == user_id).scalar_subquery()
        with self._sessions() as db:
            row = db.execute(select(
                completed.c.total_quizzes, completed.c.average_score,
                sessions.label("total_chat_sessions"),
            )).one()
            return DashboardRecord(
                total_quizzes=row.total_quizzes, average_score=Decimal(str(row.average_score)),
                total_chat_sessions=row.total_chat_sessions,
            )
