"""Kho danh mục MySQL: chỉ đọc môn và chủ đề đang active."""

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.models.subject import Subject
from app.models.topic import Topic
from app.repositories.catalog_repository import CatalogSubject, CatalogTopic, OpenTopic


class SqlAlchemyCatalogRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def list_active_subjects(self) -> list[CatalogSubject]:
        return await asyncio.to_thread(self._list_active_subjects)

    async def find_open_topic(self, topic_id: int) -> OpenTopic | None:
        return await asyncio.to_thread(self._find_open_topic, topic_id)

    def _list_active_subjects(self) -> list[CatalogSubject]:
        with self._sessions() as db:
            rows = db.execute(
                select(Subject, Topic)
                .join(Topic, Topic.subject_id == Subject.id)
                .where(Subject.is_active.is_(True), Topic.is_active.is_(True))
                .order_by(Subject.name, Subject.grade_level, Subject.id, Topic.id)
            ).all()
        grouped: dict[int, tuple[Subject, list[CatalogTopic]]] = {}
        for subject, topic in rows:
            _, topics = grouped.setdefault(subject.id, (subject, []))
            topics.append(CatalogTopic(topic.id, topic.chapter_name, topic.name, topic.description))
        return [
            CatalogSubject(subject.id, subject.name, subject.grade_level, tuple(topics))
            for subject, topics in grouped.values()
        ]

    def _find_open_topic(self, topic_id: int) -> OpenTopic | None:
        with self._sessions() as db:
            row = db.execute(
                select(Topic, Subject)
                .join(Subject, Topic.subject_id == Subject.id)
                .where(Topic.id == topic_id, Topic.is_active.is_(True), Subject.is_active.is_(True))
            ).first()
        if row is None:
            return None
        topic, subject = row
        return OpenTopic(
            topic.id, topic.name, topic.description, topic.chapter_name,
            subject.id, subject.name, subject.grade_level,
        )
