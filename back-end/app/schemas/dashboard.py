"""Summary counters for the authenticated account, without quiz or chat content."""

from pydantic import BaseModel, Field


class DashboardStats(BaseModel):
    total_quizzes: int = Field(ge=0, serialization_alias="totalQuizzes")
    average_score: float = Field(ge=0, le=100, allow_inf_nan=False, serialization_alias="averageScore")
    total_chat_sessions: int = Field(ge=0, serialization_alias="totalChatSessions")


class DashboardResponse(BaseModel):
    dashboard: DashboardStats
