"""New model-facing chat behavior against the isolated MySQL fixture only."""

import asyncio
import json
import threading

import httpx
import pytest
from app.config import Settings
from app.main import create_app
from app.models import ChatMessage, Document, DocumentChunk
from app.repositories.ai_quota_repository import SqlAlchemyAiQuotaRepository
from app.utils.errors import AppError
from test_database_integration import RecordingChatModel, database, make_catalog
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


async def test_mysql_real_sources_feedback_and_shared_success_quota(database):
    _, sessions = database
    with sessions.begin() as db:
        owner, _, topic = make_catalog(db)
        document = Document(topic_id=topic.id, title="Nguồn phương trình", file_path="source.txt", status="ready", is_active=True)
        db.add(document)
        db.flush()
        chunk = DocumentChunk(document_id=document.id, chunk_index=0, content="Phương trình bậc hai xét biệt thức delta.")
        db.add(chunk)
        db.flush()
        owner_id, topic_id, document_id, chunk_id = owner.id, topic.id, document.id, chunk.id
    model = RecordingChatModel("Bạn thử xét biệt thức như thế nào? [1]")
    app = create_app(session_factory=sessions, llm_client=model, settings=Settings(jwt_secret="ai-sources-sql-" + "x" * 40))
    user = await app.state.user_repository.find_by_id(owner_id)
    headers = {"Authorization": "Bearer " + app.state.token_service.create_access_token(owner_id).access_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        created = await client.post("/api/chat/sessions", json={"topicId": topic_id})
        session_id = created.json()["session"]["id"]
        path = f"/api/chat/sessions/{session_id}"
        reply = await client.post(path + "/messages", json={"content": "Phương trình bậc hai"})
        assert reply.status_code == 201, reply.text
        assistant = reply.json()["assistantMessage"]
        assert assistant["sourceRefs"] == [{"documentId": document_id, "chunkId": chunk_id, "title": "Nguồn phương trình", "chunkIndex": 0, "available": True}]
        assert "biệt thức delta" in json.dumps(model.requests, ensure_ascii=False)
        with sessions() as db:
            row = db.get(ChatMessage, assistant["id"])
            assert row.source_refs[0]["chunkId"] == chunk_id and row.feedback is None
        feedback = await client.patch(f"{path}/messages/{assistant['id']}/feedback", json={"feedback": -1})
        assert feedback.status_code == 200 and feedback.json()["message"]["feedback"] == -1
        with sessions() as db:
            assert db.get(ChatMessage, assistant["id"]).feedback == -1
        await app.state.quiz_service.save_generated_quiz(user, topic_id, "easy", valid_payload())
        quota = await client.get("/api/ai/quota")
        assert quota.status_code == 200 and quota.json()["used"] == 2 and quota.json()["remaining"] == 28
        assert quota.headers["cache-control"] == "no-store"
        with sessions.begin() as db:
            db.get(Document, document_id).is_active = False
        history = (await client.get(path + "/messages")).json()["messages"]
        assert history[-1]["sourceRefs"][0]["available"] is False
        assert history[-1]["feedback"] == -1


async def test_mysql_advisory_guard_serializes_accounts_across_repository_instances(database):
    _, sessions = database
    with sessions.begin() as db:
        owner, _, _ = make_catalog(db)
        owner_id = owner.id
    first, second = SqlAlchemyAiQuotaRepository(sessions), SqlAlchemyAiQuotaRepository(sessions)
    async with first.request_guard(owner_id):
        with pytest.raises(AppError) as caught:
            async with second.request_guard(owner_id):
                pytest.fail("The other worker must not start a paid model request")
        assert caught.value.code == "AI_REQUEST_BUSY"
        async with second.request_guard(owner_id + 100000):
            pass
    async with second.request_guard(owner_id):
        pass


async def test_mysql_cancelled_model_wait_releases_guard(database):
    _, sessions = database
    guard = SqlAlchemyAiQuotaRepository(sessions)
    entered = asyncio.Event()
    async def pending_call():
        async with guard.request_guard(900001):
            entered.set()
            await asyncio.Event().wait()
    task = asyncio.create_task(pending_call())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with SqlAlchemyAiQuotaRepository(sessions).request_guard(900001):
        pass


async def test_mysql_cancellation_during_acquire_does_not_leak_late_lock(database, monkeypatch):
    _, sessions = database
    guard = SqlAlchemyAiQuotaRepository(sessions)
    entered, release = threading.Event(), threading.Event()
    original = guard._acquire
    def delayed(user_id):
        entered.set()
        if not release.wait(timeout=5):
            raise RuntimeError("The test did not release its acquisition worker")
        return original(user_id)
    monkeypatch.setattr(guard, "_acquire", delayed)
    async def pending_call():
        async with guard.request_guard(900002):
            pytest.fail("Cancelled request must not enter provider work")
    task = asyncio.create_task(pending_call())
    assert await asyncio.to_thread(entered.wait, 3)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with SqlAlchemyAiQuotaRepository(sessions).request_guard(900002):
        pass
