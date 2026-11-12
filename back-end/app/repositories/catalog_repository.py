"""DTO danh mục môn/chủ đề và repository trong bộ nhớ dùng cho kiểm thử."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogTopic:
    id: int
    chapter_name: str
    name: str
    description: str | None


@dataclass(frozen=True)
class CatalogSubject:
    id: int
    name: str
    grade_level: str
    topics: tuple[CatalogTopic, ...]


@dataclass(frozen=True)
class OpenTopic:
    id: int
    name: str
    description: str | None
    chapter_name: str
    subject_id: int
    subject_name: str
    grade_level: str


class InMemoryCatalogRepository:
    def __init__(self) -> None:
        self._subjects: dict[int, dict] = {}
        self._topics: dict[int, dict] = {}
        self._next_subject_id = 1
        self._next_topic_id = 1

    def add_subject(self, name: str, grade_level: str, *, is_active: bool = True) -> int:
        subject_id = self._next_subject_id
        self._next_subject_id += 1
        self._subjects[subject_id] = {"name": name, "grade_level": grade_level, "is_active": is_active}
        return subject_id

    def add_topic(
        self,
        subject_id: int,
        chapter_name: str,
        name: str,
        description: str | None = None,
        *,
        is_active: bool = True,
    ) -> int:
        topic_id = self._next_topic_id
        self._next_topic_id += 1
        self._topics[topic_id] = {
            "subject_id": subject_id,
            "chapter_name": chapter_name,
            "name": name,
            "description": description,
            "is_active": is_active,
        }
        return topic_id

    async def list_active_subjects(self, *, grade_level: str | None = None) -> list[CatalogSubject]:
        result: list[CatalogSubject] = []
        ordered = sorted(
            self._subjects.items(), key=lambda item: (item[1]["name"], item[1]["grade_level"], item[0])
        )
        for subject_id, subject in ordered:
            if not subject["is_active"] or (grade_level is not None and subject["grade_level"] != grade_level):
                continue
            topics = tuple(
                CatalogTopic(topic_id, t["chapter_name"], t["name"], t["description"])
                for topic_id, t in sorted(self._topics.items())
                if t["subject_id"] == subject_id and t["is_active"]
            )
            if topics:
                result.append(CatalogSubject(subject_id, subject["name"], subject["grade_level"], topics))
        return result

    async def find_open_topic(self, topic_id: int) -> OpenTopic | None:
        topic = self._topics.get(topic_id)
        if topic is None or not topic["is_active"]:
            return None
        subject = self._subjects.get(topic["subject_id"])
        if subject is None or not subject["is_active"]:
            return None
        return OpenTopic(
            topic_id, topic["name"], topic["description"], topic["chapter_name"],
            topic["subject_id"], subject["name"], subject["grade_level"],
        )
