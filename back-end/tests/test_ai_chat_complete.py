"""Real chat actions with a fake provider: retry, sources, feedback and shared quota."""

import asyncio
from contextlib import asynccontextmanager
from dataclasses import replace
import json
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.ai_quota_repository import InMemoryAiQuotaRepository
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.document_repository import InMemoryDocumentRepository, SubjectRecord, TopicRecord
from app.repositories.quiz_repository import InMemoryQuizRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.ai_quota import AiQuotaService
from app.utils.errors import AppError
from test_chat_api import FakeLLM
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


@asynccontextmanager
async def application(*, limit=30, source=True):
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phương trình")
    users = InMemoryUserRepository()
    owner = await users.create(name="Nguyễn Văn An", email="an@example.com", password_hash="private-hash", role="LEARNER")
    other = await users.create(name="Người khác", email="other@example.com", password_hash="other-hash", role="ADMIN")
    docs = InMemoryDocumentRepository(
        subjects=[SubjectRecord(subject_id, "Toán", "THPT")],
        topics=[TopicRecord(topic_id, subject_id, "Phương trình", "Đại số")],
    )
    document = await docs.create(topic_id=topic_id, title="Tài liệu Đại số", file_path="source.txt")
    await docs.finish_processing(document.id, chunks=["Phương trình bậc hai có biệt thức delta. Nguyễn Văn An, an@example.com, password: private-pass"])
    if source:
        docs._documents[document.id] = replace(docs._documents[document.id], is_active=True)
    chat = InMemoryChatRepository(catalog)
    quiz = InMemoryQuizRepository(catalog)
    quota = AiQuotaService(InMemoryAiQuotaRepository(chat, quiz), limit=limit)
    model = FakeLLM("Bạn thử kiểm tra biệt thức của phương trình nhé. [1]")
    app = create_app(
        user_repository=users, catalog_repository=catalog, chat_repository=chat, quiz_repository=quiz,
        document_repository=docs, llm_client=model, ai_quota_service=quota,
        settings=Settings(jwt_secret="ai-chat-complete-tests-" + "x" * 40),
    )
    def auth(user):
        return {"Authorization": "Bearer " + app.state.token_service.create_access_token(user.id).access_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=auth(owner)) as client:
        created = await client.post("/api/chat/sessions", json={"topicId": topic_id})
        yield SimpleNamespace(app=app, client=client, owner=owner, other=other, auth=auth, model=model,
                              chat=chat, quiz=quiz, docs=docs, quota=quota, topic_id=topic_id,
                              document=document, session_id=created.json()["session"]["id"])


async def test_model_receives_only_redacted_real_sources_and_history_checks_availability():
    async with application() as state:
        path = f"/api/chat/sessions/{state.session_id}"
        response = await state.client.post(path + "/messages", json={"content": "Giải phương trình bậc hai"})
        assert response.status_code == 201, response.text
        assistant = response.json()["assistantMessage"]
        assert assistant["sourcesStatus"] == "available" and len(assistant["sourceRefs"]) == 1
        ref = assistant["sourceRefs"][0]
        assert ref["documentId"] == state.document.id and ref["title"] == "Tài liệu Đại số"
        assert ref["available"] is True and "file_path" not in json.dumps(ref)
        prompt = json.dumps(state.model.calls[0], ensure_ascii=False)
        assert "biệt thức delta" in prompt
        for secret in (state.owner.name, state.owner.email, "private-pass", state.owner.password_hash):
            assert secret not in prompt
        state.docs._documents[state.document.id] = replace(state.docs._documents[state.document.id], is_active=False)
        history = (await state.client.get(path + "/messages")).json()["messages"]
        assert history[-1]["sourceRefs"][0]["available"] is False
        assert history[-1]["sourcesStatus"] == "unavailable"
        assert history[-1]["content"] == assistant["content"]


async def test_no_source_is_explicit_in_prompt_and_response():
    async with application(source=False) as state:
        response = await state.client.post(f"/api/chat/sessions/{state.session_id}/messages", json={"content": "Phương trình bậc hai"})
        assert response.status_code == 201
        assert response.json()["assistantMessage"]["sourceRefs"] == []
        assert response.json()["assistantMessage"]["sourcesStatus"] == "none"
        prompts = state.model.calls[0]
        source_data = [json.loads(item["content"]) for item in prompts if item["role"] == "user" and item["content"].startswith('{"type": "retrieved_academic_sources"')]
        assert source_data == [{"type": "retrieved_academic_sources", "sources": []}]


async def test_provider_failure_retry_preserves_exactly_one_question_and_counts_only_success():
    async with application() as state:
        path = f"/api/chat/sessions/{state.session_id}"
        state.model.failure = AppError(504, "LLM_TIMEOUT", "Thử lại sau.")
        failed = await state.client.post(path + "/messages", json={"content": "Giải phương trình"})
        assert failed.status_code == 504
        assert failed.json()["error"]["fields"]["messageSaved"] == "true"
        assert len(state.chat._messages) == 1
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 0
        state.model.failure = None
        retried = await state.client.post(path + "/retry")
        assert retried.status_code == 201 and retried.json()["userMessage"] is None
        assert [item.role for item in state.chat._messages.values()] == ["user", "assistant"]
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 1
        assert (await state.client.post(path + "/retry")).status_code == 409
        assert len(state.model.calls) == 2


async def test_explanation_does_not_advance_hint_level_or_grant_full_solution():
    async with application() as state:
        path = f"/api/chat/sessions/{state.session_id}"
        await state.client.post(path + "/messages", json={"content": "Giải phương trình"})
        for mode in ("simplify", "example"):
            response = await state.client.post(path + "/explanations", json={"mode": mode})
            assert response.status_code == 201
            assert response.json()["assistantMessage"]["hintLevel"] is None
            assert response.json()["assistantMessage"]["isFullSolution"] is False
            assert json.loads(state.model.calls[-1][-1]["content"])["action"] == mode
        next_hint = await state.client.post(path + "/hints")
        assert next_hint.json()["assistantMessage"]["hintLevel"] == 2
        invalid = await state.client.post(path + "/explanations", json={"mode": "full_solution", "confirmed": True})
        assert invalid.status_code == 422


async def test_feedback_updates_same_owned_assistant_row_only():
    async with application() as state:
        path = f"/api/chat/sessions/{state.session_id}"
        response = await state.client.post(path + "/messages", json={"content": "Phương trình"})
        user_id = response.json()["userMessage"]["id"]
        assistant_id = response.json()["assistantMessage"]["id"]
        feedback_path = f"{path}/messages/{assistant_id}/feedback"
        for feedback in (1, -1, None):
            updated = await state.client.patch(feedback_path, json={"feedback": feedback})
            assert updated.status_code == 200 and updated.json()["message"]["feedback"] == feedback
            assert updated.json()["message"]["id"] == assistant_id and len(state.chat._messages) == 2
        assert (await state.client.patch(feedback_path, json={"feedback": 2})).status_code == 422
        assert (await state.client.patch(feedback_path, json={"feedback": True})).status_code == 422
        assert (await state.client.patch(f"{path}/messages/{user_id}/feedback", json={"feedback": 1})).status_code == 404
        assert (await state.client.patch(feedback_path, json={"feedback": 1}, headers=state.auth(state.other))).status_code == 404


async def test_quota_counts_successful_chat_and_created_quiz_then_blocks_without_writes():
    async with application(limit=2) as state:
        path = f"/api/chat/sessions/{state.session_id}"
        await state.client.post(path + "/messages", json={"content": "Phương trình"})
        await state.app.state.quiz_service.save_generated_quiz(state.owner, state.topic_id, "easy", valid_payload())
        quota = await state.client.get("/api/ai/quota")
        assert quota.json()["used"] == 2 and quota.json()["remaining"] == 0
        assert quota.json()["resetTimezone"] == "UTC" and "T00:00:00" in quota.json()["nextResetAt"]
        count = len(state.chat._messages)
        blocked = await state.client.post(path + "/messages", json={"content": "Câu hỏi tiếp theo"})
        assert blocked.status_code == 429 and blocked.json()["error"]["code"] == "AI_QUOTA_EXCEEDED"
        assert int(blocked.headers["retry-after"]) > 0
        assert len(state.chat._messages) == count and len(state.model.calls) == 1
        assert (await state.client.get(path + "/messages")).status_code == 200
        assert (await state.client.get("/api/progress")).status_code == 200


async def test_one_account_cannot_start_parallel_paid_calls_in_different_sessions():
    async with application() as state:
        second = (await state.client.post("/api/chat/sessions", json={"topicId": state.topic_id})).json()["session"]["id"]
        entered, release = asyncio.Event(), asyncio.Event()
        original = state.model.generate
        async def generate(messages):
            entered.set()
            await release.wait()
            return await original(messages)
        state.model.generate = generate
        first = asyncio.create_task(state.client.post(f"/api/chat/sessions/{state.session_id}/messages", json={"content": "Phương trình"}))
        await entered.wait()
        try:
            second_result = await state.client.post(f"/api/chat/sessions/{second}/messages", json={"content": "Một câu hỏi khác"})
            assert second_result.status_code == 409 and second_result.json()["error"]["code"] == "AI_REQUEST_BUSY"
            assert await state.chat.list_messages(state.owner.id, second, limit=10, offset=0) == []
        finally:
            release.set()
            assert (await first).status_code == 201


async def test_cancelled_request_keeps_quota_guard_until_reply_commit_finishes():
    async with application(limit=1) as state:
        entered, release = asyncio.Event(), asyncio.Event()
        original = state.chat.append_assistant_message
        async def delayed_commit(*args, **kwargs):
            entered.set()
            await release.wait()
            return await original(*args, **kwargs)
        state.chat.append_assistant_message = delayed_commit
        task = asyncio.create_task(state.app.state.chat_service.send_message(state.owner, state.session_id, "Phương trình"))
        await entered.wait()
        task.cancel()
        await asyncio.sleep(0)
        try:
            with pytest.raises(AppError) as caught:
                async with state.quota.generation(state.owner.id):
                    pytest.fail("The pending commit still owns this account's admission guard")
            assert caught.value.code == "AI_REQUEST_BUSY"
        finally:
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert (await state.quota.get_quota(state.owner.id)).used == 1
        with pytest.raises(AppError) as caught:
            async with state.quota.generation(state.owner.id):
                pytest.fail("The completed assistant reply exhausted the one-call test limit")
        assert caught.value.code == "AI_QUOTA_EXCEEDED"


@pytest.mark.parametrize("value", ["\u034f", "\u200b\u034f", "\u0301\u0300"])
async def test_invisible_only_input_never_reaches_provider(value):
    async with application() as state:
        response = await state.client.post(f"/api/chat/sessions/{state.session_id}/messages", json={"content": value})
        assert response.status_code == 422 and state.chat._messages == {} and state.model.calls == []


@pytest.mark.parametrize("suffix,body", [("/retry", None), ("/explanations", {"mode": "example"})])
async def test_new_ai_actions_keep_foreign_sessions_private(suffix, body):
    async with application() as state:
        options = {"json": body} if body is not None else {}
        foreign = await state.client.post(f"/api/chat/sessions/{state.session_id}" + suffix, headers=state.auth(state.other), **options)
        missing = await state.client.post("/api/chat/sessions/2147483647" + suffix, headers=state.auth(state.other), **options)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json() and state.model.calls == []
