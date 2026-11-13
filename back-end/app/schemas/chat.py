"""Dữ liệu API phiên chat, lịch sử và gợi ý; role/level do server quyết định."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CreateChatSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic_id: int = Field(alias="topicId", strict=True, ge=1, le=2**31 - 1)
    title: str | None = Field(default=None, strict=True, max_length=200)


class SendChatMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(strict=True, min_length=1, max_length=4000)


class ChatSessionItem(BaseModel):
    id: int
    topic_id: int = Field(serialization_alias="topicId")
    title: str | None
    topic_name: str = Field(serialization_alias="topicName")
    subject_name: str = Field(serialization_alias="subjectName")
    grade_level: str = Field(serialization_alias="gradeLevel")
    chapter_name: str = Field(serialization_alias="chapterName")
    created_at: str = Field(serialization_alias="createdAt")
    updated_at: str = Field(serialization_alias="updatedAt")


class ChatMessageItem(BaseModel):
    id: int
    session_id: int = Field(serialization_alias="sessionId")
    role: Literal["user", "assistant"]
    content: str
    hint_level: int | None = Field(default=None, serialization_alias="hintLevel")
    is_full_solution: bool = Field(default=False, serialization_alias="isFullSolution")
    token_count: int | None = Field(default=None, serialization_alias="tokenCount")
    created_at: str = Field(serialization_alias="createdAt")


class ChatSessionResponse(BaseModel):
    session: ChatSessionItem


class ChatSessionListResponse(BaseModel):
    sessions: list[ChatSessionItem]
    limit: int
    offset: int
    has_more: bool = Field(serialization_alias="hasMore")


class ChatMessageListResponse(BaseModel):
    session: ChatSessionItem
    messages: list[ChatMessageItem]
    limit: int
    offset: int
    has_more: bool = Field(serialization_alias="hasMore")


class ChatReplyResponse(BaseModel):
    session: ChatSessionItem
    user_message: ChatMessageItem | None = Field(default=None, serialization_alias="userMessage")
    assistant_message: ChatMessageItem = Field(serialization_alias="assistantMessage")
