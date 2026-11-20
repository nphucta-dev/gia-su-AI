"""TK-070: real document status/listing and publication with ADMIN authorization."""

from dataclasses import replace
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app.repositories.document_repository import DocumentNotReadyError
from test_document_upload_api import URL, api, upload_data

pytestmark = pytest.mark.anyio


async def pending_document(state):
    state.storage.mkdir(exist_ok=True)
    path = state.storage / "private-stored-file.txt"
    path.write_text("Nội dung đạo hàm của hàm số.", encoding="utf-8")
    record = await state.documents.create(topic_id=1, title="Bài học", file_path=path.name)
    return record, path


async def test_admin_listing_contains_all_processing_and_usage_states_even_for_closed_content(tmp_path):
    async with api(tmp_path) as state:
        assert (await state.client.get(URL, headers=state.admin_headers)).json() == {"documents": []}
        pending, path = await pending_document(state)
        ready = await state.documents.create(topic_id=1, title="Đã sẵn sàng", file_path=path.name)
        await state.documents.finish_processing(ready.id, chunks=["Nội dung đã trích xuất"])
        await state.documents.set_document_active(ready.id, True)
        failed = await state.documents.create(topic_id=1, title="File lỗi", file_path=path.name)
        await state.documents.finish_processing(failed.id, chunks=None)
        state.documents._topics[1] = replace(state.documents._topics[1], is_active=False)
        state.documents._subjects[1] = replace(state.documents._subjects[1], is_active=False)

        response = await state.client.get(URL, headers=state.admin_headers)
        assert response.status_code == 200 and response.headers["cache-control"] == "no-store"
        records = response.json()["documents"]
        assert [item["id"] for item in records] == [failed.id, ready.id, pending.id]
        assert [(item["status"], item["isActive"], item["chunkCount"]) for item in records] == [
            ("error", False, 0), ("ready", True, 1), ("pending", False, 0),
        ]
        assert all(item["topicId"] == 1 and item["subjectName"] == "Toán học" for item in records)
        assert records[0]["processedAt"] and records[1]["processedAt"] and records[2]["processedAt"] is None
        for private in (str(state.storage), path.name, "file_path", "Nội dung đạo hàm"):
            assert private not in response.text
        assert path.read_text(encoding="utf-8") == "Nội dung đạo hàm của hàm số."


async def test_admin_status_changes_through_processing_and_toggle_preserves_file_and_chunks(tmp_path):
    async with api(tmp_path) as state:
        record, path = await pending_document(state)
        path.write_text(" \n ", encoding="utf-8")
        processed = await state.client.post(f"{URL}/{record.id}/process", headers=state.admin_headers)
        assert processed.status_code == 200 and processed.json()["document"]["status"] == "error"
        assert (await state.client.get(URL, headers=state.admin_headers)).json()["documents"][0]["status"] == "error"
        rejected = await state.client.patch(f"{URL}/{record.id}", headers=state.admin_headers, json={"isActive": True})
        assert rejected.status_code == 409

        content = "Đạo hàm giúp khảo sát hàm số."
        path.write_text(content, encoding="utf-8")
        retried = await state.client.post(f"{URL}/{record.id}/process", headers=state.admin_headers)
        ready = retried.json()["document"]
        assert ready["status"] == "ready" and ready["chunkCount"] == 1 and ready["isActive"] is False
        for active in (True, True, False, False):
            changed = await state.client.patch(f"{URL}/{record.id}", headers=state.admin_headers, json={"isActive": active})
            assert changed.status_code == 200 and changed.json()["document"] == {**ready, "isActive": active}
            listed = (await state.client.get(URL, headers=state.admin_headers)).json()["documents"]
            assert listed == [changed.json()["document"]]
            found = await state.app.state.document_retrieval_service.search(1, "đạo hàm")
            assert bool(found.matches) is active
            assert state.documents._chunks[record.id] == (content,)
            assert path.read_text(encoding="utf-8") == content


@pytest.mark.parametrize("body", [
    {"status": "ready"}, {"isActive": True, "status": "ready"},
    {"isActive": False, "file_path": "outside.txt"}, {"isActive": False, "topicId": 2},
    {"isActive": True, "is_active": False},
])
async def test_update_cannot_forge_processing_status_paths_or_topic(tmp_path, body):
    async with api(tmp_path) as state:
        record, path = await pending_document(state)
        response = await state.client.patch(f"{URL}/{record.id}", headers=state.admin_headers, json=body)
        assert response.status_code == 422
        assert await state.documents.find_document(record.id) == record
        assert not state.documents._chunks and path.exists()


@pytest.mark.parametrize("content_type", ["text/plain", "application/x-www-form-urlencoded", None])
async def test_patch_requires_json_after_admin_authorization(tmp_path, content_type):
    async with api(tmp_path) as state:
        record, _ = await pending_document(state)
        for auth, status in (({}, 401), (state.learner_headers, 403), (state.admin_headers, 415)):
            headers = {**auth, **({"Content-Type": content_type} if content_type else {})}
            response = await state.client.patch(f"{URL}/{record.id}", headers=headers, content='{"isActive":false}')
            assert response.status_code == status
            assert response.headers["cache-control"] == "no-store"
        assert await state.documents.find_document(record.id) == record


async def test_existing_snake_case_body_remains_supported_by_the_same_activation_guard(tmp_path):
    async with api(tmp_path) as state:
        record, _ = await pending_document(state)
        await state.documents.finish_processing(record.id, chunks=["Văn bản hợp lệ"])
        enabled = await state.client.patch(f"{URL}/{record.id}", headers=state.admin_headers, json={"is_active": True})
        assert enabled.status_code == 200 and enabled.json()["document"]["isActive"] is True


async def test_repository_legacy_activation_also_rejects_ready_without_chunks(tmp_path):
    async with api(tmp_path) as state:
        record, _ = await pending_document(state)
        state.documents._documents[record.id] = replace(record, status="ready")
        with pytest.raises(DocumentNotReadyError):
            await state.documents.set_active(record.id, is_active=True)
        assert not (await state.documents.find_document(record.id)).is_active


@pytest.mark.parametrize("document_id", ["0", "-1", "2147483648", "not-an-id"])
async def test_patch_validates_document_ids_without_creating_records(tmp_path, document_id):
    async with api(tmp_path) as state:
        response = await state.client.patch(f"{URL}/{document_id}", headers=state.admin_headers, json={"isActive": False})
        assert response.status_code == 422 and await state.documents.list_documents() == []


@pytest.mark.parametrize("access,status", [("guest", 401), ("learner", 403), ("inactive", 403)])
async def test_forbidden_read_and_update_never_touch_the_document_repository(tmp_path, access, status):
    async with api(tmp_path) as state:
        headers = {} if access == "guest" else state.learner_headers if access == "learner" else state.admin_headers
        if access == "inactive":
            state.users._users[state.admin.id] = replace(state.admin, is_active=False)
        read, write = AsyncMock(side_effect=AssertionError("Forbidden repository read")), AsyncMock(side_effect=AssertionError("Forbidden mutation"))
        with patch.object(state.documents, "list_documents", read), patch.object(state.documents, "set_document_active", write):
            assert (await state.client.get(URL, headers=headers)).status_code == status
            assert (await state.client.patch(f"{URL}/1", headers=headers, json={"isActive": False})).status_code == status
        read.assert_not_awaited()
        write.assert_not_awaited()
        assert not state.storage.exists()


@pytest.mark.parametrize("operation", [
    "list_documents", "list_subjects", "set_document_active", "find_document",
    "finish_processing", "find_upload_topic", "create",
])
async def test_database_errors_are_503_and_retry_preserves_existing_files_and_state(tmp_path, operation):
    async with api(tmp_path) as state:
        record, path = await pending_document(state)
        saved_bytes = path.read_bytes()
        failure = OperationalError("SELECT private_table", None, Exception("private-db-password"))
        with patch.object(state.documents, operation, AsyncMock(side_effect=failure)):
            if operation == "list_documents":
                response = await state.client.get(URL, headers=state.admin_headers)
            elif operation == "list_subjects":
                response = await state.client.get(URL + "/options", headers=state.admin_headers)
            elif operation == "set_document_active":
                response = await state.client.patch(f"{URL}/{record.id}", headers=state.admin_headers, json={"isActive": False})
            elif operation in {"find_document", "finish_processing"}:
                response = await state.client.post(f"{URL}/{record.id}/process", headers=state.admin_headers)
            else:
                response = await state.client.post(URL, headers=state.admin_headers, **upload_data())
        assert response.status_code == 503, response.text
        assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert response.headers["cache-control"] == "no-store"
        assert all(secret not in response.text for secret in ("private_table", "private-db-password", str(state.storage)))
        assert await state.documents.list_documents() == [record]
        assert not state.documents._chunks and path.read_bytes() == saved_bytes
        assert list(state.storage.iterdir()) == [path]
        retried = await state.client.get(URL, headers=state.admin_headers)
        assert retried.status_code == 200 and retried.json()["documents"][0]["status"] == "pending"
