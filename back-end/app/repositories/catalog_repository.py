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


@dataclass(frozen=True)
class AdminSubject:
    id: int
    name: str
    grade_level: str
    is_active: bool


@dataclass(frozen=True)
class AdminTopic:
    id: int
    subject_id: int
    subject_name: str
    grade_level: str
    chapter_name: str
    name: str
    description: str | None
    is_active: bool


class CatalogConflictError(Exception):
    """Trùng khóa tên/cấp học hoặc môn/chương/tên chủ đề."""


class CatalogSubjectNotFoundError(Exception):
    """Môn cha của chủ đề không tồn tại."""


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

    def _admin_subject(self, subject_id: int) -> AdminSubject:
        return AdminSubject(subject_id, **self._subjects[subject_id])

    def _admin_topic(self, topic_id: int) -> AdminTopic:
        topic = self._topics[topic_id]
        subject = self._subjects[topic["subject_id"]]
        return AdminTopic(topic_id, subject_name=subject["name"], grade_level=subject["grade_level"], **topic)

    async def list_admin_subjects(self) -> list[AdminSubject]:
        return [self._admin_subject(key) for key in sorted(self._subjects)]

    async def list_admin_topics(self) -> list[AdminTopic]:
        return [self._admin_topic(key) for key in sorted(self._topics)]

    def _check_subject_unique(self, candidate: dict, exclude_id: int | None = None) -> None:
        if any(
            key != exclude_id and (item["name"], item["grade_level"]) == (candidate["name"], candidate["grade_level"])
            for key, item in self._subjects.items()
        ):
            raise CatalogConflictError()

    def _check_topic_unique(self, candidate: dict, exclude_id: int | None = None) -> None:
        if candidate["subject_id"] not in self._subjects:
            raise CatalogSubjectNotFoundError()
        fields = ("subject_id", "chapter_name", "name")
        if any(
            key != exclude_id and all(item[field] == candidate[field] for field in fields)
            for key, item in self._topics.items()
        ):
            raise CatalogConflictError()

    async def create_subject(self, values: dict) -> AdminSubject:
        self._check_subject_unique(values)
        key = self.add_subject(**values)
        return self._admin_subject(key)

    async def update_subject(self, subject_id: int, changes: dict) -> AdminSubject | None:
        existing = self._subjects.get(subject_id)
        if existing is None:
            return None
        candidate = {**existing, **changes}
        self._check_subject_unique(candidate, subject_id)
        self._subjects[subject_id] = candidate
        return self._admin_subject(subject_id)

    async def create_topic(self, values: dict) -> AdminTopic:
        self._check_topic_unique(values)
        key = self.add_topic(**values)
        return self._admin_topic(key)

    async def update_topic(self, topic_id: int, changes: dict) -> AdminTopic | None:
        existing = self._topics.get(topic_id)
        if existing is None:
            return None
        candidate = {**existing, **changes}
        self._check_topic_unique(candidate, topic_id)
        self._topics[topic_id] = candidate
        return self._admin_topic(topic_id)
