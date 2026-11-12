"""Dữ liệu danh mục dành cho quản trị, gồm cả nội dung đã tắt."""

from pydantic import BaseModel, Field


class AdminSubjectItem(BaseModel):
    id: int
    name: str
    grade_level: str = Field(serialization_alias="gradeLevel")
    is_active: bool = Field(serialization_alias="isActive")


class AdminTopicItem(BaseModel):
    id: int
    subject_id: int = Field(serialization_alias="subjectId")
    subject_name: str = Field(serialization_alias="subjectName")
    grade_level: str = Field(serialization_alias="gradeLevel")
    chapter_name: str = Field(serialization_alias="chapterName")
    name: str
    description: str | None
    is_active: bool = Field(serialization_alias="isActive")


class AdminSubjectResponse(BaseModel):
    subject: AdminSubjectItem


class AdminSubjectListResponse(BaseModel):
    subjects: list[AdminSubjectItem]


class AdminTopicResponse(BaseModel):
    topic: AdminTopicItem


class AdminTopicListResponse(BaseModel):
    topics: list[AdminTopicItem]
