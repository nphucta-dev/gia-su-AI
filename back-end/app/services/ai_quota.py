"""One account's successful AI operations per UTC calendar day."""

from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.ai_quota_repository import AiQuotaRepository
from app.repositories.chat_repository import utc_timestamp
from app.schemas.ai_quota import AiQuotaItem
from app.utils.errors import AppError


class AiQuotaService:
    def __init__(self, repository: AiQuotaRepository, *, limit: int = 30, clock: Callable[[], datetime] | None = None) -> None:
        self._repository = repository
        self._limit = limit
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    async def get_quota(self, user_id: int) -> AiQuotaItem:
        now = self._clock().astimezone(timezone.utc)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        try:
            used = await self._repository.count_successes(user_id, start, end)
        except SQLAlchemyError:
            raise AppError(503, "AI_QUOTA_UNAVAILABLE", "Chưa thể kiểm tra hạn mức AI. Vui lòng thử lại.") from None
        return AiQuotaItem(limit=self._limit, used=used, remaining=max(0, self._limit - used), next_reset_at=utc_timestamp(end))

    @asynccontextmanager
    async def generation(self, user_id: int):
        async with AsyncExitStack() as stack:
            try:
                await stack.enter_async_context(self._repository.request_guard(user_id))
            except SQLAlchemyError:
                raise AppError(503, "AI_QUOTA_UNAVAILABLE", "Chưa thể kiểm tra hạn mức AI. Vui lòng thử lại.") from None
            quota = await self.get_quota(user_id)
            if quota.remaining == 0:
                reset = datetime.fromisoformat(quota.next_reset_at.replace("Z", "+00:00"))
                retry_after = max(1, int((reset - self._clock().astimezone(timezone.utc)).total_seconds()))
                raise AppError(
                    429, "AI_QUOTA_EXCEEDED", "Bạn đã dùng hết lượt AI hôm nay. Lịch sử vẫn xem được.",
                    {"nextResetAt": quota.next_reset_at}, headers={"Retry-After": str(retry_after)},
                )
            yield
