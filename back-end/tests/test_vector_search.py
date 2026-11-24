"""TK-046: Kiểm thử tạo embedding và tìm kiếm vector (kèm fallback keyword)."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.repositories.document_repository import (
    InMemoryDocumentRepository,
    SubjectRecord,
    TopicRecord,
)
from app.repositories.user_repository import InMemoryUserRepository
from app.services.document_retrieval import DocumentRetrievalService
from app.services.document_service import DocumentService
from app.services.embedding_client import (
    EMBEDDING_DIMENSIONS,
    EmbeddingError,
    cosine_similarity,
    validate_embedding,
)
from app.services.token_service import TokenService
from app.utils.password import hash_password


def _unit_vector(primary_index: int, secondary_index: int | None = None, secondary_weight: float = 0.0) -> list[float]:
    vec = [0.0] * EMBEDDING_DIMENSIONS
    vec[primary_index] = 1.0
    if secondary_index is not None:
        vec[secondary_index] = secondary_weight
    return vec


class FakeEmbeddingProvider:
    def __init__(self, mapping: dict[str, list[float]], *, configured: bool = True, fail: bool = False) -> None:
        self._mapping = mapping
        self._configured = configured
        self._fail = fail
        self.calls: list[list[str]] = []

    @property
    def is_configured(self) -> bool:
        return self._configured

    async def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self._fail:
            raise EmbeddingError("Dịch vụ embedding tạm thời không khả dụng.")
        result: list[list[float]] = []
        for text in texts:
            lowered = text.lower()
            matched = None
            for key, vector in self._mapping.items():
                if key in lowered:
                    matched = vector
                    break
            result.append(matched or _unit_vector(767))
        return result


def test_validate_embedding_and_cosine_similarity() -> None:
    vec_a = validate_embedding(_unit_vector(0))
    vec_b = validate_embedding(_unit_vector(0, 1, 1.0))
    vec_c = validate_embedding(_unit_vector(2))

    assert len(vec_a) == EMBEDDING_DIMENSIONS
    assert cosine_similarity(vec_a, vec_a) == pytest.approx(1.0)
    assert cosine_similarity(vec_a, vec_b) == pytest.approx(0.70710678, rel=1e-5)
    assert cosine_similarity(vec_a, vec_c) == pytest.approx(0.0)

    with pytest.raises(EmbeddingError):
        validate_embedding([1.0, 2.0])
    with pytest.raises(EmbeddingError):
        validate_embedding([0.0] * EMBEDDING_DIMENSIONS)
    with pytest.raises(EmbeddingError):
        validate_embedding([float("nan")] + [0.0] * (EMBEDDING_DIMENSIONS - 1))


def test_document_process_generates_embeddings_and_falls_back_on_error(tmp_path: Path) -> None:
    repo = InMemoryDocumentRepository(
        subjects=[SubjectRecord(1, "Toán", "10")],
        topics=[TopicRecord(10, 1, "Hàm số", "Chương 1")],
    )
    file_ok = tmp_path / "doc_ok.txt"
    file_ok.write_text("Định nghĩa hàm số bậc nhất và đồ thị.", encoding="utf-8")

    provider = FakeEmbeddingProvider({"hàm số": _unit_vector(0)})
    service = DocumentService(repo, tmp_path, embedding_provider=provider)

    async def _run() -> None:
        doc = await repo.create(topic_id=10, title="Bài 1", file_path="doc_ok.txt")
        processed = await service.process(doc.id)
        assert processed.status == "ready"
        assert processed.chunk_count == 1
        await repo.set_document_active(doc.id, True)
        chunks = await repo.list_eligible_chunks(10)
        assert len(chunks) == 1
        assert chunks[0].embedding is not None
        assert len(chunks[0].embedding) == EMBEDDING_DIMENSIONS

        # Khi embedding lỗi, tài liệu vẫn phải ready để không chặn keyword retrieval.
        file_fail = tmp_path / "doc_fail.txt"
        file_fail.write_text("Phương trình bậc hai một ẩn.", encoding="utf-8")
        failing_service = DocumentService(repo, tmp_path, embedding_provider=FakeEmbeddingProvider({}, fail=True))
        doc2 = await repo.create(topic_id=10, title="Bài 2", file_path="doc_fail.txt")
        processed2 = await failing_service.process(doc2.id)
        assert processed2.status == "ready"
        assert processed2.chunk_count == 1
        await repo.set_document_active(doc2.id, True)
        chunks_after = await repo.list_eligible_chunks(10)
        doc2_chunks = [c for c in chunks_after if c.document_id == doc2.id]
        assert len(doc2_chunks) == 1
        assert doc2_chunks[0].embedding is None

    asyncio.run(_run())


def test_vector_search_ranks_by_cosine_and_respects_eligibility() -> None:
    repo = InMemoryDocumentRepository(
        subjects=[SubjectRecord(1, "Vật lý", "10")],
        topics=[TopicRecord(10, 1, "Động học", "Chương 1"), TopicRecord(11, 1, "Động lực học", "Chương 2")],
    )
    provider = FakeEmbeddingProvider({
        "vận tốc": _unit_vector(0),
        "quãng đường": _unit_vector(0, 1, 0.5),
        "nhiệt độ": _unit_vector(5),
        "tốc độ chuyển động": _unit_vector(0),
    })
    retrieval = DocumentRetrievalService(repo, embedding_provider=provider)

    async def _run() -> None:
        doc_active = await repo.create(topic_id=10, title="Chuyển động thẳng", file_path="a.txt")
        await repo.finish_processing(
            doc_active.id,
            chunks=["Công thức tính nhiệt độ.", "Khái niệm vận tốc trung bình.", "Quãng đường đi được."],
            embeddings=[_unit_vector(5), _unit_vector(0), _unit_vector(0, 1, 0.5)],
        )
        await repo.set_document_active(doc_active.id, True)

        # Tài liệu chưa bật (is_active=False) không được xuất hiện.
        doc_inactive = await repo.create(topic_id=10, title="Bản nháp", file_path="b.txt")
        await repo.finish_processing(
            doc_inactive.id,
            chunks=["Vận tốc tức thời."],
            embeddings=[_unit_vector(0)],
        )

        # Tài liệu thuộc chủ đề khác không được xuất hiện.
        doc_other_topic = await repo.create(topic_id=11, title="Lực ma sát", file_path="c.txt")
        await repo.finish_processing(
            doc_other_topic.id,
            chunks=["Vận tốc của vật chịu lực."],
            embeddings=[_unit_vector(0)],
        )
        await repo.set_document_active(doc_other_topic.id, True)

        result = await retrieval.search(10, "tốc độ chuyển động", limit=2, mode="vector")
        assert result.search_mode == "vector"
        assert len(result.matches) == 2
        assert result.matches[0].chunk.content == "Khái niệm vận tốc trung bình."
        assert result.matches[0].similarity == pytest.approx(1.0)
        assert result.matches[1].chunk.content == "Quãng đường đi được."
        assert result.matches[1].similarity is not None
        assert result.matches[0].similarity > result.matches[1].similarity

    asyncio.run(_run())


def test_vector_search_falls_back_to_keyword_when_unavailable() -> None:
    repo = InMemoryDocumentRepository(
        subjects=[SubjectRecord(1, "Toán", "10")],
        topics=[TopicRecord(10, 1, "Phương trình", "Chương 1")],
    )

    async def _run() -> None:
        doc = await repo.create(topic_id=10, title="Đại số", file_path="a.txt")
        await repo.finish_processing(doc.id, chunks=["Giải phương trình bậc nhất một ẩn."])
        await repo.set_document_active(doc.id, True)

        # Không có provider -> fallback keyword.
        retrieval_no_provider = DocumentRetrievalService(repo, embedding_provider=None)
        res1 = await retrieval_no_provider.search(10, "phuong trinh", mode="vector")
        assert res1.search_mode == "keyword"
        assert len(res1.matches) == 1

        # Có provider nhưng chunk chưa có embedding -> fallback keyword.
        retrieval_no_data = DocumentRetrievalService(
            repo,
            embedding_provider=FakeEmbeddingProvider({"phuong trinh": _unit_vector(0)}),
        )
        res2 = await retrieval_no_data.search(10, "phuong trinh", mode="vector")
        assert res2.search_mode == "keyword"
        assert len(res2.matches) == 1

    asyncio.run(_run())


def test_api_chunk_search_supports_vector_and_hybrid_modes(tmp_path: Path) -> None:
    users = InMemoryUserRepository()
    docs = InMemoryDocumentRepository(
        subjects=[SubjectRecord(1, "Toán", "10")],
        topics=[TopicRecord(10, 1, "Phương trình", "Chương 1")],
    )
    provider = FakeEmbeddingProvider({
        "nghiệm kép": _unit_vector(0),
        "biệt thức delta": _unit_vector(0, 1, 0.2),
    })
    tokens = TokenService(secret="t" * 32, issuer="gia-su-ai", access_token_minutes=30)
    app = create_app(
        user_repository=users,
        document_repository=docs,
        token_service=tokens,
        upload_dir=tmp_path,
        embedding_provider=provider,
    )

    async def _seed() -> str:
        user = await users.create(
            email="learner@example.com",
            name="Người Học",
            password_hash=hash_password("MatKhau123!"),
            role="LEARNER",
        )
        doc = await docs.create(topic_id=10, title="Phương trình bậc hai", file_path="pt.txt")
        await docs.finish_processing(
            doc.id,
            chunks=["Khi biệt thức delta bằng 0 thì phương trình có nghiệm kép."],
            embeddings=[_unit_vector(0)],
        )
        await docs.set_document_active(doc.id, True)
        return tokens.create_access_token(user.id).access_token

    access_token = asyncio.run(_seed())
    client = TestClient(app)

    response = client.get(
        "/api/catalog/topics/10/chunks",
        params={"q": "biệt thức delta", "mode": "vector", "limit": 5},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["searchMode"] == "vector"
    assert len(body["chunks"]) == 1
    assert body["chunks"][0]["similarity"] is not None
    assert body["chunks"][0]["similarity"] > 0.9

    hybrid_resp = client.get(
        "/api/catalog/topics/10/chunks",
        params={"q": "biệt thức delta", "mode": "hybrid", "limit": 5},
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert hybrid_resp.status_code == 200
    assert hybrid_resp.json()["searchMode"] == "hybrid"
