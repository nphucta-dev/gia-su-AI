"""Kho tài liệu và danh mục phục vụ riêng cho màn hình tải tài liệu ADMIN."""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Protocol

from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from app.models.document import Document as DocumentModel
from app.models.document_chunk import DocumentChunk
from app.models.subject import Subject as SubjectModel
from app.models.topic import Topic as TopicModel
from app.utils.errors import AppError
from app.utils.keywords import fold_text, literal_contains_pattern


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
    source_url: str | None = None


@dataclass(frozen=True)
class LearningDocumentRecord:
    id: int
    topic_id: int
    subject_id: int
    title: str
    file_path: str
    source_url: str | None
    created_at: str
    processed_at: str | None
    subject_name: str
    grade_level: str
    topic_name: str
    chapter_name: str
    chunk_count: int = 0


@dataclass(frozen=True)
class LearningDocumentChunkRecord:
    id: int
    chunk_index: int
    content: str


@dataclass(frozen=True)
class LearningDocumentDetailRecord:
    document: LearningDocumentRecord
    chunks: tuple[LearningDocumentChunkRecord, ...]


@dataclass(frozen=True)
class DocumentChunkRecord:
    id: int
    document_id: int
    document_title: str
    topic_id: int
    chunk_index: int
    content: str
    source_url: str | None = None
    embedding: tuple[float, ...] | None = None


class DocumentNotReadyError(Exception):
    """Không cho phép bật tài liệu có trạng thái khác ready."""


def missing_topic_error() -> AppError:
    message = "Chủ đề không tồn tại hoặc môn/chủ đề đã bị vô hiệu hóa."
    return AppError(404, "TOPIC_NOT_FOUND", message, {"topic_id": message})


class DocumentRepository(Protocol):
    async def list_subjects(self) -> list[UploadSubject]: ...

    async def find_upload_topic(self, topic_id: int) -> UploadTopic | None: ...

    async def list_documents(self) -> list[DocumentRecord]: ...

    async def create(self, *, topic_id: int, title: str, file_path: str) -> DocumentRecord: ...

    async def find_document(self, document_id: int) -> DocumentRecord | None: ...

    async def finish_processing(
        self,
        document_id: int,
        *,
        chunks: list[str] | None,
        embeddings: list[list[float] | None] | None = None,
    ) -> DocumentRecord | None: ...

    async def set_active(self, document_id: int, *, is_active: bool) -> DocumentRecord | None: ...

    async def list_eligible_chunks(self, topic_id: int) -> list[DocumentChunkRecord]: ...

    async def set_document_active(self, document_id: int, is_active: bool) -> DocumentRecord | None: ...

    async def search_eligible_chunks(self, topic_id: int, terms: tuple[str, ...]) -> list[DocumentChunkRecord]: ...

    async def list_learning_documents(
        self,
        *,
        topic_id: int | None = None,
        subject_id: int | None = None,
        grade_level: str | None = None,
    ) -> list[LearningDocumentRecord]: ...

    async def find_learning_document(self, document_id: int) -> LearningDocumentDetailRecord | None: ...


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
        self._embeddings: dict[int, tuple[tuple[float, ...] | None, ...]] = {}
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

    async def set_document_active(self, document_id: int, is_active: bool) -> DocumentRecord | None:
        document = self._documents.get(document_id)
        if document is None:
            return None
        if is_active and (document.status != "ready" or not self._chunks.get(document_id)):
            raise AppError(409, "DOCUMENT_NOT_READY", "Chỉ bật được tài liệu đã xử lý xong và có nội dung.")
        updated = replace(document, is_active=is_active)
        self._documents[document_id] = updated
        return updated

    async def finish_processing(
        self,
        document_id: int,
        *,
        chunks: list[str] | None,
        embeddings: list[list[float] | None] | None = None,
    ) -> DocumentRecord | None:
        document = self._documents.get(document_id)
        if document is None:
            return None
        if document.status == "ready" and document.chunk_count:
            return document
        if chunks is not None and (not chunks or any(not part.strip() for part in chunks)):
            raise ValueError("Tài liệu sẵn sàng phải có các đoạn văn bản không rỗng.")
        if chunks is not None and embeddings is not None and len(embeddings) != len(chunks):
            raise ValueError("Số lượng embedding không khớp số lượng đoạn văn bản.")
        saved_chunks = tuple(chunks or ())
        saved_embeddings = tuple(
            tuple(vec) if vec is not None else None
            for vec in (embeddings if embeddings is not None else [None] * len(saved_chunks))
        )
        result = replace(
            document, status="ready" if chunks is not None else "error", is_active=False,
            processed_at=datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            chunk_count=len(saved_chunks),
        )
        self._chunks[document_id] = saved_chunks
        self._embeddings[document_id] = saved_embeddings
        self._documents[document_id] = result
        return result

    async def set_active(self, document_id: int, *, is_active: bool) -> DocumentRecord | None:
        try:
            return await self.set_document_active(document_id, is_active)
        except AppError as error:
            if error.code == "DOCUMENT_NOT_READY":
                raise DocumentNotReadyError() from None
            raise

    async def list_eligible_chunks(self, topic_id: int) -> list[DocumentChunkRecord]:
        eligible_docs = sorted(
            (
                doc for doc in self._documents.values()
                if doc.topic_id == topic_id and doc.status == "ready" and doc.is_active is True
            ),
            key=lambda item: item.id,
        )
        results: list[DocumentChunkRecord] = []
        chunk_id = 1
        for doc in eligible_docs:
            doc_embeddings = self._embeddings.get(doc.id, ())
            for index, content in enumerate(self._chunks.get(doc.id, ())):
                embedding = doc_embeddings[index] if index < len(doc_embeddings) else None
                results.append(DocumentChunkRecord(
                    id=chunk_id,
                    document_id=doc.id,
                    document_title=doc.title,
                    topic_id=doc.topic_id,
                    chunk_index=index,
                    content=content,
                    embedding=embedding,
                ))
                chunk_id += 1
        return results

    async def search_eligible_chunks(self, topic_id: int, terms: tuple[str, ...]) -> list[DocumentChunkRecord]:
        if not terms or await self.find_upload_topic(topic_id) is None:
            return []
        matches = []
        for chunk in await self.list_eligible_chunks(topic_id):
            normalized = fold_text(chunk.content)
            if any(term in normalized for term in terms):
                matches.append(chunk)
        return matches

    def _to_learning_record(self, doc: DocumentRecord) -> LearningDocumentRecord | None:
        if doc.status != "ready" or doc.is_active is not True:
            return None
        topic = self._topics.get(doc.topic_id)
        subject = self._subjects.get(topic.subject_id) if topic is not None else None
        if topic is None or subject is None or not topic.is_active or not subject.is_active:
            return None
        return LearningDocumentRecord(
            id=doc.id,
            topic_id=doc.topic_id,
            subject_id=subject.id,
            title=doc.title,
            file_path=doc.file_path,
            source_url=doc.source_url,
            created_at=doc.created_at,
            processed_at=doc.processed_at,
            subject_name=subject.name,
            grade_level=subject.grade_level,
            topic_name=topic.name,
            chapter_name=topic.chapter_name,
            chunk_count=len(self._chunks.get(doc.id, ())),
        )

    async def list_learning_documents(
        self,
        *,
        topic_id: int | None = None,
        subject_id: int | None = None,
        grade_level: str | None = None,
    ) -> list[LearningDocumentRecord]:
        items: list[LearningDocumentRecord] = []
        for doc in self._documents.values():
            record = self._to_learning_record(doc)
            if record is None:
                continue
            if topic_id is not None and record.topic_id != topic_id:
                continue
            if subject_id is not None and record.subject_id != subject_id:
                continue
            if grade_level is not None and record.grade_level != grade_level:
                continue
            items.append(record)
        return sorted(items, key=lambda item: (item.created_at, item.id), reverse=True)

    async def find_learning_document(self, document_id: int) -> LearningDocumentDetailRecord | None:
        doc = self._documents.get(document_id)
        if doc is None:
            return None
        record = self._to_learning_record(doc)
        if record is None:
            return None
        chunks = tuple(
            LearningDocumentChunkRecord(id=index + 1, chunk_index=index, content=content)
            for index, content in enumerate(self._chunks.get(doc.id, ()))
        )
        return LearningDocumentDetailRecord(document=record, chunks=chunks)


class SqlAlchemyDocumentRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._sessions = session_factory

    async def set_document_active(self, document_id: int, is_active: bool) -> DocumentRecord | None:
        return await asyncio.to_thread(self._set_document_active, document_id, is_active)

    def _set_document_active(self, document_id: int, is_active: bool) -> DocumentRecord | None:
        with self._sessions.begin() as db:
            document = db.scalar(select(DocumentModel).where(DocumentModel.id == document_id).with_for_update())
            if document is None:
                return None
            count = db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id))
            if is_active and (document.status != "ready" or not count):
                raise AppError(409, "DOCUMENT_NOT_READY", "Chỉ bật được tài liệu đã xử lý xong và có nội dung.")
            document.is_active = is_active
            topic = db.get(TopicModel, document.topic_id)
            subject = db.get(SubjectModel, topic.subject_id)
            db.flush()
            return self._to_record(document, topic.name, subject.name, count)

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

    async def finish_processing(
        self,
        document_id: int,
        *,
        chunks: list[str] | None,
        embeddings: list[list[float] | None] | None = None,
    ) -> DocumentRecord | None:
        return await asyncio.to_thread(
            self._finish_processing,
            document_id,
            chunks=chunks,
            embeddings=embeddings,
        )

    async def set_active(self, document_id: int, *, is_active: bool) -> DocumentRecord | None:
        return await asyncio.to_thread(self._set_active, document_id, is_active=is_active)

    async def list_eligible_chunks(self, topic_id: int) -> list[DocumentChunkRecord]:
        return await asyncio.to_thread(self._list_eligible_chunks, topic_id)

    async def search_eligible_chunks(self, topic_id: int, terms: tuple[str, ...]) -> list[DocumentChunkRecord]:
        if not terms:
            return []
        return await asyncio.to_thread(self._search_eligible_chunks, topic_id, terms)

    async def list_learning_documents(
        self,
        *,
        topic_id: int | None = None,
        subject_id: int | None = None,
        grade_level: str | None = None,
    ) -> list[LearningDocumentRecord]:
        return await asyncio.to_thread(
            self._list_learning_documents,
            topic_id=topic_id,
            subject_id=subject_id,
            grade_level=grade_level,
        )

    async def find_learning_document(self, document_id: int) -> LearningDocumentDetailRecord | None:
        return await asyncio.to_thread(self._find_learning_document, document_id)

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

    def _finish_processing(
        self,
        document_id: int,
        *,
        chunks: list[str] | None,
        embeddings: list[list[float] | None] | None = None,
    ) -> DocumentRecord | None:
        if chunks is not None and (not chunks or any(not part.strip() for part in chunks)):
            raise ValueError("Tài liệu sẵn sàng phải có các đoạn văn bản không rỗng.")
        if chunks is not None and embeddings is not None and len(embeddings) != len(chunks):
            raise ValueError("Số lượng embedding không khớp số lượng đoạn văn bản.")
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
            chunk_list = chunks or ()
            embedding_list = embeddings if embeddings is not None else [None] * len(chunk_list)
            db.add_all([
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=index,
                    content=content,
                    embedding=embedding_list[index],
                )
                for index, content in enumerate(chunk_list)
            ])
            document.status = "ready" if chunks is not None else "error"
            document.is_active = False
            document.processed_at = datetime.now(timezone.utc)
            # Chunks và trạng thái cùng commit; lỗi ghi sẽ rollback toàn bộ.
            db.flush()
            return self._to_record(document, topic.name, subject.name, len(chunks or ()))

    def _set_active(self, document_id: int, *, is_active: bool) -> DocumentRecord | None:
        try:
            return self._set_document_active(document_id, is_active)
        except AppError as error:
            if error.code == "DOCUMENT_NOT_READY":
                raise DocumentNotReadyError() from None
            raise

    def _list_eligible_chunks(self, topic_id: int) -> list[DocumentChunkRecord]:
        with self._sessions() as db:
            rows = db.execute(
                select(DocumentChunk, DocumentModel.title, DocumentModel.topic_id, DocumentModel.source_url)
                .join(DocumentModel, DocumentModel.id == DocumentChunk.document_id)
                .join(TopicModel, TopicModel.id == DocumentModel.topic_id)
                .join(SubjectModel, SubjectModel.id == TopicModel.subject_id)
                .where(
                    DocumentModel.topic_id == topic_id,
                    DocumentModel.status == "ready",
                    DocumentModel.is_active.is_(True),
                    TopicModel.is_active.is_(True),
                    SubjectModel.is_active.is_(True),
                )
                .order_by(DocumentModel.id, DocumentChunk.chunk_index, DocumentChunk.id)
            )
            return [
                DocumentChunkRecord(
                    id=chunk.id,
                    document_id=chunk.document_id,
                    document_title=title,
                    topic_id=doc_topic_id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    source_url=source_url,
                    embedding=tuple(chunk.embedding) if isinstance(chunk.embedding, list) else None,
                )
                for chunk, title, doc_topic_id, source_url in rows
            ]

    def _search_eligible_chunks(self, topic_id: int, terms: tuple[str, ...]) -> list[DocumentChunkRecord]:
        content = DocumentChunk.content
        contains_term = or_(*(
            content.collate("utf8mb4_0900_ai_ci").like(literal_contains_pattern(term), escape="!")
            for term in terms
        ))
        # LIKE can disagree with Python normalization for decomposed characters or
        # casefold expansions (e.g. ß -> ss). Keep all Unicode candidates so the
        # exact whole-word scorer never loses a valid match. No pre-ranking cap.
        unicode_content = func.length(content) > func.char_length(content)
        with self._sessions() as db:
            rows = db.execute(
                select(DocumentChunk, DocumentModel.title, DocumentModel.topic_id, DocumentModel.source_url)
                .join(DocumentModel, DocumentModel.id == DocumentChunk.document_id)
                .join(TopicModel, TopicModel.id == DocumentModel.topic_id)
                .join(SubjectModel, SubjectModel.id == TopicModel.subject_id)
                .where(
                    DocumentModel.topic_id == topic_id,
                    DocumentModel.status == "ready", DocumentModel.is_active.is_(True),
                    TopicModel.is_active.is_(True), SubjectModel.is_active.is_(True),
                    or_(contains_term, unicode_content),
                )
                .order_by(DocumentModel.id, DocumentChunk.chunk_index, DocumentChunk.id)
            )
            return [DocumentChunkRecord(
                id=chunk.id, document_id=chunk.document_id, document_title=title,
                topic_id=doc_topic_id, chunk_index=chunk.chunk_index, content=chunk.content,
                source_url=source_url,
            ) for chunk, title, doc_topic_id, source_url in rows]

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
    def _learning_document_query():
        count = select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == DocumentModel.id).scalar_subquery()
        return (
            select(DocumentModel, TopicModel, SubjectModel, count)
            .join(TopicModel, TopicModel.id == DocumentModel.topic_id)
            .join(SubjectModel, SubjectModel.id == TopicModel.subject_id)
            .where(
                DocumentModel.status == "ready",
                DocumentModel.is_active.is_(True),
                TopicModel.is_active.is_(True),
                SubjectModel.is_active.is_(True),
            )
        )

    def _list_learning_documents(
        self,
        *,
        topic_id: int | None = None,
        subject_id: int | None = None,
        grade_level: str | None = None,
    ) -> list[LearningDocumentRecord]:
        stmt = self._learning_document_query()
        if topic_id is not None:
            stmt = stmt.where(DocumentModel.topic_id == topic_id)
        if subject_id is not None:
            stmt = stmt.where(TopicModel.subject_id == subject_id)
        if grade_level is not None:
            stmt = stmt.where(SubjectModel.grade_level == grade_level)
        stmt = stmt.order_by(DocumentModel.created_at.desc(), DocumentModel.id.desc())
        with self._sessions() as db:
            rows = db.execute(stmt)
            return [
                self._to_learning_record(document, topic, subject, count)
                for document, topic, subject, count in rows
            ]

    def _find_learning_document(self, document_id: int) -> LearningDocumentDetailRecord | None:
        with self._sessions() as db:
            row = db.execute(
                self._learning_document_query().where(DocumentModel.id == document_id)
            ).first()
            if row is None:
                return None
            document, topic, subject, count = row
            chunk_rows = db.scalars(
                select(DocumentChunk)
                .where(DocumentChunk.document_id == document_id)
                .order_by(DocumentChunk.chunk_index, DocumentChunk.id)
            )
            chunks = tuple(
                LearningDocumentChunkRecord(
                    id=chunk.id,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                )
                for chunk in chunk_rows
            )
            return LearningDocumentDetailRecord(
                document=self._to_learning_record(document, topic, subject, count),
                chunks=chunks,
            )

    @staticmethod
    def _to_learning_record(
        document: DocumentModel,
        topic: TopicModel,
        subject: SubjectModel,
        chunk_count: int = 0,
    ) -> LearningDocumentRecord:
        created_at = document.created_at
        if created_at.tzinfo is None:
            created_at = created_at.replace(tzinfo=timezone.utc)
        return LearningDocumentRecord(
            id=document.id,
            topic_id=document.topic_id,
            subject_id=subject.id,
            title=document.title,
            file_path=document.file_path,
            source_url=document.source_url,
            created_at=created_at.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            processed_at=(
                document.processed_at.replace(tzinfo=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                if document.processed_at is not None else None
            ),
            subject_name=subject.name,
            grade_level=subject.grade_level,
            topic_name=topic.name,
            chapter_name=topic.chapter_name,
            chunk_count=chunk_count,
        )

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
            source_url=document.source_url,
        )
