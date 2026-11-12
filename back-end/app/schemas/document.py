"""Dữ liệu công khai cho API tải tài liệu, không trả đường dẫn file nội bộ."""

from pydantic import BaseModel, Field


class DocumentInfo(BaseModel):
    id: int
    topic_id: int = Field(serialization_alias="topicId")
    title: str
    subject_name: str = Field(serialization_alias="subjectName")
    topic_name: str = Field(serialization_alias="topicName")
    status: str
    is_active: bool = Field(serialization_alias="isActive")
    created_at: str = Field(serialization_alias="createdAt")
    size_bytes: int | None = Field(serialization_alias="sizeBytes")
    file_name: str = Field(serialization_alias="fileName")


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
