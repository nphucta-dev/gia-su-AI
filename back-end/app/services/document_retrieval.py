"""TK-045 / TK-044 / TK-046: Lọc nguồn hợp lệ, tra cứu từ khóa và tìm kiếm vector."""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from app.repositories.document_repository import DocumentChunkRecord, DocumentRecord, DocumentRepository
from app.services.embedding_client import (
    EMBEDDING_DIMENSIONS,
    EmbeddingError,
    EmbeddingProvider,
    cosine_similarity,
    validate_embedding,
)
from app.utils.errors import AppError
from app.utils.keywords import keyword_score, parse_query

logger = logging.getLogger(__name__)

SearchMode = Literal["keyword", "vector", "hybrid"]


@dataclass(frozen=True)
class RankedDocumentChunk:
    chunk: DocumentChunkRecord
    score: int
    similarity: float | None = None


@dataclass(frozen=True)
class ChunkSearchResult:
    topic_id: int
    query: str
    limit: int
    matches: tuple[RankedDocumentChunk, ...]
    search_mode: str = "keyword"


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

    def __init__(
        self,
        repository: DocumentRepository,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self._repository = repository
        self._embedding_provider = embedding_provider

    async def list_eligible_chunks(self, topic_id: int) -> list[DocumentChunkRecord]:
        if not isinstance(topic_id, int) or isinstance(topic_id, bool) or topic_id <= 0:
            return []
        return await self._repository.list_eligible_chunks(topic_id)

    def _validate_search_inputs(self, topic_id: int, query: str, limit: int) -> tuple[str, tuple[str, ...]]:
        if isinstance(topic_id, bool) or not isinstance(topic_id, int) or not 1 <= topic_id <= 2**31 - 1:
            raise AppError(422, "VALIDATION_ERROR", "Mã chủ đề không hợp lệ.")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 20:
            raise AppError(422, "VALIDATION_ERROR", "Số đoạn cần tìm phải từ 1 đến 20.")
        try:
            return parse_query(query)
        except ValueError:
            raise AppError(422, "INVALID_SEARCH_QUERY", "Nhập từ 1 đến 20 từ khóa, tối đa 400 ký tự.") from None

    async def _search_keyword(
        self,
        topic_id: int,
        cleaned: str,
        terms: tuple[str, ...],
        *,
        limit: int,
    ) -> ChunkSearchResult:
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
            topic_id=topic_id,
            query=cleaned,
            limit=limit,
            matches=tuple(RankedDocumentChunk(chunk, score) for score, _, chunk in ranked[:limit]),
            search_mode="keyword",
        )

    async def search_vector(
        self,
        topic_id: int,
        query: str,
        *,
        limit: int = 5,
        min_similarity: float = 0.0,
    ) -> ChunkSearchResult:
        """Tìm kiếm theo độ tương đồng cosine trên embedding 768 chiều; fallback keyword nếu chưa có dữ liệu/provider."""
        cleaned, terms = self._validate_search_inputs(topic_id, query, limit)
        if self._embedding_provider is None or not self._embedding_provider.is_configured:
            return await self._search_keyword(topic_id, cleaned, terms, limit=limit)
        try:
            topic = await self._repository.find_upload_topic(topic_id)
            if topic is None:
                raise AppError(404, "TOPIC_NOT_FOUND", "Chủ đề không tồn tại hoặc chưa được mở.")
            eligible_chunks = await self._repository.list_eligible_chunks(topic_id)
        except SQLAlchemyError:
            raise AppError(503, "SOURCES_UNAVAILABLE", "Chưa thể tra cứu tài liệu. Vui lòng thử lại sau.") from None

        embedded_chunks = [
            chunk
            for chunk in eligible_chunks
            if chunk.embedding is not None and len(chunk.embedding) == EMBEDDING_DIMENSIONS
        ]
        if not embedded_chunks:
            return await self._search_keyword(topic_id, cleaned, terms, limit=limit)

        try:
            vectors = await self._embedding_provider.embed_texts([cleaned])
            if not vectors:
                return await self._search_keyword(topic_id, cleaned, terms, limit=limit)
            query_vector = validate_embedding(vectors[0])
        except (EmbeddingError, Exception) as exc:
            logger.warning("Không thể tạo embedding cho câu truy vấn, fallback keyword: %s", exc)
            return await self._search_keyword(topic_id, cleaned, terms, limit=limit)

        scored: list[tuple[float, int, DocumentChunkRecord]] = []
        for chunk in embedded_chunks:
            assert chunk.embedding is not None
            sim = cosine_similarity(query_vector, chunk.embedding)
            if sim >= min_similarity:
                matched, _ = keyword_score(chunk.content, terms)
                scored.append((round(sim, 6), matched, chunk))
        scored.sort(key=lambda item: (-item[0], -item[1], item[2].document_id, item[2].chunk_index, item[2].id))
        return ChunkSearchResult(
            topic_id=topic_id,
            query=cleaned,
            limit=limit,
            matches=tuple(
                RankedDocumentChunk(chunk, max(matched, 1), similarity=sim)
                for sim, matched, chunk in scored[:limit]
            ),
            search_mode="vector",
        )

    async def search(
        self,
        topic_id: int,
        query: str,
        *,
        limit: int = 5,
        mode: SearchMode = "keyword",
    ) -> ChunkSearchResult:
        cleaned, terms = self._validate_search_inputs(topic_id, query, limit)
        if mode == "keyword":
            return await self._search_keyword(topic_id, cleaned, terms, limit=limit)
        if mode == "vector":
            return await self.search_vector(topic_id, cleaned, limit=limit)
        if mode == "hybrid":
            vector_result = await self.search_vector(topic_id, cleaned, limit=limit)
            if vector_result.search_mode != "vector":
                return vector_result
            keyword_result = await self._search_keyword(topic_id, cleaned, terms, limit=limit)
            combined: dict[int, tuple[float, int, float | None, DocumentChunkRecord]] = {}
            for item in vector_result.matches:
                sim = item.similarity or 0.0
                combined[item.chunk.id] = (sim * 0.7, item.score, sim, item.chunk)
            max_kw = max((item.score for item in keyword_result.matches), default=0)
            for item in keyword_result.matches:
                kw_norm = (item.score / max_kw) if max_kw > 0 else 0.0
                existing = combined.get(item.chunk.id)
                if existing is not None:
                    combined[item.chunk.id] = (
                        round(existing[0] + kw_norm * 0.3, 6),
                        max(existing[1], item.score),
                        existing[2],
                        item.chunk,
                    )
                else:
                    combined[item.chunk.id] = (round(kw_norm * 0.3, 6), item.score, None, item.chunk)
            ordered = sorted(
                combined.values(),
                key=lambda row: (-row[0], -row[1], row[3].document_id, row[3].chunk_index, row[3].id),
            )
            return ChunkSearchResult(
                topic_id=topic_id,
                query=cleaned,
                limit=limit,
                matches=tuple(
                    RankedDocumentChunk(chunk, score, similarity=sim)
                    for _, score, sim, chunk in ordered[:limit]
                ),
                search_mode="hybrid",
            )
        raise AppError(422, "VALIDATION_ERROR", "Chế độ tìm kiếm chỉ hỗ trợ keyword, vector hoặc hybrid.")
