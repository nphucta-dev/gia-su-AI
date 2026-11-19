"""Read persisted progress through the authenticated account, never a supplied owner ID."""

from dataclasses import asdict
from decimal import Decimal

from app.repositories.progress_repository import ProgressRecord, ProgressRepository
from app.repositories.user_repository import User
from app.schemas.progress import ProgressItem, ProgressListResponse, ProgressResponse
from app.services.mastery import calculate_mastery_percent
from app.utils.errors import AppError


def progress_item(record: ProgressRecord) -> ProgressItem:
    values = asdict(record)
    return ProgressItem(**{name: values[name] for name in ProgressItem.model_fields})


class ProgressService:
    def __init__(self, repository: ProgressRepository) -> None:
        self._repository = repository

    @staticmethod
    def calculate_mastery(correct_count: int, total_count: int) -> Decimal:
        try:
            return calculate_mastery_percent(correct_count, total_count)
        except ValueError as error:
            raise AppError(422, "VALIDATION_ERROR", str(error)) from None

    async def get_progress(self, user: User, progress_id: int) -> ProgressResponse:
        record = await self._repository.find_progress(user.id, progress_id)
        if record is None:
            raise AppError(404, "PROGRESS_NOT_FOUND", "Không tìm thấy tiến độ học tập của bạn.")
        return ProgressResponse(progress=progress_item(record))

    async def list_progress(self, user: User, *, limit: int, offset: int) -> ProgressListResponse:
        records = await self._repository.list_progress(user.id, limit=limit + 1, offset=offset)
        return ProgressListResponse(
            progress=[progress_item(record) for record in records[:limit]],
            limit=limit, offset=offset, has_more=len(records) > limit,
        )
