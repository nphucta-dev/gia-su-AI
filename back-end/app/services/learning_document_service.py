"""Nghiệp vụ xem tài liệu học tập đang mở cho người học (LEARNER và ADMIN)."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.document_repository import (
    DocumentRepository,
    LearningDocumentDetailRecord,
    LearningDocumentRecord,
    missing_topic_error,
)
from app.schemas.learning_document import (
    LearningDocumentChunkItem,
    LearningDocumentDetail,
    LearningDocumentItem,
)
from app.services.document_service import database_unavailable
from app.utils.errors import AppError
from app.utils.keywords import fold_text

_FILE_TYPES: dict[str, tuple[Literal["pdf", "txt"], str]] = {
    ".pdf": ("pdf", "application/pdf"),
    ".txt": ("txt", "text/plain; charset=utf-8"),
}


@dataclass(frozen=True)
class ResolvedDocumentFile:
    path: Path
    media_type: str
    file_name: str


class LearningDocumentService:
    def __init__(self, repository: DocumentRepository, upload_dir: Path) -> None:
        self.repository = repository
        self.upload_dir = upload_dir.resolve()

    async def list_documents(
        self,
        *,
        topic_id: int | None = None,
        subject_id: int | None = None,
        grade_level: str | None = None,
        query: str | None = None,
    ) -> list[LearningDocumentItem]:
        cleaned_grade = grade_level.strip() if grade_level is not None else None
        if cleaned_grade == "":
            cleaned_grade = None
        try:
            if topic_id is not None:
                topic = await self.repository.find_upload_topic(topic_id)
                if topic is None:
                    raise missing_topic_error()
            records = await self.repository.list_learning_documents(
                topic_id=topic_id,
                subject_id=subject_id,
                grade_level=cleaned_grade,
            )
        except SQLAlchemyError:
            raise database_unavailable() from None

        cleaned_query = fold_text(query) if query else ""
        if cleaned_query:
            records = [
                record
                for record in records
                if cleaned_query in fold_text(
                    f"{record.title} {record.topic_name} {record.chapter_name} {record.subject_name}"
                )
            ]

        return await asyncio.to_thread(lambda: [self._to_item(record) for record in records])

    async def list_topic_documents(self, topic_id: int) -> list[LearningDocumentItem]:
        return await self.list_documents(topic_id=topic_id)

    async def get_document(self, document_id: int) -> LearningDocumentDetail:
        detail = await self._load_detail(document_id)
        return await asyncio.to_thread(self._to_detail, detail)

    async def get_document_file(self, document_id: int) -> ResolvedDocumentFile:
        detail = await self._load_detail(document_id)
        return await asyncio.to_thread(self._resolve_file, detail.document)

    async def _load_detail(self, document_id: int) -> LearningDocumentDetailRecord:
        try:
            detail = await self.repository.find_learning_document(document_id)
        except SQLAlchemyError:
            raise database_unavailable() from None
        if detail is None:
            raise AppError(404, "DOCUMENT_NOT_FOUND", "Không tìm thấy tài liệu học tập.")
        return detail

    def _safe_file_path(self, file_path: str) -> Path | None:
        relative = Path(file_path)
        if not file_path or relative.is_absolute() or relative.name != file_path:
            return None
        candidate = self.upload_dir / relative
        try:
            if candidate.is_symlink():
                return None
            resolved = candidate.resolve()
            if resolved.parent != self.upload_dir or not resolved.is_file():
                return None
            return resolved
        except OSError:
            return None

    def _resolve_file(self, record: LearningDocumentRecord) -> ResolvedDocumentFile:
        resolved = self._safe_file_path(record.file_path)
        if resolved is None:
            raise AppError(404, "DOCUMENT_FILE_NOT_FOUND", "Không tìm thấy tệp gốc của tài liệu.")
        extension = resolved.suffix.lower()
        file_meta = _FILE_TYPES.get(extension)
        if file_meta is None:
            raise AppError(404, "DOCUMENT_FILE_NOT_FOUND", "Định dạng tệp tài liệu không được hỗ trợ.")
        _, media_type = file_meta
        display_name = self._display_name(record.title, extension)
        return ResolvedDocumentFile(path=resolved, media_type=media_type, file_name=display_name)

    @staticmethod
    def _display_name(title: str, extension: str) -> str:
        clean_title = title.replace("\r", " ").replace("\n", " ").strip() or "tai-lieu"
        if extension and not clean_title.lower().endswith(extension):
            return clean_title + extension
        return clean_title

    def _to_item(self, record: LearningDocumentRecord) -> LearningDocumentItem:
        resolved = self._safe_file_path(record.file_path)
        size: int | None = None
        if resolved is not None:
            try:
                size = resolved.stat().st_size
            except OSError:
                size = None
        extension = Path(record.file_path).suffix.lower()
        file_meta = _FILE_TYPES.get(extension)
        file_type: Literal["pdf", "txt", "unknown"] = file_meta[0] if file_meta is not None else "unknown"
        display_ext = extension if file_meta is not None else ""
        return LearningDocumentItem(
            id=record.id,
            topic_id=record.topic_id,
            subject_id=record.subject_id,
            title=record.title,
            subject_name=record.subject_name,
            grade_level=record.grade_level,
            topic_name=record.topic_name,
            chapter_name=record.chapter_name,
            source_url=record.source_url,
            file_name=self._display_name(record.title, display_ext),
            file_type=file_type,
            size_bytes=size,
            chunk_count=record.chunk_count,
            created_at=record.created_at,
            processed_at=record.processed_at,
        )

    def _to_detail(self, detail: LearningDocumentDetailRecord) -> LearningDocumentDetail:
        item = self._to_item(detail.document)
        chunks = [
            LearningDocumentChunkItem(
                id=chunk.id,
                chunk_index=chunk.chunk_index,
                content=chunk.content,
            )
            for chunk in detail.chunks
        ]
        full_content = "\n\n".join(chunk.content for chunk in detail.chunks)
        return LearningDocumentDetail(
            **item.model_dump(),
            content=full_content,
            chunks=chunks,
        )
