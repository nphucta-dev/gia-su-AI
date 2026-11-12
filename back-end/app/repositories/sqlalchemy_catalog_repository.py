"""Kho danh mục MySQL cho luồng học và quản trị nội dung."""

import asyncio

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.models.subject import Subject
from app.models.topic import Topic
from app.repositories.catalog_repository import (
    AdminSubject, AdminTopic, CatalogConflictError, CatalogSubject,
    CatalogSubjectNotFoundError, CatalogTopic, OpenTopic,
)


class SqlAlchemyCatalogRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def list_active_subjects(self, *, grade_level: str | None = None) -> list[CatalogSubject]:
        return await asyncio.to_thread(self._list_active_subjects, grade_level=grade_level)

    async def find_open_topic(self, topic_id: int) -> OpenTopic | None:
        return await asyncio.to_thread(self._find_open_topic, topic_id)

    def _list_active_subjects(self, *, grade_level: str | None = None) -> list[CatalogSubject]:
        statement = (
            select(Subject, Topic)
            .join(Topic, Topic.subject_id == Subject.id)
            .where(Subject.is_active.is_(True), Topic.is_active.is_(True))
            .order_by(Subject.name, Subject.grade_level, Subject.id, Topic.id)
        )
        if grade_level is not None:
            statement = statement.where(Subject.grade_level == grade_level)
        with self._sessions() as db:
            rows = db.execute(statement).all()
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

    async def list_admin_subjects(self) -> list[AdminSubject]:
        return await asyncio.to_thread(self._list_admin_subjects)

    async def list_admin_topics(self) -> list[AdminTopic]:
        return await asyncio.to_thread(self._list_admin_topics)

    async def create_subject(self, values: dict) -> AdminSubject:
        return await asyncio.to_thread(self._save_subject, values)

    async def update_subject(self, subject_id: int, changes: dict) -> AdminSubject | None:
        return await asyncio.to_thread(self._save_subject, changes, subject_id)

    async def create_topic(self, values: dict) -> AdminTopic:
        return await asyncio.to_thread(self._save_topic, values)

    async def update_topic(self, topic_id: int, changes: dict) -> AdminTopic | None:
        return await asyncio.to_thread(self._save_topic, changes, topic_id)

    @staticmethod
    def _subject_item(subject: Subject) -> AdminSubject:
        return AdminSubject(subject.id, subject.name, subject.grade_level, subject.is_active)

    @staticmethod
    def _topic_item(topic: Topic, subject: Subject) -> AdminTopic:
        return AdminTopic(
            topic.id, subject.id, subject.name, subject.grade_level,
            topic.chapter_name, topic.name, topic.description, topic.is_active,
        )

    def _list_admin_subjects(self) -> list[AdminSubject]:
        with self._sessions() as db:
            return [self._subject_item(item) for item in db.scalars(select(Subject).order_by(Subject.id))]

    def _list_admin_topics(self) -> list[AdminTopic]:
        with self._sessions() as db:
            rows = db.execute(select(Topic, Subject).join(Subject, Topic.subject_id == Subject.id).order_by(Topic.id))
            return [self._topic_item(topic, subject) for topic, subject in rows]

    def _save_subject(self, values: dict, subject_id: int | None = None) -> AdminSubject | None:
        try:
            with self._sessions.begin() as db:
                if subject_id is None:
                    subject = Subject(**values)
                    db.add(subject)
                else:
                    subject = db.get(Subject, subject_id, with_for_update=True)
                    if subject is None:
                        return None
                    for key, value in values.items():
                        setattr(subject, key, value)
                db.flush()
                return self._subject_item(subject)
        except IntegrityError as exc:
            if exc.orig.args and exc.orig.args[0] == 1062:
                raise CatalogConflictError() from None
            raise

    def _save_topic(self, values: dict, topic_id: int | None = None) -> AdminTopic | None:
        try:
            with self._sessions.begin() as db:
                if topic_id is None:
                    topic = Topic(**values)
                    subject_id = values["subject_id"]
                else:
                    topic = db.get(Topic, topic_id, with_for_update=True)
                    if topic is None:
                        return None
                    subject_id = values.get("subject_id", topic.subject_id)
                subject = db.get(Subject, subject_id, with_for_update=True)
                if subject is None:
                    raise CatalogSubjectNotFoundError()
                for key, value in values.items():
                    setattr(topic, key, value)
                if topic_id is None:
                    db.add(topic)
                db.flush()
                return self._topic_item(topic, subject)
        except IntegrityError as exc:
            if exc.orig.args and exc.orig.args[0] == 1062:
                raise CatalogConflictError() from None
            raise
