"""Stored learning progress visible only to its authenticated owner."""

from pydantic import BaseModel, Field


class ProgressItem(BaseModel):
    id: int
    topic_id: int = Field(serialization_alias="topicId")
    total_quizzes: int = Field(serialization_alias="totalQuizzes")
    correct_count: int = Field(serialization_alias="correctCount")
    total_count: int = Field(serialization_alias="totalCount")
    mastery_percent: float = Field(serialization_alias="masteryPercent")
    last_studied_at: str | None = Field(serialization_alias="lastStudiedAt")


class ProgressResponse(BaseModel):
    progress: ProgressItem


class ProgressListResponse(BaseModel):
    progress: list[ProgressItem]
    limit: int
    offset: int
    has_more: bool = Field(serialization_alias="hasMore")


class ReviewTopicsResponse(BaseModel):
    topics: list[ProgressItem]
    limit: int
    offset: int
    has_more: bool = Field(serialization_alias="hasMore")
