"""TK-045: Lọc nguồn hợp lệ — chỉ dùng tài liệu có status='ready' và is_active=True."""

from __future__ import annotations

from collections.abc import Iterable

from app.repositories.document_repository import DocumentChunkRecord, DocumentRecord, DocumentRepository


def is_eligible_source(document: DocumentRecord) -> bool:
    """Chỉ tài liệu đã xử lý xong (ready) và đang bật (is_active=True) mới hợp lệ."""
    return document.status == "ready" and document.is_active is True


def filter_eligible_documents(
    documents: Iterable[DocumentRecord], *, topic_id: int | None = None,
) -> list[DocumentRecord]:
    return [
        doc for doc in documents
        if is_eligible_source(doc) and (topic_id is None or doc.topic_id == topic_id)
    ]


class DocumentRetrievalService:
    """Cung cấp các đoạn văn bản từ nguồn hợp lệ (status='ready' và is_active=True) theo chủ đề."""

    def __init__(self, repository: DocumentRepository) -> None:
        self._repository = repository

    async def list_eligible_chunks(self, topic_id: int) -> list[DocumentChunkRecord]:
        if not isinstance(topic_id, int) or isinstance(topic_id, bool) or topic_id <= 0:
            return []
        return await self._repository.list_eligible_chunks(topic_id)
