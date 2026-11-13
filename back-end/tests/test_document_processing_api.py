"""Xử lý tài liệu thật qua API, dùng kho riêng và file tạm để không sửa dữ liệu dự án."""

import asyncio
from dataclasses import replace
from io import BytesIO
from unittest.mock import patch

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from app.repositories.document_repository import InMemoryDocumentRepository
from app.services.document_text import extract_document_text
from test_document_upload_api import URL, api, make_documents, upload_data

pytestmark = pytest.mark.anyio


def text_pdf(text="Quadratic formula and worked examples.", *, encrypted=False, blank=False):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    if not blank:
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)}),
        })
        escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream = DecodedStreamObject()
        stream.set_data(f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii"))
        page[NameObject("/Contents")] = writer._add_object(stream)
    if encrypted:
        writer.encrypt("document-test-password")
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


async def pending_document(state, *, filename="legacy.txt", content=b"Legacy text to process"):
    state.storage.mkdir(exist_ok=True)
    path = state.storage / filename
    path.write_bytes(content)
    record = await state.documents.create(topic_id=1, title="Tài liệu chờ xử lý", file_path=filename)
    return record, path


async def process(state, document_id, *, headers=None):
    return await state.client.post(
        f"{URL}/{document_id}/process",
        headers=state.admin_headers if headers is None else headers,
    )


async def test_txt_upload_extracts_vietnamese_bom_and_persists_ordered_chunks(tmp_path):
    paragraphs = [f"DOC{index:04d} Nội dung về hàm số và phương trình bậc hai." for index in range(240)]
    content = ("\ufeffMở đầu tài liệu.\r\n\r\n" + "\r\n\r\n".join(paragraphs) + "\r\nĐoạn kết.").encode("utf-8")
    async with api(tmp_path) as state:
        response = await state.client.post(URL, headers=state.admin_headers, **upload_data(content=content))
        assert response.status_code == 201
        document = response.json()["document"]
        chunks = state.documents._chunks[document["id"]]
        assert document["status"] == "ready" and document["isActive"] is False
        assert document["chunkCount"] == len(chunks) > 1
        assert document["processedAt"].endswith("Z")
        assert all(chunk.strip() and len(chunk) <= 1000 for chunk in chunks)
        assert chunks[0].startswith("Mở đầu tài liệu.")
        assert "Đoạn kết." in chunks[-1]
        joined = "\n".join(chunks)
        assert "\ufeff" not in joined and "\r" not in joined
        for index in range(240):
            assert f"DOC{index:04d}" in joined
        listing = await state.client.get(URL, headers=state.admin_headers)
        assert listing.json()["documents"] == [document]


async def test_real_text_pdf_upload_reaches_ready_with_extracted_content(tmp_path):
    async with api(tmp_path) as state:
        response = await state.client.post(URL, headers=state.admin_headers, **upload_data(
            filename="lesson.pdf", mime="application/pdf", content=text_pdf("Algebra and quadratic formula. " * 90),
        ))
        assert response.status_code == 201
        document = response.json()["document"]
        assert document["status"] == "ready" and document["isActive"] is False
        assert document["chunkCount"] > 1 and document["processedAt"].endswith("Z")
        assert "quadratic formula" in " ".join(state.documents._chunks[document["id"]])


@pytest.mark.parametrize("kind", ["corrupt", "encrypted", "no-text", "blank-txt"])
async def test_processing_failures_keep_file_and_metadata_as_error_without_chunks(tmp_path, kind):
    payloads = {
        "corrupt": ("broken.pdf", b"%PDF-1.4\nnot a readable PDF", "application/pdf"),
        "encrypted": ("locked.pdf", text_pdf(encrypted=True), "application/pdf"),
        "no-text": ("scan.pdf", text_pdf(blank=True), "application/pdf"),
        "blank-txt": ("empty-text.txt", b" \r\n\t ", "text/plain"),
    }
    filename, content, mime = payloads[kind]
    async with api(tmp_path) as state:
        response = await state.client.post(URL, headers=state.admin_headers, **upload_data(
            filename=filename, content=content, mime=mime,
        ))
        assert response.status_code == 201
        document = response.json()["document"]
        assert document["status"] == "error" and document["isActive"] is False
        assert document["chunkCount"] == 0 and document["processedAt"].endswith("Z")
        assert not state.documents._chunks.get(document["id"])
        files = list(state.storage.iterdir())
        assert len(files) == 1 and files[0].read_bytes() == content
        assert str(state.storage) not in response.text and "Traceback" not in response.text
        assert "file_path" not in response.text
        assert (await state.client.get(URL, headers=state.admin_headers)).json()["documents"][0] == document


async def test_existing_pending_document_can_be_processed_and_repeated_without_duplicate_chunks(tmp_path):
    async with api(tmp_path) as state:
        record, _ = await pending_document(state, content=("Văn bản có nhiều đoạn để xử lý. " * 150).encode())
        assert record.status == "pending"
        response = await process(state, record.id)
        assert response.status_code == 200
        document = response.json()["document"]
        chunks = state.documents._chunks[record.id]
        assert document["status"] == "ready" and document["chunkCount"] == len(chunks) > 1
        assert document["isActive"] is False
        repeated = await asyncio.gather(*(process(state, record.id) for _ in range(3)))
        assert all(result.status_code == 200 and result.json()["document"] == document for result in repeated)
        assert state.documents._chunks[record.id] == chunks


async def test_error_document_can_be_retried_after_its_file_is_restored(tmp_path):
    async with api(tmp_path) as state:
        record, path = await pending_document(state, content=b" \n ")
        failed = await process(state, record.id)
        assert failed.status_code == 200 and failed.json()["document"]["status"] == "error"
        path.write_text("Nội dung tài liệu đã được khôi phục.", encoding="utf-8")
        restored = await process(state, record.id)
        assert restored.status_code == 200
        document = restored.json()["document"]
        assert document["id"] == record.id and document["status"] == "ready"
        assert document["chunkCount"] == 1 and document["processedAt"].endswith("Z")
        assert state.documents._chunks[record.id] == ("Nội dung tài liệu đã được khôi phục.",)


async def test_late_failed_processing_does_not_downgrade_a_completed_document(tmp_path):
    async with api(tmp_path) as state:
        record, _ = await pending_document(state)
        ready = (await process(state, record.id)).json()["document"]
        chunks = state.documents._chunks[record.id]
        preserved = await state.documents.finish_processing(record.id, chunks=None)
        assert preserved.status == "ready" and preserved.chunk_count == ready["chunkCount"]
        assert preserved.processed_at == ready["processedAt"]
        assert state.documents._chunks[record.id] == chunks


async def test_missing_stored_file_becomes_error_instead_of_remaining_pending(tmp_path):
    async with api(tmp_path) as state:
        record = await state.documents.create(topic_id=1, title="File đã mất", file_path="missing.txt")
        response = await process(state, record.id)
        assert response.status_code == 200
        document = response.json()["document"]
        assert document["status"] == "error" and document["chunkCount"] == 0
        assert document["processedAt"].endswith("Z")
        assert str(state.storage) not in response.text and "missing.txt" not in response.text


@pytest.mark.parametrize("form", ["relative-parent", "absolute", "nested"])
async def test_process_rejects_metadata_paths_outside_private_storage_before_extracting(tmp_path, form):
    async with api(tmp_path) as state:
        outside = tmp_path / "outside.txt"
        outside.write_text("PRIVATE CONTENT MUST NEVER BE READ", encoding="utf-8")
        file_path = {"relative-parent": "../outside.txt", "absolute": str(outside), "nested": "nested/source.txt"}[form]
        record = await state.documents.create(topic_id=1, title="Đường dẫn không hợp lệ", file_path=file_path)
        with patch("app.services.document_service.extract_document_text", wraps=extract_document_text) as extract:
            response = await process(state, record.id)
        assert response.status_code == 200
        assert response.json()["document"]["status"] == "error"
        assert response.json()["document"]["chunkCount"] == 0
        extract.assert_not_called()
        assert "PRIVATE CONTENT" not in response.text and str(outside) not in response.text
        assert outside.read_text(encoding="utf-8") == "PRIVATE CONTENT MUST NEVER BE READ"


async def test_process_rejects_a_symlink_to_a_file_outside_storage(tmp_path):
    async with api(tmp_path) as state:
        state.storage.mkdir()
        outside = tmp_path / "outside.txt"
        outside.write_text("Outside file", encoding="utf-8")
        link = state.storage / "linked.txt"
        try:
            link.symlink_to(outside)
        except OSError:
            pytest.skip("Hệ điều hành không cấp quyền tạo symlink cho test.")
        record = await state.documents.create(topic_id=1, title="Liên kết ngoài kho", file_path=link.name)
        with patch("app.services.document_service.extract_document_text", wraps=extract_document_text) as extract:
            response = await process(state, record.id)
        assert response.status_code == 200 and response.json()["document"]["status"] == "error"
        extract.assert_not_called()
        assert outside.read_text(encoding="utf-8") == "Outside file"


@pytest.mark.parametrize("access,status", [("guest", 401), ("learner", 403), ("inactive", 403)])
async def test_processing_requires_active_admin_before_touching_documents(tmp_path, access, status):
    async with api(tmp_path) as state:
        record, path = await pending_document(state)
        headers = {} if access == "guest" else state.learner_headers if access == "learner" else state.admin_headers
        if access == "inactive":
            state.users._users[state.admin.id] = replace(state.admin, is_active=False)
        response = await process(state, record.id, headers=headers)
        assert response.status_code == status
        assert (await state.documents.find_document(record.id)).status == "pending"
        assert not state.documents._chunks.get(record.id)
        assert path.read_bytes() == b"Legacy text to process"


@pytest.mark.parametrize("document_id", ["0", "-1", "abc", "2147483648"])
async def test_processing_rejects_invalid_document_ids(tmp_path, document_id):
    async with api(tmp_path) as state:
        assert (await process(state, document_id)).status_code == 422
        assert not await state.documents.list_documents()


async def test_processing_unknown_document_is_404(tmp_path):
    async with api(tmp_path) as state:
        response = await process(state, 999)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"


async def test_error_processing_clears_legacy_partial_chunks(tmp_path):
    async with api(tmp_path) as state:
        record, _ = await pending_document(state, filename="broken.pdf", content=b"%PDF-1.4\ncorrupt")
        state.documents._chunks[record.id] = ("Old partial content",)
        response = await process(state, record.id)
        assert response.status_code == 200
        assert response.json()["document"]["status"] == "error"
        assert response.json()["document"]["chunkCount"] == 0
        assert not state.documents._chunks.get(record.id)


@pytest.mark.parametrize("operation", ["upload", "existing"])
async def test_failed_processing_commit_returns_safe_error_without_false_ready(tmp_path, operation):
    class FailingRepository(InMemoryDocumentRepository):
        async def finish_processing(self, document_id, *, chunks):
            raise RuntimeError("private-database-details")

    catalog = make_documents()
    repository = FailingRepository(subjects=catalog._subjects.values(), topics=catalog._topics.values())
    async with api(tmp_path, repository) as state:
        if operation == "existing":
            record, _ = await pending_document(state)
            response = await process(state, record.id)
        else:
            response = await state.client.post(URL, headers=state.admin_headers, **upload_data())
        assert response.status_code == 500
        assert "private-database-details" not in response.text
        saved = await state.documents.list_documents()
        assert len(saved) == 1 and saved[0].status == "pending"
        assert not state.documents._chunks
        assert len(list(state.storage.iterdir())) == 1
