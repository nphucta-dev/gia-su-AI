"""TK-045: Lọc nguồn hợp lệ — chỉ dùng tài liệu có status='ready' và is_active=True."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.document_repository import DocumentChunkRecord, DocumentRecord, DocumentRepository
from app.utils.errors import AppError
from app.utils.keywords import keyword_score, parse_query


@dataclass(frozen=True)
class RankedDocumentChunk:
    chunk: DocumentChunkRecord
    score: int


@dataclass(frozen=True)
class ChunkSearchResult:
    topic_id: int
    query: str
    limit: int
    matches: tuple[RankedDocumentChunk, ...]


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

    async def search(self, topic_id: int, query: str, *, limit: int = 5) -> ChunkSearchResult:
        if isinstance(topic_id, bool) or not isinstance(topic_id, int) or not 1 <= topic_id <= 2**31 - 1:
            raise AppError(422, "VALIDATION_ERROR", "Mã chủ đề không hợp lệ.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise AppError(422, "VALIDATION_ERROR", "Số đoạn cần tìm phải từ 1 đến 20.")
        try:
            cleaned, terms = parse_query(query)
        except ValueError:
            raise AppError(422, "INVALID_SEARCH_QUERY", "Nhập từ 1 đến 20 từ khóa, tối đa 400 ký tự.") from None
        try:
            topic = await self._repository.find_upload_topic(topic_id)
            if topic is None:
                raise AppError(404, "TOPIC_NOT_FOUND", "Chủ đề không tồn tại hoặc chưa được mở.")
            candidates = await self._repository.search_eligible_chunks(topic_id, terms)
        except SQLAlchemyError:
            raise AppError(503, "SOURCES_UNAVAILABLE", "Chưa thể tra cứu tài liệu. Vui lòng thử lại sau.") from None
        ranked = []
        for chunk in candidates:
            matched, occurrences = keyword_score(chunk.content, terms)
            if matched:
                ranked.append((matched, occurrences, chunk))
        # Apply the limit only after matching/ranking the complete eligible candidates.
        ranked.sort(key=lambda item: (-item[0], -item[1], item[2].document_id, item[2].chunk_index, item[2].id))
        return ChunkSearchResult(
            topic_id=topic_id, query=cleaned, limit=limit,
            matches=tuple(RankedDocumentChunk(chunk, score) for score, _, chunk in ranked[:limit]),
        )
