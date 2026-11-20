"""Dashboard aggregates use the same stores as chat and quiz, scoped by owner."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.quiz_repository import InMemoryQuizRepository


@dataclass(frozen=True)
class DashboardRecord:
    total_quizzes: int
    average_score: Decimal
    total_chat_sessions: int


class DashboardRepository(Protocol):
    async def get_stats(self, user_id: int) -> DashboardRecord: ...


class InMemoryDashboardRepository:
    """For injected test stores; production reads MySQL through the SQL repository."""

    def __init__(self, quiz: InMemoryQuizRepository, chat: InMemoryChatRepository) -> None:
        self._quiz = quiz
        self._chat = chat

    async def get_stats(self, user_id: int) -> DashboardRecord:
        completed = [
            quiz for quiz in self._quiz._quizzes.values()
            if quiz.user_id == user_id and quiz.status == "completed"
        ]
        scores = [quiz.score for quiz in completed if quiz.score is not None]
        average = sum(scores, Decimal("0")) / len(scores) if scores else Decimal("0")
        return DashboardRecord(
            total_quizzes=len(completed), average_score=average,
            total_chat_sessions=sum(session.user_id == user_id for session in self._chat._sessions.values()),
        )
