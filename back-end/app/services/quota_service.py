"""TK-077: Dịch vụ tính thông tin quota (remaining và next_reset_at) theo tài khoản."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.repositories.chat_repository import ChatRepository, utc_timestamp
from app.repositories.user_repository import User
from app.schemas.quota import QuotaInfo, QuotaResponse

DEFAULT_DAILY_AI_LIMIT = 30


def utc_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    current = now if now is not None else datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    day_start = current.replace(hour=0, minute=0, second=0, microsecond=0)
    next_reset = day_start + timedelta(days=1)
    return day_start, next_reset


class QuotaService:
    def __init__(self, chat_repository: ChatRepository, *, daily_limit: int = DEFAULT_DAILY_AI_LIMIT) -> None:
        if not isinstance(daily_limit, int) or isinstance(daily_limit, bool) or daily_limit < 1:
            raise ValueError("daily_limit phải là số nguyên dương.")
        self._chat_repository = chat_repository
        self._daily_limit = daily_limit

    async def get_quota(self, user: User, *, now: datetime | None = None) -> QuotaResponse:
        day_start, next_reset = utc_day_bounds(now)
        used = await self._chat_repository.count_assistant_messages_since(user.id, day_start)
        remaining = max(0, self._daily_limit - used)
        return QuotaResponse(quota=QuotaInfo(
            daily_limit=self._daily_limit,
            used_today=used,
            remaining=remaining,
            next_reset_at=utc_timestamp(next_reset),
        ))
