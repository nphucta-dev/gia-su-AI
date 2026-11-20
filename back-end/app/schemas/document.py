"""Dữ liệu công khai cho API quản trị tài liệu, không trả đường dẫn file nội bộ."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class UpdateDocumentActiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    is_active: bool = Field(
        alias="isActive", strict=True,
        description="Bật/tắt nguồn; chỉ bật tài liệu ready đã có nội dung. Không nhận status do client đặt.",
    )


# Giữ tên đã dùng trong code tích hợp trước đây, dùng chung quy tắc kiểm tra.
UpdateDocumentRequest = UpdateDocumentActiveRequest


class DocumentInfo(BaseModel):
    id: int
    topic_id: int = Field(serialization_alias="topicId")
    title: str
    subject_name: str = Field(serialization_alias="subjectName")
    topic_name: str = Field(serialization_alias="topicName")
    status: Literal["pending", "ready", "error"] = Field(description="Trạng thái do bước xử lý tài liệu cập nhật.")
    is_active: bool = Field(serialization_alias="isActive")
    created_at: str = Field(serialization_alias="createdAt")
    size_bytes: int | None = Field(serialization_alias="sizeBytes")
    file_name: str = Field(serialization_alias="fileName")
    processed_at: str | None = Field(default=None, serialization_alias="processedAt")
    chunk_count: int = Field(default=0, serialization_alias="chunkCount")


class DocumentResponse(BaseModel):
    message: str
    document: DocumentInfo


class DocumentListResponse(BaseModel):
    documents: list[DocumentInfo]


class UploadTopicInfo(BaseModel):
    id: int
    name: str
    chapter_name: str = Field(serialization_alias="chapterName")


class UploadSubjectInfo(BaseModel):
    id: int
    name: str
    grade_level: str = Field(serialization_alias="gradeLevel")
    topics: list[UploadTopicInfo]


class DocumentOptionsResponse(BaseModel):
    subjects: list[UploadSubjectInfo]
