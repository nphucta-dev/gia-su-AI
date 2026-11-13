"""Kiểm thử tải tài liệu bằng kho riêng trong bộ nhớ và thư mục tạm."""

from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from app.config import DEFAULT_UPLOAD_BODY_BYTES, Settings
from app.main import create_app
from app.repositories.document_repository import (
    InMemoryDocumentRepository,
    SubjectRecord,
    TopicRecord,
)
from app.repositories.user_repository import InMemoryUserRepository
from app.services.document_service import MAX_DOCUMENT_BYTES

pytestmark = pytest.mark.anyio
URL = "/api/admin/documents"


def make_documents():
    return InMemoryDocumentRepository(
        subjects=[SubjectRecord(1, "Toán học", "THPT"), SubjectRecord(2, "Vật lý", "THPT", False)],
        topics=[
            TopicRecord(1, 1, "Hàm số", "Chương 1"),
            TopicRecord(2, 1, "Chủ đề đã tắt", "Chương 2", False),
            TopicRecord(3, 2, "Môn đã tắt", "Chương 1"),
        ],
    )


@asynccontextmanager
async def api(tmp_path, documents=None):
    users = InMemoryUserRepository()
    documents = documents or make_documents()
    storage = tmp_path / "private-documents"
    app = create_app(
        user_repository=users,
        document_repository=documents,
        upload_dir=storage,
        settings=Settings(jwt_secret="upload-test-secret-" + "x" * 40),
    )
    admin = await users.create(name="Admin", email="admin@example.com", password_hash="unused", role="ADMIN")
    learner = await users.create(name="Learner", email="learner@example.com", password_hash="unused", role="LEARNER")
    admin_token = app.state.token_service.create_access_token(admin.id).access_token
    learner_token = app.state.token_service.create_access_token(learner.id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        yield SimpleNamespace(
            client=client,
            app=app,
            users=users,
            documents=documents,
            storage=storage,
            admin=admin,
            admin_headers={"Authorization": "Bearer " + admin_token},
            learner_headers={"Authorization": "Bearer " + learner_token},
        )


def upload_data(*, topic_id="1", title="Tài liệu học", filename="lesson.txt", content=b"Hello", mime="text/plain"):
    return {"data": {"topic_id": topic_id, "title": title}, "files": {"file": (filename, content, mime)}}


async def test_all_document_routes_require_admin_before_storage_or_database_changes(tmp_path):
    async with api(tmp_path) as state:
        for headers, status in (({}, 401), (state.learner_headers, 403)):
            for suffix in ("", "/options"):
                assert (await state.client.get(URL + suffix, headers=headers)).status_code == status
            assert (await state.client.post(URL, headers=headers, **upload_data())).status_code == status
        state.users._users[state.admin.id] = replace(state.admin, is_active=False)
        assert (await state.client.post(URL, headers=state.admin_headers, **upload_data())).status_code == 403
        assert not state.storage.exists()
        assert await state.documents.list_documents() == []


async def test_upload_options_only_include_active_subjects_and_topics(tmp_path):
    async with api(tmp_path) as state:
        response = await state.client.get(URL + "/options", headers=state.admin_headers)
        assert response.status_code == 200
        assert response.json() == {"subjects": [{
            "id": 1, "name": "Toán học", "gradeLevel": "THPT",
            "topics": [{"id": 1, "name": "Hàm số", "chapterName": "Chương 1"}],
        }]}


@pytest.mark.parametrize(
    "filename,content,mime,status",
    [
        ("lesson.txt", "Hàm số và đạo hàm".encode(), "text/plain", "ready"),
        ("lesson.pdf", b"%PDF-1.4\nexample", "application/pdf", "error"),
    ],
)
async def test_upload_saves_private_file_and_lists_final_processing_status(tmp_path, filename, content, mime, status):
    async with api(tmp_path) as state:
        response = await state.client.post(
            URL, headers=state.admin_headers,
            **upload_data(filename=filename, content=content, mime=mime, title="  Tài liệu học  "),
        )
        assert response.status_code == 201
        result = response.json()["document"]
        assert result["id"] == 1 and result["topicId"] == 1
        assert result["title"] == "Tài liệu học"
        assert result["subjectName"] == "Toán học" and result["topicName"] == "Hàm số"
        assert result["status"] == status and result["isActive"] is False
        assert result["processedAt"].endswith("Z")
        assert result["chunkCount"] == (1 if status == "ready" else 0)
        assert result["sizeBytes"] == len(content)
        assert result["fileName"] == "Tài liệu học" + Path(filename).suffix
        assert result["createdAt"].endswith("Z")
        assert "file_path" not in response.text and str(state.storage) not in response.text
        files = list(state.storage.iterdir())
        assert len(files) == 1 and files[0].read_bytes() == content
        assert files[0].name != filename
        assert len(files[0].stem) == 32
        listed = await state.client.get(URL, headers=state.admin_headers)
        assert listed.status_code == 200
        assert listed.json() == {"documents": [result]}


@pytest.mark.parametrize("topic_id", ["99", "2", "3"])
async def test_unknown_or_inactive_topic_does_not_create_file(tmp_path, topic_id):
    async with api(tmp_path) as state:
        response = await state.client.post(URL, headers=state.admin_headers, **upload_data(topic_id=topic_id))
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "TOPIC_NOT_FOUND"
        assert not state.storage.exists()


@pytest.mark.parametrize("topic_id", ["", "0", "-1", "1.0", "abc", "2147483648"])
async def test_invalid_topic_id_does_not_create_document(tmp_path, topic_id):
    async with api(tmp_path) as state:
        response = await state.client.post(URL, headers=state.admin_headers, **upload_data(topic_id=topic_id))
        assert response.status_code == 422
        assert "topic_id" in response.json()["error"]["fields"]
        assert not state.storage.exists()


@pytest.mark.parametrize("title", ["", "  ", "a" * 201, "title\x00invalid"])
async def test_invalid_title_does_not_create_document(tmp_path, title):
    async with api(tmp_path) as state:
        response = await state.client.post(URL, headers=state.admin_headers, **upload_data(title=title))
        assert response.status_code == 422
        assert "title" in response.json()["error"]["fields"]
        assert not state.storage.exists()


@pytest.mark.parametrize(
    "filename,content,mime",
    [
        ("script.exe", b"hello", "text/plain"),
        ("script.txt.exe", b"hello", "text/plain"),
        ("lesson.pdf", b"%PDF-1.4", "text/plain"),
        ("lesson.txt", b"hello", "application/pdf"),
        ("lesson.pdf", b"not-a-pdf", "application/pdf"),
        ("lesson.txt", b"\xff\xfe", "text/plain"),
        ("lesson.txt", b"\xc3", "text/plain"),
        ("lesson.txt", b"hello\x00binary", "text/plain"),
        ("lesson.txt", b"", "text/plain"),
    ],
)
async def test_rejects_invalid_format_mime_content_and_empty_file(tmp_path, filename, content, mime):
    async with api(tmp_path) as state:
        response = await state.client.post(
            URL, headers=state.admin_headers, **upload_data(filename=filename, content=content, mime=mime)
        )
        assert response.status_code == 422
        assert "file" in response.json()["error"]["fields"]
        assert not state.storage.exists()
        assert await state.documents.list_documents() == []


async def test_rejects_file_over_10mb_but_accepts_exact_limit(tmp_path):
    async with api(tmp_path) as state:
        response = await state.client.post(
            URL, headers=state.admin_headers, **upload_data(content=b"x" * (MAX_DOCUMENT_BYTES + 1))
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "FILE_TOO_LARGE"
        assert not state.storage.exists()
        response = await state.client.post(
            URL, headers=state.admin_headers, **upload_data(content=b"x" * MAX_DOCUMENT_BYTES)
        )
        assert response.status_code == 201
        assert response.json()["document"]["sizeBytes"] == MAX_DOCUMENT_BYTES


async def test_json_body_is_not_accepted_as_an_upload(tmp_path):
    async with api(tmp_path) as state:
        response = await state.client.post(URL, headers=state.admin_headers, json={"topic_id": 1, "title": "Title"})
        assert response.status_code == 415
        assert not state.storage.exists()


async def test_chunked_multipart_body_cannot_bypass_global_upload_limit(tmp_path):
    async with api(tmp_path) as state:
        async def body():
            yield b'--boundary\r\nContent-Disposition: form-data; name="file"; filename="lesson.txt"\r\nContent-Type: text/plain\r\n\r\n'
            chunk = b"x" * (64 * 1024)
            for _ in range(DEFAULT_UPLOAD_BODY_BYTES // len(chunk) + 2):
                yield chunk
            yield b"\r\n--boundary--\r\n"

        response = await state.client.post(
            URL,
            headers={**state.admin_headers, "Content-Type": "multipart/form-data; boundary=boundary"},
            content=body(),
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
        assert not state.storage.exists()


async def test_original_filename_cannot_choose_storage_path(tmp_path):
    async with api(tmp_path) as state:
        response = await state.client.post(
            URL, headers=state.admin_headers, **upload_data(filename="../../escaped.txt")
        )
        assert response.status_code == 201
        saved = list(state.storage.iterdir())
        assert len(saved) == 1 and saved[0].resolve().parent == state.storage.resolve()
        assert not (tmp_path / "escaped.txt").exists()


async def test_failed_database_write_removes_only_its_new_file(tmp_path):
    class FailingRepository(InMemoryDocumentRepository):
        async def create(self, **options):
            raise RuntimeError("internal database failure")

    repository = FailingRepository(subjects=[SubjectRecord(1, "Toán", "THPT")], topics=[TopicRecord(1, 1, "Hàm số")])
    async with api(tmp_path, repository) as state:
        state.storage.mkdir()
        existing = state.storage / "existing.txt"
        existing.write_bytes(b"keep me")
        response = await state.client.post(URL, headers=state.admin_headers, **upload_data())
        assert response.status_code == 500
        assert "internal database failure" not in response.text
        assert list(state.storage.iterdir()) == [existing]
        assert existing.read_bytes() == b"keep me"


async def test_storage_filename_collision_never_deletes_existing_file(tmp_path):
    async with api(tmp_path) as state:
        state.storage.mkdir()
        existing = state.storage / ("a" * 32 + ".txt")
        existing.write_bytes(b"original")
        with patch("app.services.document_service.uuid4", return_value=SimpleNamespace(hex="a" * 32)):
            response = await state.client.post(URL, headers=state.admin_headers, **upload_data())
        assert response.status_code == 500
        assert existing.read_bytes() == b"original"
        assert await state.documents.list_documents() == []
