"""TK-045: Chỉ tìm trong documents có is_active=true và status=ready."""

from dataclasses import replace

import pytest

from app.repositories.document_repository import (
    DocumentRecord,
    InMemoryDocumentRepository,
    SubjectRecord,
    TopicRecord,
)
from app.services.document_retrieval import (
    DocumentRetrievalService,
    filter_eligible_documents,
    is_eligible_source,
)


def make_doc(doc_id: int, *, topic_id: int = 1, status: str = "ready", is_active: bool = True) -> DocumentRecord:
    return DocumentRecord(
        id=doc_id,
        topic_id=topic_id,
        title=f"Tài liệu {doc_id}",
        file_path=f"doc-{doc_id}.txt",
        status=status,
        is_active=is_active,
        created_at="2026-11-18T00:00:00Z",
        subject_name="Toán",
        topic_name="Phương trình bậc hai",
        chunk_count=1 if status == "ready" else 0,
    )


@pytest.mark.parametrize("status,is_active,expected", [
    ("ready", True, True),
    ("ready", False, False),
    ("pending", True, False),
    ("pending", False, False),
    ("error", True, False),
    ("error", False, False),
])
def test_is_eligible_source_requires_ready_and_active(status, is_active, expected):
    assert is_eligible_source(make_doc(1, status=status, is_active=is_active)) is expected


def test_filter_eligible_documents_filters_by_status_active_and_topic():
    docs = [
        make_doc(1, topic_id=1, status="ready", is_active=True),
        make_doc(2, topic_id=1, status="ready", is_active=False),
        make_doc(3, topic_id=1, status="pending", is_active=True),
        make_doc(4, topic_id=1, status="error", is_active=True),
        make_doc(5, topic_id=2, status="ready", is_active=True),
    ]
    assert [d.id for d in filter_eligible_documents(docs)] == [1, 5]
    assert [d.id for d in filter_eligible_documents(docs, topic_id=1)] == [1]
    assert [d.id for d in filter_eligible_documents(docs, topic_id=2)] == [5]
    assert filter_eligible_documents(docs, topic_id=999) == []


@pytest.mark.anyio
async def test_retrieval_service_only_returns_chunks_from_ready_and_active_documents():
    repo = InMemoryDocumentRepository(
        subjects=[SubjectRecord(id=1, name="Toán", grade_level="THPT")],
        topics=[
            TopicRecord(id=1, subject_id=1, name="Phương trình bậc hai"),
            TopicRecord(id=2, subject_id=1, name="Hàm số"),
        ],
    )
    active_ready = await repo.create(topic_id=1, title="Nguồn hợp lệ", file_path="ok.txt")
    await repo.finish_processing(active_ready.id, chunks=["Đoạn 1 hợp lệ", "Đoạn 2 hợp lệ"])
    repo._documents[active_ready.id] = replace(repo._documents[active_ready.id], is_active=True)

    inactive_ready = await repo.create(topic_id=1, title="Nguồn chưa bật", file_path="off.txt")
    await repo.finish_processing(inactive_ready.id, chunks=["Không được trả về"])

    pending_doc = await repo.create(topic_id=1, title="Nguồn chờ", file_path="pending.txt")
    repo._documents[pending_doc.id] = replace(repo._documents[pending_doc.id], is_active=True)
    repo._chunks[pending_doc.id] = ("Đoạn pending không hợp lệ",)

    error_doc = await repo.create(topic_id=1, title="Nguồn lỗi", file_path="err.txt")
    await repo.finish_processing(error_doc.id, chunks=None)
    repo._documents[error_doc.id] = replace(repo._documents[error_doc.id], is_active=True)

    other_topic = await repo.create(topic_id=2, title="Nguồn chủ đề khác", file_path="other.txt")
    await repo.finish_processing(other_topic.id, chunks=["Đoạn chủ đề khác"])
    repo._documents[other_topic.id] = replace(repo._documents[other_topic.id], is_active=True)

    service = DocumentRetrievalService(repo)
    chunks = await service.list_eligible_chunks(1)
    assert [(c.document_id, c.chunk_index, c.content) for c in chunks] == [
        (active_ready.id, 0, "Đoạn 1 hợp lệ"),
        (active_ready.id, 1, "Đoạn 2 hợp lệ"),
    ]
    assert await service.list_eligible_chunks(0) == []
    assert await service.list_eligible_chunks(-1) == []
