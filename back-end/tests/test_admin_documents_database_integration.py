"""TK-070 API lifecycle/authorization/rollback in an isolated random MySQL database."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.main import create_app
from app.models import Document, DocumentChunk, Subject, Topic, User
from app.repositories.document_repository import DocumentNotReadyError
from test_database_integration import database, make_catalog
from test_document_upload_api import URL, upload_data

pytestmark = pytest.mark.anyio


@asynccontextmanager
async def admin_api(database, tmp_path):
    _, sessions = database
    with sessions.begin() as db:
        learner, subject, topic = make_catalog(db)
        admin = User(email=f"admin-{uuid4().hex}@example.com", full_name="Admin", password_hash="test-hash", role="ADMIN")
        other_admin = User(email=f"admin-{uuid4().hex}@example.com", full_name="Other admin", password_hash="test-hash", role="ADMIN")
        db.add_all([admin, other_admin])
        db.flush()
        learner_id, admin_id, other_admin_id, topic_id, subject_id = learner.id, admin.id, other_admin.id, topic.id, subject.id
    app = create_app(session_factory=sessions, upload_dir=tmp_path / "private-documents",
                     settings=Settings(jwt_secret="admin-documents-sql-tests-" + "x" * 40))
    def headers(user_id):
        return {"Authorization": "Bearer " + app.state.token_service.create_access_token(user_id).access_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                 base_url="http://test", headers=headers(admin_id)) as client:
        yield SimpleNamespace(client=client, app=app, sessions=sessions, repository=app.state.document_repository,
                              topic_id=topic_id, subject_id=subject_id, headers=headers,
                              admin_id=admin_id, other_admin_id=other_admin_id, learner_id=learner_id)


def chunks_snapshot(sessions, document_id):
    with sessions() as db:
        return [tuple(row) for row in db.execute(
            select(DocumentChunk.id, DocumentChunk.chunk_index, DocumentChunk.content)
            .where(DocumentChunk.document_id == document_id).order_by(DocumentChunk.chunk_index),
        )]


async def listed_document(state, document_id):
    response = await state.client.get(URL)
    assert response.status_code == 200, response.text
    return next(item for item in response.json()["documents"] if item["id"] == document_id)


async def test_mysql_admin_lists_and_processes_then_publishes_real_document_without_losing_history(database, tmp_path):
    async with admin_api(database, tmp_path) as state:
        storage = state.app.state.upload_dir
        storage.mkdir()
        path = storage / "private-source.txt"
        path.write_text("Đạo hàm giúp khảo sát hàm số và tìm cực trị.", encoding="utf-8")
        record = await state.repository.create(topic_id=state.topic_id, title="Tài liệu đạo hàm", file_path=path.name)
        pending = await listed_document(state, record.id)
        assert (pending["status"], pending["isActive"], pending["chunkCount"]) == ("pending", False, 0)
        assert path.name not in str(pending)
        rejected = await state.client.patch(f"{URL}/{record.id}", json={"isActive": True})
        assert rejected.status_code == 409
        assert (await state.client.get(URL, headers=state.headers(state.learner_id))).status_code == 403
        assert (await state.client.patch(f"{URL}/{record.id}", headers=state.headers(state.learner_id), json={"isActive": False})).status_code == 403

        processed = await state.client.post(f"{URL}/{record.id}/process")
        assert processed.status_code == 200, processed.text
        ready = processed.json()["document"]
        assert (ready["status"], ready["isActive"], ready["chunkCount"]) == ("ready", False, 1)
        assert ready["processedAt"] and await listed_document(state, record.id) == ready
        chunks = chunks_snapshot(state.sessions, record.id)
        for active in (True, True, False, False):
            response = await state.client.patch(f"{URL}/{record.id}", json={"isActive": active})
            assert response.status_code == 200 and response.json()["document"] == {**ready, "isActive": active}
            assert await listed_document(state, record.id) == response.json()["document"]
            found = await state.app.state.document_retrieval_service.search(state.topic_id, "đạo hàm")
            assert bool(found.matches) is active
            assert chunks_snapshot(state.sessions, record.id) == chunks

        # Document administration is shared by ADMIN accounts and includes closed topics.
        with state.sessions.begin() as db:
            db.get(Topic, state.topic_id).is_active = False
            db.get(Subject, state.subject_id).is_active = False
        first = await state.client.get(URL)
        second = await state.client.get(URL, headers=state.headers(state.other_admin_id))
        assert first.json() == second.json() and second.status_code == 200
        assert await listed_document(state, record.id) == ready
        restored = create_app(session_factory=state.sessions, upload_dir=storage,
                              settings=Settings(jwt_secret="admin-documents-sql-tests-" + "x" * 40))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restored), base_url="http://test",
                                     headers=state.headers(state.admin_id)) as client:
            assert ready in (await client.get(URL)).json()["documents"]
        assert path.read_text(encoding="utf-8") == "Đạo hàm giúp khảo sát hàm số và tìm cực trị."


@pytest.mark.parametrize("status", ["pending", "error", "ready"])
async def test_mysql_cannot_fake_or_publish_unprocessed_status_via_any_activation_method(database, tmp_path, status):
    async with admin_api(database, tmp_path) as state:
        record = await state.repository.create(topic_id=state.topic_id, title="Chưa có nội dung", file_path="missing.txt")
        with state.sessions.begin() as db:
            db.get(Document, record.id).status = status
        rejected = await state.client.patch(f"{URL}/{record.id}", json={"isActive": True})
        assert rejected.status_code == 409
        forged = await state.client.patch(f"{URL}/{record.id}", json={"isActive": True, "status": "ready"})
        assert forged.status_code == 422
        with pytest.raises(DocumentNotReadyError):
            await state.repository.set_active(record.id, is_active=True)
        saved = await listed_document(state, record.id)
        assert saved["status"] == status and saved["isActive"] is False and saved["chunkCount"] == 0
        assert saved["processedAt"] is None


async def test_mysql_failure_at_commit_rolls_back_publication_and_allows_retry(database, tmp_path):
    async with admin_api(database, tmp_path) as state:
        uploaded = await state.client.post(URL, **upload_data(topic_id=str(state.topic_id), content="Nội dung đạo hàm".encode()))
        assert uploaded.status_code == 201, uploaded.text
        ready = uploaded.json()["document"]
        before = chunks_snapshot(state.sessions, ready["id"])
        def fail_commit(session):
            raise SQLAlchemyError("private-database-commit-details")
        event.listen(state.sessions.class_, "before_commit", fail_commit)
        try:
            failed = await state.client.patch(f"{URL}/{ready['id']}", json={"isActive": True})
        finally:
            event.remove(state.sessions.class_, "before_commit", fail_commit)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
        assert "private-database-commit-details" not in failed.text
        assert await listed_document(state, ready["id"]) == ready
        assert chunks_snapshot(state.sessions, ready["id"]) == before
        retried = await state.client.patch(f"{URL}/{ready['id']}", json={"isActive": True})
        assert retried.status_code == 200 and retried.json()["document"]["isActive"] is True
