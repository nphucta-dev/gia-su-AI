"""TK-077: Dữ liệu API thông tin quota (remaining và next_reset_at)."""

from pydantic import BaseModel, Field


class QuotaInfo(BaseModel):
    daily_limit: int = Field(serialization_alias="dailyLimit")
    used_today: int = Field(serialization_alias="usedToday")
    remaining: int
    next_reset_at: str = Field(serialization_alias="nextResetAt")


class QuotaResponse(BaseModel):
    quota: QuotaInfo
