"""TK-072: Không cho bật nguồn status khác ready; tài liệu tắt không dùng trong chat mới."""

from pathlib import Path

import pytest

from app.repositories.document_repository import (
    InMemoryDocumentRepository,
    SubjectRecord,
    TopicRecord,
)
from app.services.document_retrieval import DocumentRetrievalService
from app.services.document_service import DocumentService
from app.utils.errors import AppError


@pytest.mark.anyio
async def test_cannot_activate_pending_or_error_documents(tmp_path: Path):
    repo = InMemoryDocumentRepository(
        subjects=[SubjectRecord(id=1, name="Toán", grade_level="THPT")],
        topics=[TopicRecord(id=1, subject_id=1, name="Phương trình bậc hai")],
    )
    service = DocumentService(repo, tmp_path)

    pending_doc = await repo.create(topic_id=1, title="Tài liệu pending", file_path="pending.txt")
    with pytest.raises(AppError) as pending_err:
        await service.set_active(pending_doc.id, is_active=True)
    assert pending_err.value.status_code == 409
    assert pending_err.value.code == "DOCUMENT_NOT_READY"
    assert (await repo.find_document(pending_doc.id)).is_active is False

    error_doc = await repo.create(topic_id=1, title="Tài liệu error", file_path="error.txt")
    await repo.finish_processing(error_doc.id, chunks=None)
    with pytest.raises(AppError) as error_err:
        await service.set_active(error_doc.id, is_active=True)
    assert error_err.value.status_code == 409
    assert error_err.value.code == "DOCUMENT_NOT_READY"
    assert (await repo.find_document(error_doc.id)).is_active is False


@pytest.mark.anyio
async def test_ready_document_toggle_controls_eligibility_for_new_chats(tmp_path: Path):
    repo = InMemoryDocumentRepository(
        subjects=[SubjectRecord(id=1, name="Toán", grade_level="THPT")],
        topics=[TopicRecord(id=1, subject_id=1, name="Phương trình bậc hai")],
    )
    service = DocumentService(repo, tmp_path)
    retrieval = DocumentRetrievalService(repo)

    doc = await repo.create(topic_id=1, title="Giáo trình chuẩn", file_path="ready.txt")
    await repo.finish_processing(doc.id, chunks=["Đoạn kiến thức 1"])

    assert await retrieval.list_eligible_chunks(1) == []

    activated = await service.set_active(doc.id, is_active=True)
    assert activated.is_active is True
    assert len(await retrieval.list_eligible_chunks(1)) == 1

    deactivated = await service.set_active(doc.id, is_active=False)
    assert deactivated.is_active is False
    assert await retrieval.list_eligible_chunks(1) == []
