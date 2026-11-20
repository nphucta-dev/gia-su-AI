"""Publishing a processed source controls whether retrieval can use its chunks."""

from dataclasses import replace

import pytest

from test_document_upload_api import URL, api, upload_data

pytestmark = pytest.mark.anyio


async def test_ready_source_can_be_published_and_withdrawn_without_changing_chunks(tmp_path):
    async with api(tmp_path) as state:
        uploaded = await state.client.post(URL, headers=state.admin_headers, **upload_data(
            content="Đạo hàm giúp khảo sát hàm số.".encode(),
        ))
        document = uploaded.json()["document"]
        document_id = document["id"]
        assert await state.documents.list_eligible_chunks(1) == []
        enabled = await state.client.patch(f"{URL}/{document_id}", headers=state.admin_headers, json={"isActive": True})
        assert enabled.status_code == 200, enabled.text
        assert enabled.json()["document"] == {**document, "isActive": True}
        chunks = await state.documents.list_eligible_chunks(1)
        assert len(chunks) == 1 and chunks[0].document_id == document_id
        disabled = await state.client.patch(f"{URL}/{document_id}", headers=state.admin_headers, json={"isActive": False})
        assert disabled.status_code == 200
        assert disabled.json()["document"] == document
        assert await state.documents.list_eligible_chunks(1) == []
        assert state.documents._chunks[document_id] == ("Đạo hàm giúp khảo sát hàm số.",)
        assert disabled.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("status", ["pending", "error", "ready"])
async def test_no_source_can_be_published_without_successful_processing_and_chunks(tmp_path, status):
    async with api(tmp_path) as state:
        record = await state.documents.create(topic_id=1, title="Chưa có nguồn", file_path="absent.txt")
        state.documents._documents[record.id] = replace(record, status=status)
        response = await state.client.patch(f"{URL}/{record.id}", headers=state.admin_headers, json={"isActive": True})
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "DOCUMENT_NOT_READY"
        assert not (await state.documents.find_document(record.id)).is_active


async def test_only_active_admin_can_change_source_publication(tmp_path):
    async with api(tmp_path) as state:
        record = await state.documents.create(topic_id=1, title="Nguồn", file_path="absent.txt")
        for headers, status in (({}, 401), (state.learner_headers, 403)):
            response = await state.client.patch(f"{URL}/{record.id}", headers=headers, json={"isActive": False})
            assert response.status_code == status
        state.users._users[state.admin.id] = replace(state.admin, is_active=False)
        response = await state.client.patch(f"{URL}/{record.id}", headers=state.admin_headers, json={"isActive": False})
        assert response.status_code == 403


@pytest.mark.parametrize("body", [{}, {"isActive": 1}, {"isActive": "true"}, {"isActive": None}, {"isActive": True, "status": "ready"}])
async def test_activation_rejects_ambiguous_or_additional_fields(tmp_path, body):
    async with api(tmp_path) as state:
        response = await state.client.patch(f"{URL}/1", headers=state.admin_headers, json=body)
        assert response.status_code == 422


async def test_unknown_document_is_404(tmp_path):
    async with api(tmp_path) as state:
        response = await state.client.patch(f"{URL}/2147483647", headers=state.admin_headers, json={"isActive": False})
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "DOCUMENT_NOT_FOUND"
