"""TK-034 on temporary MySQL: persisted explanations, ownership, quota and rollback."""

from contextlib import asynccontextmanager
import json
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import event, select
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.main import create_app
from app.models import ChatMessage, Document, DocumentChunk, User
from test_database_integration import RecordingChatModel, database, make_catalog

pytestmark = pytest.mark.anyio


@asynccontextmanager
async def chat_api(database):
    _, sessions = database
    with sessions.begin() as db:
        owner, _, topic = make_catalog(db)
        intruder = User(email=f"other-{uuid4().hex}@example.com", full_name="Other admin",
                        password_hash="test-hash", role="ADMIN")
        document = Document(topic_id=topic.id, title="Nguồn phương trình", file_path="private-source.txt", status="ready", is_active=True)
        db.add_all([document, intruder])
        db.flush()
        chunk = DocumentChunk(document_id=document.id, chunk_index=0, content="Phương trình bậc hai xét biệt thức delta.")
        db.add(chunk)
        db.flush()
        owner_id, intruder_id, topic_id, document_id, chunk_id = owner.id, intruder.id, topic.id, document.id, chunk.id
    settings = Settings(jwt_secret="explanations-sql-tests-" + "x" * 40)
    model = RecordingChatModel("Phản hồi gốc: bạn hãy xét biệt thức delta.")
    app = create_app(session_factory=sessions, llm_client=model, settings=settings)
    def auth(user_id):
        return {"Authorization": "Bearer " + app.state.token_service.create_access_token(user_id).access_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                 base_url="http://test", headers=auth(owner_id)) as client:
        created = await client.post("/api/chat/sessions", json={"topicId": topic_id})
        assert created.status_code == 201
        session_id = created.json()["session"]["id"]
        path = f"/api/chat/sessions/{session_id}"
        first = await client.post(path + "/messages", json={"content": "Phương trình bậc hai bắt đầu thế nào?"})
        assert first.status_code == 201, first.text
        yield SimpleNamespace(client=client, app=app, settings=settings, model=model, sessions=sessions,
                              owner_id=owner_id, intruder_id=intruder_id, auth=auth, session_id=session_id,
                              path=path, document_id=document_id, chunk_id=chunk_id)


async def test_mysql_explanation_modes_persist_sources_and_do_not_advance_hint_level(database):
    async with chat_api(database) as state:
        for mode in ("simplify", "example"):
            state.model.content = "Giải thích bổ sung: " + mode
            response = await state.client.post(state.path + "/explanations", json={"mode": mode})
            assert response.status_code == 201, response.text
            assistant = response.json()["assistantMessage"]
            assert assistant["hintLevel"] is None and assistant["isFullSolution"] is False
            assert assistant["sourceRefs"][0]["documentId"] == state.document_id
            assert json.loads(state.model.requests[-1][-1]["content"]) == {
                "type": "learning_request", "action": mode, "target": "latest_assistant_response",
            }
            with state.sessions() as db:
                stored = db.get(ChatMessage, assistant["id"])
                assert stored.role == "assistant" and stored.content == state.model.content
                assert stored.hint_level is None and stored.is_full_solution is False
                assert stored.token_count == 11 and stored.source_refs[0]["chunkId"] == state.chunk_id
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 3
        foreign = await state.client.post(state.path + "/explanations", json={"mode": "example"}, headers=state.auth(state.intruder_id))
        missing = await state.client.post("/api/chat/sessions/2147483647/explanations", json={"mode": "example"}, headers=state.auth(state.intruder_id))
        assert foreign.status_code == missing.status_code == 404 and foreign.json() == missing.json()
        assert len(state.model.requests) == 3
        next_hint = await state.client.post(state.path + "/hints")
        assert next_hint.status_code == 201 and next_hint.json()["assistantMessage"]["hintLevel"] == 2
        with state.sessions() as db:
            messages = list(db.scalars(select(ChatMessage).where(ChatMessage.session_id == state.session_id).order_by(ChatMessage.id)))
            assert len(messages) == 5 and sum(row.role == "user" for row in messages) == 1
            assert [row.hint_level for row in messages if row.role == "assistant"] == [1, None, None, 2]
        restored = create_app(session_factory=state.sessions, llm_client=state.model, settings=state.settings)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restored), base_url="http://test",
                                     headers=state.auth(state.owner_id)) as client:
            history = await client.get(state.path + "/messages")
            assert history.status_code == 200 and len(history.json()["messages"]) == 5
            assert (await client.get("/api/ai/quota")).json()["used"] == 4
        assert len(state.model.requests) == 4  # Reloading history/quota makes no model call.


async def test_mysql_explanation_commit_failure_keeps_history_and_quota_then_retries(database):
    async with chat_api(database) as state:
        before = (await state.client.get(state.path + "/messages")).json()
        def fail_commit(session):
            raise SQLAlchemyError("private-explanation-commit-error")
        event.listen(state.sessions.class_, "before_commit", fail_commit)
        try:
            failed = await state.client.post(state.path + "/explanations", json={"mode": "simplify"})
        finally:
            event.remove(state.sessions.class_, "before_commit", fail_commit)
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "CHAT_SAVE_FAILED"
        assert "private-explanation-commit-error" not in failed.text
        assert (await state.client.get(state.path + "/messages")).json() == before
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 1
        retried = await state.client.post(state.path + "/explanations", json={"mode": "simplify"})
        assert retried.status_code == 201
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 2
        assert len((await state.client.get(state.path + "/messages")).json()["messages"]) == 3
