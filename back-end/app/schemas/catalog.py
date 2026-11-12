"""Schema phản hồi cho API danh mục môn học."""

from pydantic import BaseModel, Field


class TopicItem(BaseModel):
    id: int
    name: str
    description: str | None = None


class ChapterItem(BaseModel):
    name: str
    topics: list[TopicItem]


class SubjectItem(BaseModel):
    id: int
    name: str
    grade_level: str = Field(serialization_alias="gradeLevel")
    chapters: list[ChapterItem]


class SubjectListResponse(BaseModel):
    subjects: list[SubjectItem]


class OpenTopicItem(BaseModel):
    id: int
    name: str
    description: str | None = None
    chapter_name: str = Field(serialization_alias="chapterName")
    subject_id: int = Field(serialization_alias="subjectId")
    subject_name: str = Field(serialization_alias="subjectName")
    grade_level: str = Field(serialization_alias="gradeLevel")


class OpenTopicResponse(BaseModel):
    topic: OpenTopicItem
