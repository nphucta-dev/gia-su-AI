"""Read persisted progress through the authenticated account, never a supplied owner ID."""

from dataclasses import asdict

from app.repositories.progress_repository import ProgressRecord, ProgressRepository
from app.repositories.user_repository import User
from app.schemas.progress import ProgressItem, ProgressListResponse, ProgressResponse, ReviewTopicsResponse
from app.utils.errors import AppError


def progress_item(record: ProgressRecord) -> ProgressItem:
    values = asdict(record)
    return ProgressItem(**{name: values[name] for name in ProgressItem.model_fields})


class ProgressService:
    def __init__(self, repository: ProgressRepository) -> None:
        self._repository = repository

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

    async def list_review_topics(self, user: User, *, limit: int, offset: int) -> ReviewTopicsResponse:
        """TK-067: Gợi ý chủ đề cần ôn theo mastery_percent tăng dần."""
        records = await self._repository.list_review_topics(user.id, limit=limit + 1, offset=offset)
        return ReviewTopicsResponse(
            topics=[progress_item(record) for record in records[:limit]],
            limit=limit, offset=offset, has_more=len(records) > limit,
        )
