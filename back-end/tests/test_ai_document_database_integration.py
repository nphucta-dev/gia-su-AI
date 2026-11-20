"""Source publication and retrieval use only the isolated random MySQL fixture."""

import pytest
from sqlalchemy import select

from app.models import Document, DocumentChunk
from app.repositories.document_repository import SqlAlchemyDocumentRepository
from app.services.document_retrieval import DocumentRetrievalService
from app.utils.errors import AppError
from test_database_integration import database, make_catalog

pytestmark = pytest.mark.anyio


def make_topic(sessions):
    with sessions.begin() as db:
        _, _, topic = make_catalog(db)
        return topic.id


def chunk_snapshot(sessions, document_id):
    with sessions() as db:
        return tuple(tuple(row) for row in db.execute(
            select(DocumentChunk.id, DocumentChunk.chunk_index, DocumentChunk.content)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        ))


@pytest.mark.parametrize("status", ["pending", "error", "ready"])
async def test_mysql_source_without_processed_chunks_cannot_be_published(database, status):
    _, sessions = database
    topic_id = make_topic(sessions)
    repository = SqlAlchemyDocumentRepository(sessions)
    record = await repository.create(topic_id=topic_id, title="Chưa có nội dung", file_path="unused.txt")
    if status != "pending":
        with sessions.begin() as db:
            db.get(Document, record.id).status = status

    with pytest.raises(AppError) as caught:
        await repository.set_document_active(record.id, True)

    assert caught.value.status_code == 409
    assert caught.value.code == "DOCUMENT_NOT_READY"
    persisted = await repository.find_document(record.id)
    assert persisted.status == status and persisted.is_active is False
    assert chunk_snapshot(sessions, record.id) == ()
    assert await repository.list_eligible_chunks(topic_id) == []
    assert (await DocumentRetrievalService(repository).search(topic_id, "đạo hàm")).matches == ()


async def test_mysql_publication_controls_retrieval_without_deleting_processed_chunks(database):
    _, sessions = database
    topic_id = make_topic(sessions)
    other_topic_id = make_topic(sessions)
    repository = SqlAlchemyDocumentRepository(sessions)
    retrieval = DocumentRetrievalService(repository)
    record = await repository.create(topic_id=topic_id, title="Chuyên đề đạo hàm", file_path="unused.txt")
    content = ["Đạo hàm của hàm số bậc hai.", "Ứng dụng đạo hàm để tìm cực trị."]
    ready = await repository.finish_processing(record.id, chunks=content)
    original_chunks = chunk_snapshot(sessions, record.id)
    assert ready.status == "ready" and ready.processed_at is not None and not ready.is_active
    assert len(original_chunks) == 2
    assert await repository.list_eligible_chunks(topic_id) == []
    assert (await retrieval.search(topic_id, "đạo hàm")).matches == ()

    published = await repository.set_document_active(record.id, True)
    assert published.is_active and published.chunk_count == 2
    assert (await repository.find_document(record.id)).is_active
    eligible = await repository.list_eligible_chunks(topic_id)
    assert {chunk.id for chunk in eligible} == {row[0] for row in original_chunks}
    matches = (await retrieval.search(topic_id, "đạo hàm")).matches
    assert {match.chunk.id for match in matches} == {row[0] for row in original_chunks}
    assert all(match.chunk.document_id == record.id for match in matches)
    assert (await retrieval.search(other_topic_id, "đạo hàm")).matches == ()

    withdrawn = await repository.set_document_active(record.id, False)
    assert not withdrawn.is_active and withdrawn.status == "ready"
    assert withdrawn.processed_at == ready.processed_at
    assert not (await repository.find_document(record.id)).is_active
    assert await repository.list_eligible_chunks(topic_id) == []
    assert (await retrieval.search(topic_id, "đạo hàm")).matches == ()
    assert chunk_snapshot(sessions, record.id) == original_chunks

    await repository.set_document_active(record.id, True)
    assert chunk_snapshot(sessions, record.id) == original_chunks
    assert len((await retrieval.search(topic_id, "đạo hàm")).matches) == 2
