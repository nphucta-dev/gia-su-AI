"""Completed quiz scores and chat counts; reads never consume AI quota."""

from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.user_repository import User
from app.schemas.dashboard import DashboardResponse, DashboardStats
from app.utils.errors import AppError


class DashboardService:
    def __init__(self, repository: DashboardRepository) -> None:
        self._repository = repository

    async def get_dashboard(self, user: User) -> DashboardResponse:
        try:
            stats = await self._repository.get_stats(user.id)
        except SQLAlchemyError:
            raise AppError(
                503, "DASHBOARD_UNAVAILABLE", "Chưa thể tải thống kê học tập. Vui lòng thử lại.",
            ) from None
        return DashboardResponse(dashboard=DashboardStats(
            total_quizzes=stats.total_quizzes,
            average_score=float(stats.average_score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
            total_chat_sessions=stats.total_chat_sessions,
        ))
