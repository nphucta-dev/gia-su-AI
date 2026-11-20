"""TK-075: Hạn mức lượt gọi AI mặc định 30 yêu cầu thành công/ngày/tài khoản."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.repositories.chat_repository import ChatRepository, utc_timestamp
from app.repositories.user_repository import User
from app.utils.errors import AppError
from app.schemas.quota import QuotaInfo, QuotaResponse

DEFAULT_DAILY_AI_LIMIT = 30


@dataclass(frozen=True)
class QuotaStatus:
    daily_limit: int
    used_today: int
    remaining: int
    next_reset_at: str


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
    """Tính hạn mức từ các phản hồi AI thành công (role='assistant') trong ngày UTC hiện tại."""

    def __init__(self, chat_repository: ChatRepository, *, daily_limit: int = DEFAULT_DAILY_AI_LIMIT, ai_quota_service=None) -> None:
        if not isinstance(daily_limit, int) or isinstance(daily_limit, bool) or daily_limit < 1:
            raise ValueError("daily_limit phải là số nguyên dương.")
        self._chat_repository = chat_repository
        self._daily_limit = daily_limit
        self._ai_quota_service = ai_quota_service

    @property
    def daily_limit(self) -> int:
        return self._daily_limit

    async def get_quota_status(self, user_id: int, *, now: datetime | None = None) -> QuotaStatus:
        if self._ai_quota_service is not None:
            quota = await self._ai_quota_service.get_quota(user_id)
            return QuotaStatus(quota.limit, quota.used, quota.remaining, quota.next_reset_at)
        day_start, next_reset = utc_day_bounds(now)
        used = await self._chat_repository.count_assistant_messages_since(user_id, day_start)
        remaining = max(0, self._daily_limit - used)
        return QuotaStatus(
            daily_limit=self._daily_limit,
            used_today=used,
            remaining=remaining,
            next_reset_at=utc_timestamp(next_reset),
        )

    async def ensure_within_quota(self, user: User, *, now: datetime | None = None) -> QuotaStatus:
        status = await self.get_quota_status(user.id, now=now)
        if status.remaining <= 0:
            if self._ai_quota_service is not None:
                reset = datetime.fromisoformat(status.next_reset_at.replace("Z", "+00:00"))
                seconds = max(1, int((reset - datetime.now(timezone.utc)).total_seconds()))
                raise AppError(429, "AI_QUOTA_EXCEEDED", "B?n ?? d?ng h?t l??t AI h?m nay. L?ch s? v?n xem ???c.", {"nextResetAt": status.next_reset_at}, headers={"Retry-After": str(seconds)})
            raise AppError(
                429,
                "AI_QUOTA_EXCEEDED",
                f"Bạn đã dùng hết {self._daily_limit} lượt hỏi đáp AI trong ngày. Bạn vẫn có thể xem lại lịch sử và tiến độ học tập.",
            )
        return status

    async def get_quota(self, user: User, *, now: datetime | None = None) -> QuotaResponse:
        status = await self.get_quota_status(user.id, now=now)
        return QuotaResponse(quota=QuotaInfo(
            daily_limit=status.daily_limit, used_today=status.used_today,
            remaining=status.remaining, next_reset_at=status.next_reset_at,
        ))
