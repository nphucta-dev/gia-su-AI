"""Schema phản hồi cho API xem tài liệu học tập của người học (không lộ đường dẫn nội bộ)."""

from typing import Literal

from pydantic import BaseModel, Field


class LearningDocumentChunkItem(BaseModel):
    id: int
    chunk_index: int = Field(serialization_alias="chunkIndex")
    content: str


class LearningDocumentItem(BaseModel):
    id: int
    topic_id: int = Field(serialization_alias="topicId")
    subject_id: int = Field(serialization_alias="subjectId")
    title: str
    subject_name: str = Field(serialization_alias="subjectName")
    grade_level: str = Field(serialization_alias="gradeLevel")
    topic_name: str = Field(serialization_alias="topicName")
    chapter_name: str = Field(serialization_alias="chapterName")
    source_url: str | None = Field(default=None, serialization_alias="sourceUrl")
    file_name: str = Field(serialization_alias="fileName")
    file_type: Literal["pdf", "txt", "unknown"] = Field(serialization_alias="fileType")
    size_bytes: int | None = Field(default=None, serialization_alias="sizeBytes")
    chunk_count: int = Field(default=0, serialization_alias="chunkCount")
    created_at: str = Field(serialization_alias="createdAt")
    processed_at: str | None = Field(default=None, serialization_alias="processedAt")


class LearningDocumentDetail(LearningDocumentItem):
    content: str
    chunks: list[LearningDocumentChunkItem]


class LearningDocumentListResponse(BaseModel):
    documents: list[LearningDocumentItem]
    limit: int
    offset: int
    has_more: bool = Field(serialization_alias="hasMore")


class TopicDocumentListResponse(LearningDocumentListResponse):
    topic_id: int = Field(serialization_alias="topicId")


class LearningDocumentDetailResponse(BaseModel):
    document: LearningDocumentDetail
