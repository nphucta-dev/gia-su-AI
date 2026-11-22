"""Kiểm thử API xem tài liệu học tập (danh sách, chi tiết nội dung và xem/tải tệp gốc)."""

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.main import create_app
from app.repositories.document_repository import (
    InMemoryDocumentRepository,
    SubjectRecord,
    TopicRecord,
)
from app.repositories.user_repository import InMemoryUserRepository

pytestmark = pytest.mark.anyio
ROOT = "/api/documents"


def make_repository() -> InMemoryDocumentRepository:
    return InMemoryDocumentRepository(
        subjects=[
            SubjectRecord(1, "Toán học", "THPT", True),
            SubjectRecord(2, "Vật lí", "THCS", True),
            SubjectRecord(3, "Hóa học", "THPT", False),
        ],
        topics=[
            TopicRecord(1, 1, "Phương trình bậc hai", "Chương 1", True),
            TopicRecord(2, 1, "Chủ đề đã tắt", "Chương 2", False),
            TopicRecord(3, 2, "Định luật Ôm", "Điện học", True),
            TopicRecord(4, 3, "Phản ứng oxi hóa", "Chương 1", True),
        ],
    )


async def seed_document(
    repository: InMemoryDocumentRepository,
    storage: Path,
    *,
    topic_id: int,
    title: str,
    filename: str,
    file_bytes: bytes | None,
    chunks: list[str] | None = None,
    active: bool = True,
    source_url: str | None = None,
):
    if file_bytes is not None:
        storage.mkdir(parents=True, exist_ok=True)
        (storage / filename).write_bytes(file_bytes)
    doc = await repository.create(topic_id=topic_id, title=title, file_path=filename)
    if source_url is not None:
        doc = replace(doc, source_url=source_url)
        repository._documents[doc.id] = doc
    if chunks is not None:
        doc = await repository.finish_processing(doc.id, chunks=chunks)
        if active:
            doc = await repository.set_document_active(doc.id, True)
    return doc


@asynccontextmanager
async def api(tmp_path: Path, *, role: str = "LEARNER", missing_repository: bool = False):
    users = InMemoryUserRepository()
    user = await users.create(
        name="Người học",
        email="learner@example.com",
        password_hash="private-hash",
        role=role,
    )
    repository = make_repository()
    storage = tmp_path / "private-documents"

    doc_txt = await seed_document(
        repository,
        storage,
        topic_id=1,
        title="Phương trình bậc hai cơ bản",
        filename="pt_bac_hai.txt",
        file_bytes="Đoạn 1: ax^2 + bx + c = 0.\n\nĐoạn 2: Delta = b^2 - 4ac.".encode("utf-8"),
        chunks=["Đoạn 1: ax^2 + bx + c = 0.", "Đoạn 2: Delta = b^2 - 4ac."],
        active=True,
        source_url="https://example.edu.vn/toan/pt-bac-hai",
    )
    doc_pdf = await seed_document(
        repository,
        storage,
        topic_id=3,
        title="Tóm tắt Định luật Ôm",
        filename="dinh_luat_ohm.pdf",
        file_bytes=b"%PDF-1.4\n%fake-pdf-content\n%%EOF",
        chunks=["Cường độ dòng điện tỉ lệ thuận với hiệu điện thế."],
        active=True,
    )
    # Tài liệu đã ready nhưng chưa bật active -> người học không được thấy.
    doc_inactive = await seed_document(
        repository,
        storage,
        topic_id=1,
        title="Tài liệu chưa bật",
        filename="inactive.txt",
        file_bytes=b"hidden",
        chunks=["Nội dung ẩn"],
        active=False,
    )
    # Tài liệu đang pending -> người học không được thấy.
    doc_pending = await seed_document(
        repository,
        storage,
        topic_id=1,
        title="Tài liệu đang chờ",
        filename="pending.txt",
        file_bytes=b"pending",
        chunks=None,
        active=False,
    )
    # Tài liệu bị error -> người học không được thấy.
    doc_error = await seed_document(
        repository,
        storage,
        topic_id=1,
        title="Tài liệu lỗi",
        filename="error.txt",
        file_bytes=b"error",
        chunks=None,
        active=False,
    )
    await repository.finish_processing(doc_error.id, chunks=None)

    app = create_app(
        user_repository=users,
        document_repository=None if missing_repository else repository,
        upload_dir=storage,
        settings=Settings(jwt_secret="learning-docs-secret-" + "x" * 40),
    )
    token = app.state.token_service.create_access_token(user.id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        yield SimpleNamespace(
            client=client,
            app=app,
            users=users,
            user=user,
            repository=repository,
            storage=storage,
            doc_txt=doc_txt,
            doc_pdf=doc_pdf,
            doc_inactive=doc_inactive,
            doc_pending=doc_pending,
            doc_error=doc_error,
        )


@pytest.mark.parametrize("role", ["LEARNER", "ADMIN"])
async def test_list_learning_documents_returns_only_ready_active_documents_in_active_catalog(tmp_path, role):
    async with api(tmp_path, role=role) as state:
        response = await state.client.get(ROOT)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"
        docs = response.json()["documents"]
        assert {doc["id"] for doc in docs} == {state.doc_txt.id, state.doc_pdf.id}
        txt_item = next(doc for doc in docs if doc["id"] == state.doc_txt.id)
        assert txt_item["title"] == "Phương trình bậc hai cơ bản"
        assert txt_item["subjectId"] == 1
        assert txt_item["subjectName"] == "Toán học"
        assert txt_item["gradeLevel"] == "THPT"
        assert txt_item["topicId"] == 1
        assert txt_item["topicName"] == "Phương trình bậc hai"
        assert txt_item["chapterName"] == "Chương 1"
        assert txt_item["sourceUrl"] == "https://example.edu.vn/toan/pt-bac-hai"
        assert txt_item["fileName"] == "Phương trình bậc hai cơ bản.txt"
        assert txt_item["fileType"] == "txt"
        assert txt_item["chunkCount"] == 2
        assert txt_item["sizeBytes"] > 0
        for private in ("file_path", "filePath", "pt_bac_hai.txt", str(state.storage), state.user.email):
            assert private not in response.text


async def test_list_learning_documents_supports_filters_and_vietnamese_search(tmp_path):
    async with api(tmp_path) as state:
        by_topic = await state.client.get(ROOT, params={"topicId": 1})
        assert by_topic.status_code == 200
        assert [doc["id"] for doc in by_topic.json()["documents"]] == [state.doc_txt.id]

        by_subject = await state.client.get(ROOT, params={"subjectId": 2})
        assert by_subject.status_code == 200
        assert [doc["id"] for doc in by_subject.json()["documents"]] == [state.doc_pdf.id]

        by_grade = await state.client.get(ROOT, params={"gradeLevel": "THCS"})
        assert by_grade.status_code == 200
        assert [doc["id"] for doc in by_grade.json()["documents"]] == [state.doc_pdf.id]

        by_query = await state.client.get(ROOT, params={"q": "dinh luat om"})
        assert by_query.status_code == 200
        assert [doc["id"] for doc in by_query.json()["documents"]] == [state.doc_pdf.id]

        disabled_topic = await state.client.get(ROOT, params={"topicId": 2})
        assert disabled_topic.status_code == 404


async def test_catalog_topic_documents_route_lists_active_documents_and_rejects_closed_topic(tmp_path):
    async with api(tmp_path) as state:
        ok = await state.client.get("/api/catalog/topics/1/documents")
        assert ok.status_code == 200
        assert ok.json()["topicId"] == 1
        assert [doc["id"] for doc in ok.json()["documents"]] == [state.doc_txt.id]

        assert (await state.client.get("/api/catalog/topics/2/documents")).status_code == 404
        assert (await state.client.get("/api/catalog/topics/999/documents")).status_code == 404


async def test_get_learning_document_detail_returns_ordered_chunks_and_content(tmp_path):
    async with api(tmp_path) as state:
        response = await state.client.get(f"{ROOT}/{state.doc_txt.id}")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        doc = response.json()["document"]
        assert doc["id"] == state.doc_txt.id
        assert doc["chunkCount"] == 2
        assert doc["chunks"] == [
            {"id": 1, "chunkIndex": 0, "content": "Đoạn 1: ax^2 + bx + c = 0."},
            {"id": 2, "chunkIndex": 1, "content": "Đoạn 2: Delta = b^2 - 4ac."},
        ]
        assert doc["content"] == "Đoạn 1: ax^2 + bx + c = 0.\n\nĐoạn 2: Delta = b^2 - 4ac."
        assert "pt_bac_hai.txt" not in response.text


async def test_ineligible_or_disabled_documents_return_404_on_detail_and_file(tmp_path):
    async with api(tmp_path) as state:
        for hidden_id in (state.doc_inactive.id, state.doc_pending.id, state.doc_error.id, 9999):
            assert (await state.client.get(f"{ROOT}/{hidden_id}")).status_code == 404
            assert (await state.client.get(f"{ROOT}/{hidden_id}/file")).status_code == 404

        # Tắt chủ đề -> tài liệu thuộc chủ đề đó lập tức không xem được nữa.
        state.repository._topics[1] = replace(state.repository._topics[1], is_active=False)
        assert (await state.client.get(f"{ROOT}/{state.doc_txt.id}")).status_code == 404
        assert (await state.client.get(f"{ROOT}/{state.doc_txt.id}/file")).status_code == 404

        # Tắt môn học -> tài liệu thuộc môn đó lập tức không xem được nữa.
        state.repository._subjects[2] = replace(state.repository._subjects[2], is_active=False)
        assert (await state.client.get(f"{ROOT}/{state.doc_pdf.id}")).status_code == 404
        assert (await state.client.get(f"{ROOT}/{state.doc_pdf.id}/file")).status_code == 404


async def test_get_learning_document_file_streams_inline_and_attachment_safely(tmp_path):
    async with api(tmp_path) as state:
        txt_inline = await state.client.get(f"{ROOT}/{state.doc_txt.id}/file")
        assert txt_inline.status_code == 200
        assert txt_inline.headers["content-type"].startswith("text/plain")
        assert txt_inline.headers["content-disposition"].startswith("inline;")
        assert txt_inline.headers["cache-control"] == "no-store"
        assert txt_inline.headers["x-content-type-options"] == "nosniff"
        assert "Delta = b^2 - 4ac." in txt_inline.text

        pdf_download = await state.client.get(f"{ROOT}/{state.doc_pdf.id}/file", params={"download": "true"})
        assert pdf_download.status_code == 200
        assert pdf_download.headers["content-type"] == "application/pdf"
        assert pdf_download.headers["content-disposition"].startswith("attachment;")
        assert pdf_download.content.startswith(b"%PDF-1.4")

        # Chống path traversal nếu metadata cũ chứa đường dẫn ngoài thư mục lưu trữ.
        outside = tmp_path / "secret.txt"
        outside.write_text("TOP SECRET", encoding="utf-8")
        state.repository._documents[state.doc_txt.id] = replace(
            state.repository._documents[state.doc_txt.id], file_path="../secret.txt"
        )
        blocked = await state.client.get(f"{ROOT}/{state.doc_txt.id}/file")
        assert blocked.status_code == 404
        assert "TOP SECRET" not in blocked.text


@pytest.mark.parametrize("access,status", [("missing", 401), ("invalid", 401), ("inactive", 403), ("deleted", 401)])
async def test_learning_document_routes_require_active_authenticated_user(tmp_path, access, status):
    async with api(tmp_path) as state:
        headers = {}
        if access == "missing":
            headers = {"Authorization": ""}
        elif access == "invalid":
            headers = {"Authorization": "Bearer invalid-token"}
        elif access == "inactive":
            state.users._users[state.user.id] = replace(state.user, is_active=False)
        else:
            state.users._users.pop(state.user.id)

        for path in (ROOT, f"{ROOT}/{state.doc_txt.id}", f"{ROOT}/{state.doc_txt.id}/file", "/api/catalog/topics/1/documents"):
            response = await state.client.get(path, headers=headers)
            assert response.status_code == status
            assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    [
        f"{ROOT}/0",
        f"{ROOT}/2147483648",
        f"{ROOT}/not-an-id",
        f"{ROOT}/0/file",
        "/api/catalog/topics/0/documents",
        "/api/catalog/topics/2147483648/documents",
    ],
)
async def test_invalid_ids_are_rejected_with_422(tmp_path, path):
    async with api(tmp_path) as state:
        assert (await state.client.get(path)).status_code == 422


async def test_missing_repository_and_database_errors_return_safe_503(tmp_path):
    async with api(tmp_path, missing_repository=True) as state:
        assert (await state.client.get(ROOT)).status_code == 503
        assert (await state.client.get(f"{ROOT}/1")).status_code == 503
        assert (await state.client.get("/api/catalog/topics/1/documents")).status_code == 503

    async with api(tmp_path) as state:
        async def failed_list(**kwargs):
            raise SQLAlchemyError("mysql://secret:pass@db/giasuai")

        async def failed_find(document_id):
            raise SQLAlchemyError("mysql://secret:pass@db/giasuai")

        state.repository.list_learning_documents = failed_list
        state.repository.find_learning_document = failed_find

        list_resp = await state.client.get(ROOT)
        assert list_resp.status_code == 503
        assert "secret:pass" not in list_resp.text

        detail_resp = await state.client.get(f"{ROOT}/{state.doc_txt.id}")
        assert detail_resp.status_code == 503
        assert "secret:pass" not in detail_resp.text
