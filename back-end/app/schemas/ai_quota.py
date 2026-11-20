"""Successful model requests counted from persisted chat replies and quizzes."""

from typing import Literal

from pydantic import BaseModel, Field


class AiQuotaItem(BaseModel):
    limit: int
    used: int
    remaining: int
    next_reset_at: str = Field(serialization_alias="nextResetAt")
    reset_timezone: Literal["UTC"] = Field(default="UTC", serialization_alias="resetTimezone")
