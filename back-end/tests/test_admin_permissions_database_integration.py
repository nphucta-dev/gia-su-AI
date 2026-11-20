"""TK-071: permissions are read from MySQL, not cached in issued JWTs."""

from contextlib import asynccontextmanager
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.main import create_app
from app.models import Document, DocumentChunk, Subject, Topic, User
from test_admin_permissions_api import ADMIN_OPERATIONS, request_data
from test_database_integration import database, make_catalog

pytestmark = pytest.mark.anyio


@asynccontextmanager
async def api(database, tmp_path):
    _, sessions = database
    with sessions.begin() as db:
        learner, subject, topic = make_catalog(db)
        learner_id, subject_id, topic_id = learner.id, subject.id, topic.id
    settings = Settings(jwt_secret="admin-permissions-sql-" + "x" * 40)
    storage = tmp_path / "private-documents"
    storage.mkdir()
    path = storage / "original.txt"
    path.write_text("Nội dung gốc cần giữ", encoding="utf-8")
    app = create_app(session_factory=sessions, upload_dir=storage, settings=settings)
    document = await app.state.document_repository.create(topic_id=topic_id, title="Nguồn gốc", file_path=path.name)
    await app.state.document_repository.finish_processing(document.id, chunks=["Nội dung gốc cần giữ"])
    headers = {"Authorization": "Bearer " + app.state.token_service.create_access_token(learner_id).access_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                 base_url="http://test", headers=headers) as client:
        yield SimpleNamespace(client=client, app=app, sessions=sessions, path=path, storage=storage,
                              learner_id=learner_id, subject_id=subject_id, topic_id=topic_id,
                              document_id=document.id)


def business_snapshot(sessions, state):
    with sessions() as db:
        counts = tuple(db.scalar(select(func.count()).select_from(model))
                       for model in (Subject, Topic, Document, DocumentChunk))
        document = db.get(Document, state.document_id)
        subject = db.get(Subject, state.subject_id)
        topic = db.get(Topic, state.topic_id)
        return counts, (subject.name, subject.is_active, topic.name, topic.is_active,
                        document.status, document.is_active, document.processed_at, document.file_path)


async def assert_all_forbidden(state):
    for method, path in ADMIN_OPERATIONS:
        resolved = path.format(subject_id=state.subject_id, topic_id=state.topic_id, document_id=state.document_id)
        response = await state.client.request(method, resolved, **request_data(
            method, path, subject_id=state.subject_id, topic_id=state.topic_id,
        ))
        assert response.status_code == 403, (method, resolved, response.text)
        assert response.json()["error"]["code"] == "FORBIDDEN"
        assert response.headers["cache-control"] == "no-store"


async def test_mysql_learner_cannot_use_any_admin_operation_or_change_business_data(database, tmp_path):
    async with api(database, tmp_path) as state:
        before = business_snapshot(state.sessions, state)
        await assert_all_forbidden(state)
        assert business_snapshot(state.sessions, state) == before
        assert list(state.storage.iterdir()) == [state.path]
        assert state.path.read_text(encoding="utf-8") == "Nội dung gốc cần giữ"


async def test_mysql_role_lock_and_deletion_take_effect_on_the_same_previously_issued_token(database, tmp_path):
    async with api(database, tmp_path) as state:
        assert (await state.client.get("/api/admin/access")).status_code == 403
        with state.sessions.begin() as db:
            db.get(User, state.learner_id).role = "ADMIN"
        allowed = await state.client.get("/api/admin/access")
        assert allowed.status_code == 200 and allowed.json()["role"] == "ADMIN"
        updated = await state.client.patch(f"/api/admin/subjects/{state.subject_id}", json={"isActive": False})
        assert updated.status_code == 200 and updated.json()["subject"]["isActive"] is False
        # A real write succeeds for ADMIN; the same token is then denied after demotion.
        with state.sessions.begin() as db:
            db.get(User, state.learner_id).role = "LEARNER"
        snapshot = business_snapshot(state.sessions, state)
        await assert_all_forbidden(state)
        assert business_snapshot(state.sessions, state) == snapshot
        with state.sessions.begin() as db:
            user = db.get(User, state.learner_id)
            user.role, user.is_active = "ADMIN", False
        denied = await state.client.get("/api/admin/access")
        assert denied.status_code == 403 and denied.json()["error"]["code"] == "FORBIDDEN"
        with state.sessions.begin() as db:
            db.delete(db.get(User, state.learner_id))
        deleted = await state.client.get("/api/admin/access")
        assert deleted.status_code == 401 and deleted.json()["error"]["code"] == "INVALID_TOKEN"
