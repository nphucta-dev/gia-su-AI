"""Kho tài liệu và danh mục phục vụ riêng cho màn hình tải tài liệu ADMIN."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import and_, delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.document import Document as DocumentModel
from app.models.document_chunk import DocumentChunk
from app.models.subject import Subject as SubjectModel
from app.models.topic import Topic as TopicModel
from app.utils.errors import AppError


@dataclass(frozen=True)
class SubjectRecord:
    id: int
    name: str
    grade_level: str
    is_active: bool = True


@dataclass(frozen=True)
class TopicRecord:
    id: int
    subject_id: int
    name: str
    chapter_name: str = ""
    is_active: bool = True


@dataclass(frozen=True)
class UploadSubject:
    id: int
    name: str
    grade_level: str
    topics: tuple[TopicRecord, ...]


@dataclass(frozen=True)
class UploadTopic:
    id: int
    subject_id: int
    name: str
    chapter_name: str
    subject_name: str


@dataclass(frozen=True)
class DocumentRecord:
    id: int
    topic_id: int
    title: str
    file_path: str
    status: str
    is_active: bool
    created_at: str
    subject_name: str
    topic_name: str
    processed_at: str | None = None
    chunk_count: int = 0


def missing_topic_error() -> AppError:
    message = "Chủ đề không tồn tại hoặc môn/chủ đề đã bị vô hiệu hóa."
    return AppError(404, "TOPIC_NOT_FOUND", message, {"topic_id": message})


class DocumentRepository(Protocol):
    async def list_subjects(self) -> list[UploadSubject]: ...

    async def find_upload_topic(self, topic_id: int) -> UploadTopic | None: ...

    async def list_documents(self) -> list[DocumentRecord]: ...

    async def create(self, *, topic_id: int, title: str, file_path: str) -> DocumentRecord: ...

    async def find_document(self, document_id: int) -> DocumentRecord | None: ...

    async def finish_processing(self, document_id: int, *, chunks: list[str] | None) -> DocumentRecord | None: ...


ProtocolDocumentRepository = DocumentRepository


class InMemoryDocumentRepository:
    """Có thể inject vào create_app để test, không thay thế MySQL khi chạy thật."""

    def __init__(
        self,
        *,
        subjects: Iterable[SubjectRecord] = (),
        topics: Iterable[TopicRecord] = (),
    ) -> None:
        self._subjects = {subject.id: subject for subject in subjects}
        self._topics = {topic.id: topic for topic in topics}
        self._documents: dict[int, DocumentRecord] = {}
        self._chunks: dict[int, tuple[str, ...]] = {}
        self._next_id = 1

    async def list_subjects(self) -> list[UploadSubject]:
        return [
            UploadSubject(
                id=subject.id,
                name=subject.name,
                grade_level=subject.grade_level,
                topics=tuple(
                    sorted(
                        (topic for topic in self._topics.values() if topic.subject_id == subject.id and topic.is_active),
                        key=lambda topic: (topic.chapter_name, topic.name, topic.id),
                    )
                ),
            )
            for subject in sorted(self._subjects.values(), key=lambda item: (item.name, item.id))
            if subject.is_active
        ]

    async def find_upload_topic(self, topic_id: int) -> UploadTopic | None:
        topic = self._topics.get(topic_id)
        subject = self._subjects.get(topic.subject_id) if topic else None
        if topic is None or subject is None or not topic.is_active or not subject.is_active:
            return None
        return UploadTopic(topic.id, topic.subject_id, topic.name, topic.chapter_name, subject.name)

    async def list_documents(self) -> list[DocumentRecord]:
        return sorted(self._documents.values(), key=lambda item: (item.created_at, item.id), reverse=True)

    async def create(self, *, topic_id: int, title: str, file_path: str) -> DocumentRecord:
        topic = await self.find_upload_topic(topic_id)
        if topic is None:
            raise missing_topic_error()
        document = DocumentRecord(
            id=self._next_id,
            topic_id=topic_id,
            title=title,
            file_path=file_path,
            status="pending",
            is_active=False,
            created_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            subject_name=topic.subject_name,
            topic_name=topic.name,
        )
        self._documents[document.id] = document
        self._next_id += 1
        return document

    async def find_document(self, document_id: int) -> DocumentRecord | None:
        return self._documents.get(document_id)

    async def finish_processing(self, document_id: int, *, chunks: list[str] | None) -> DocumentRecord | None:
        document = self._documents.get(document_id)
        if document is None:
            return None
        if document.status == "ready" and document.chunk_count:
            return document
        if chunks is not None and (not chunks or any(not part.strip() for part in chunks)):
            raise ValueError("Tài liệu sẵn sàng phải có các đoạn văn bản không rỗng.")
        saved_chunks = tuple(chunks or ())
        result = replace(
            document, status="ready" if chunks is not None else "error", is_active=False,
            processed_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            chunk_count=len(saved_chunks),
        )
        self._chunks[document_id] = saved_chunks
        self._documents[document_id] = result
        return result


class SqlAlchemyDocumentRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def list_subjects(self) -> list[UploadSubject]:
        return await asyncio.to_thread(self._list_subjects)

    async def find_upload_topic(self, topic_id: int) -> UploadTopic | None:
        return await asyncio.to_thread(self._find_upload_topic, topic_id)

    async def list_documents(self) -> list[DocumentRecord]:
        return await asyncio.to_thread(self._list_documents)

    async def create(self, *, topic_id: int, title: str, file_path: str) -> DocumentRecord:
        return await asyncio.to_thread(self._create, topic_id=topic_id, title=title, file_path=file_path)

    async def find_document(self, document_id: int) -> DocumentRecord | None:
        return await asyncio.to_thread(self._find_document, document_id)

    async def finish_processing(self, document_id: int, *, chunks: list[str] | None) -> DocumentRecord | None:
        return await asyncio.to_thread(self._finish_processing, document_id, chunks=chunks)

    def _list_subjects(self) -> list[UploadSubject]:
        with self._sessions() as db:
            rows = db.execute(
                select(SubjectModel, TopicModel)
                .outerjoin(TopicModel, and_(TopicModel.subject_id == SubjectModel.id, TopicModel.is_active.is_(True)))
                .where(SubjectModel.is_active.is_(True))
                .order_by(SubjectModel.name, SubjectModel.id, TopicModel.chapter_name, TopicModel.name, TopicModel.id)
            )
            subjects: dict[int, SubjectRecord] = {}
            topics: dict[int, list[TopicRecord]] = {}
            for subject, topic in rows:
                subjects[subject.id] = SubjectRecord(subject.id, subject.name, subject.grade_level)
                topics.setdefault(subject.id, [])
                if topic is not None:
                    topics[subject.id].append(TopicRecord(topic.id, subject.id, topic.name, topic.chapter_name))
            return [
                UploadSubject(subject.id, subject.name, subject.grade_level, tuple(topics[subject.id]))
                for subject in subjects.values()
            ]

    @staticmethod
    def _topic_query(topic_id: int):
        return (
            select(TopicModel, SubjectModel)
            .join(SubjectModel, SubjectModel.id == TopicModel.subject_id)
            .where(TopicModel.id == topic_id, TopicModel.is_active.is_(True), SubjectModel.is_active.is_(True))
        )

    def _find_upload_topic(self, topic_id: int) -> UploadTopic | None:
        with self._sessions() as db:
            row = db.execute(self._topic_query(topic_id)).first()
            if row is None:
                return None
            topic, subject = row
            return UploadTopic(topic.id, subject.id, topic.name, topic.chapter_name, subject.name)

    def _list_documents(self) -> list[DocumentRecord]:
        with self._sessions() as db:
            rows = db.execute(self._document_query().order_by(DocumentModel.created_at.desc(), DocumentModel.id.desc()))
            return [self._to_record(document, topic, subject, count) for document, topic, subject, count in rows]

    @staticmethod
    def _document_query():
        count = select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == DocumentModel.id).scalar_subquery()
        return (
            select(DocumentModel, TopicModel.name, SubjectModel.name, count)
            .join(TopicModel, TopicModel.id == DocumentModel.topic_id)
            .join(SubjectModel, SubjectModel.id == TopicModel.subject_id)
        )

    def _find_document(self, document_id: int) -> DocumentRecord | None:
        with self._sessions() as db:
            row = db.execute(self._document_query().where(DocumentModel.id == document_id)).first()
            return self._to_record(*row) if row is not None else None

    def _finish_processing(self, document_id: int, *, chunks: list[str] | None) -> DocumentRecord | None:
        if chunks is not None and (not chunks or any(not part.strip() for part in chunks)):
            raise ValueError("Tài liệu sẵn sàng phải có các đoạn văn bản không rỗng.")
        with self._sessions.begin() as db:
            # Khóa bản ghi cha: các lần xử lý đồng thời không tạo trùng chunk_index.
            document = db.get(DocumentModel, document_id, with_for_update=True)
            if document is None:
                return None
            count = db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id))
            topic = db.get(TopicModel, document.topic_id)
            subject = db.get(SubjectModel, topic.subject_id)
            if document.status == "ready" and count:
                return self._to_record(document, topic.name, subject.name, count)
            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            db.add_all([
                DocumentChunk(document_id=document_id, chunk_index=index, content=content)
                for index, content in enumerate(chunks or ())
            ])
            document.status = "ready" if chunks is not None else "error"
            document.is_active = False
            document.processed_at = datetime.now(timezone.utc)
            # Chunks và trạng thái cùng commit; lỗi ghi sẽ rollback toàn bộ.
            db.flush()
            return self._to_record(document, topic.name, subject.name, len(chunks or ()))

    def _create(self, *, topic_id: int, title: str, file_path: str) -> DocumentRecord:
        with self._sessions.begin() as db:
            # Kiểm tra lại trong transaction; khóa danh mục khi tạo tài liệu mới.
            row = db.execute(self._topic_query(topic_id).with_for_update()).first()
            if row is None:
                raise missing_topic_error()
            topic, subject = row
            document = DocumentModel(topic_id=topic_id, title=title, file_path=file_path, status="pending", is_active=False)
            db.add(document)
            db.flush()
            db.refresh(document)
            saved = self._to_record(document, topic.name, subject.name)
        return saved

    @staticmethod
    def _to_record(document: DocumentModel, topic_name: str, subject_name: str, chunk_count: int = 0) -> DocumentRecord:
        created_at = document.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return DocumentRecord(
            id=document.id,
            topic_id=document.topic_id,
            title=document.title,
            file_path=document.file_path,
            status=document.status,
            is_active=document.is_active,
            created_at=created_at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            subject_name=subject_name,
            topic_name=topic_name,
            processed_at=(
                document.processed_at.replace(tzinfo=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                if document.processed_at is not None else None
            ),
            chunk_count=chunk_count,
        )
