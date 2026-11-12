"""Đọc danh mục môn, chương, chủ đề đang mở cho người học."""

from __future__ import annotations

from typing import Protocol

from app.repositories.catalog_repository import CatalogSubject, OpenTopic
from app.schemas.catalog import (
    ChapterItem,
    OpenTopicItem,
    SubjectItem,
    SubjectListResponse,
    TopicItem,
)
from app.utils.errors import AppError

TOPIC_NOT_OPEN_MESSAGE = "Chủ đề không tồn tại hoặc chưa được mở."


class CatalogRepository(Protocol):
    async def list_active_subjects(self, *, grade_level: str | None = None) -> list[CatalogSubject]: ...

    async def find_open_topic(self, topic_id: int) -> OpenTopic | None: ...


class CatalogService:
    def __init__(self, repository: CatalogRepository) -> None:
        self._repository = repository

    async def list_subjects(self, *, grade_level: str | None = None) -> SubjectListResponse:
        if grade_level is not None:
            grade_level = grade_level.strip() or None
        subjects = []
        for subject in await self._repository.list_active_subjects(grade_level=grade_level):
            chapters: dict[str, list[TopicItem]] = {}  # dict giữ thứ tự chương xuất hiện đầu tiên
            for topic in subject.topics:
                chapters.setdefault(topic.chapter_name, []).append(
                    TopicItem(id=topic.id, name=topic.name, description=topic.description)
                )
            subjects.append(
                SubjectItem(
                    id=subject.id,
                    name=subject.name,
                    grade_level=subject.grade_level,
                    chapters=[ChapterItem(name=name, topics=items) for name, items in chapters.items()],
                )
            )
        return SubjectListResponse(subjects=subjects)

    async def get_open_topic(self, topic_id: int) -> OpenTopicItem:
        """Dùng cho luồng học: chủ đề và môn của nó đều phải đang active."""
        topic = await self._repository.find_open_topic(topic_id)
        if topic is None:
            raise AppError(404, "TOPIC_NOT_FOUND", TOPIC_NOT_OPEN_MESSAGE)
        return OpenTopicItem(
            id=topic.id,
            name=topic.name,
            description=topic.description,
            chapter_name=topic.chapter_name,
            subject_id=topic.subject_id,
            subject_name=topic.subject_name,
            grade_level=topic.grade_level,
        )
