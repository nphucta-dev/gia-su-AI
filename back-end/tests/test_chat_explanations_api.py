"""TK-034: explanation modes use private history and persist one assistant reply."""

import asyncio
from dataclasses import replace
import json
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.services.llm_client import ChatCompletionsClient
from app.utils.errors import AppError
from test_ai_chat_complete import application

pytestmark = pytest.mark.anyio


async def seed_reply(state):
    path = f"/api/chat/sessions/{state.session_id}"
    state.model.content = "Phản hồi gốc: xét dấu của biệt thức delta."
    response = await state.client.post(path + "/messages", json={"content": "Phương trình bậc hai nên bắt đầu từ đâu?"})
    assert response.status_code == 201, response.text
    return path, response.json()["assistantMessage"]


@pytest.mark.parametrize("mode", ["simplify", "example"])
async def test_modes_use_existing_context_persist_reply_and_consume_one_successful_call(mode):
    async with application() as state:
        path, original = await seed_reply(state)
        state.model.content = "Giải thích bổ sung cho " + mode
        response = await state.client.post(path + "/explanations", json={"mode": mode})
        assert response.status_code == 201 and response.headers["cache-control"] == "no-store"
        reply = response.json()["assistantMessage"]
        assert response.json()["userMessage"] is None and reply["role"] == "assistant"
        assert reply["hintLevel"] is None and reply["isFullSolution"] is False and reply["tokenCount"] == 17
        assert reply["sourceRefs"] == original["sourceRefs"] and reply["content"] == state.model.content
        sent = json.dumps(state.model.calls[-1], ensure_ascii=False)
        assert original["content"] in sent and "Phương trình bậc hai nên bắt đầu từ đâu?" in sent
        assert all(secret not in sent for secret in (state.owner.name, state.owner.email, state.owner.password_hash, "private-pass"))
        assert json.loads(state.model.calls[-1][-1]["content"]) == {
            "type": "learning_request", "action": mode, "target": "latest_assistant_response",
        }
        history = (await state.client.get(path + "/messages")).json()["messages"]
        assert len(history) == 3 and history[-1] == reply
        assert sum(item["role"] == "user" for item in history) == 1
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 2


@pytest.mark.parametrize("body", [{}, {"mode": "full_solution"}, {"mode": True}, {"mode": None},
                                  {"mode": "simplify", "confirmed": True}, {"mode": "example", "userId": 99}])
async def test_invalid_modes_and_client_supplied_control_fields_never_call_model(body):
    async with application() as state:
        response = await state.client.post(f"/api/chat/sessions/{state.session_id}/explanations", json=body)
        assert response.status_code == 422 and state.model.calls == [] and state.chat._messages == {}


async def test_explanation_requires_json_and_a_question_in_the_owned_session():
    async with application() as state:
        path = f"/api/chat/sessions/{state.session_id}/explanations"
        invalid_type = await state.client.post(path, content='{"mode":"example"}', headers={"Content-Type": "text/plain"})
        assert invalid_type.status_code == 415
        empty = await state.client.post(path, json={"mode": "example"})
        assert empty.status_code == 409 and empty.json()["error"]["code"] == "CHAT_QUESTION_REQUIRED"
        assert state.model.calls == [] and state.chat._messages == {}


@pytest.mark.parametrize("access,status", [("guest", 401), ("inactive", 403), ("other_admin", 404)])
async def test_auth_and_ownership_protect_context_even_from_other_admins(access, status):
    async with application() as state:
        path, _ = await seed_reply(state)
        before = dict(state.chat._messages)
        headers = state.auth(state.owner)
        if access == "guest":
            headers = {"Authorization": ""}
        elif access == "inactive":
            state.users = state.app.state.user_repository
            state.users._users[state.owner.id] = replace(state.owner, is_active=False)
        else:
            headers = state.auth(state.other)
        response = await state.client.post(path + "/explanations", json={"mode": "example"}, headers=headers)
        assert response.status_code == status and len(state.model.calls) == 1
        assert state.chat._messages == before
        if access == "other_admin":
            missing = await state.client.post("/api/chat/sessions/2147483647/explanations", json={"mode": "example"}, headers=headers)
            assert response.json() == missing.json()


@pytest.mark.parametrize("closed", ["topic", "subject"])
async def test_closed_content_is_readable_but_cannot_generate_explanations(closed):
    async with application() as state:
        path, _ = await seed_reply(state)
        catalog = state.chat._catalog
        if closed == "topic":
            catalog._topics[state.topic_id]["is_active"] = False
        else:
            catalog._subjects[catalog._topics[state.topic_id]["subject_id"]]["is_active"] = False
        response = await state.client.post(path + "/explanations", json={"mode": "simplify"})
        assert response.status_code == 409 and response.json()["error"]["code"] == "TOPIC_CLOSED"
        assert len(state.model.calls) == 1 and (await state.client.get(path + "/messages")).status_code == 200


async def test_exhausted_quota_does_not_write_or_generate_an_explanation():
    async with application(limit=1) as state:
        path, _ = await seed_reply(state)
        response = await state.client.post(path + "/explanations", json={"mode": "example"})
        assert response.status_code == 429 and response.json()["error"]["code"] == "AI_QUOTA_EXCEEDED"
        assert int(response.headers["retry-after"]) > 0
        assert len(state.model.calls) == 1 and len(state.chat._messages) == 2


@pytest.mark.parametrize("status,code", [(504, "LLM_TIMEOUT"), (429, "LLM_RATE_LIMITED"), (502, "LLM_UNAVAILABLE")])
async def test_provider_failure_keeps_history_and_quota_and_can_retry_the_same_mode(status, code):
    async with application() as state:
        path, _ = await seed_reply(state)
        before = dict(state.chat._messages)
        state.model.failure = AppError(status, code, "Chưa thể kết nối model.")
        failed = await state.client.post(path + "/explanations", json={"mode": "example"})
        assert failed.status_code == status and failed.json()["error"]["code"] == code
        assert state.chat._messages == before and (await state.quota.get_quota(state.owner.id)).used == 1
        state.model.failure = None
        response = await state.client.post(path + "/explanations", json={"mode": "example"})
        assert response.status_code == 201 and len(state.chat._messages) == 3
        assert (await state.quota.get_quota(state.owner.id)).used == 2


async def test_missing_model_configuration_does_not_create_a_fake_explanation():
    async with application() as state:
        path, _ = await seed_reply(state)
        state.app.state.chat_service._client = ChatCompletionsClient(Settings())
        before = dict(state.chat._messages)
        response = await state.client.post(path + "/explanations", json={"mode": "simplify"})
        assert response.status_code == 503 and response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
        assert state.chat._messages == before and (await state.quota.get_quota(state.owner.id)).used == 1


@pytest.mark.parametrize("content", [" \n\t ", "x" * 8001, "Invalid\x00reply"])
async def test_invalid_model_text_is_not_persisted_or_counted(content):
    async with application() as state:
        path, _ = await seed_reply(state)
        state.model.content = content
        before = dict(state.chat._messages)
        response = await state.client.post(path + "/explanations", json={"mode": "example"})
        assert response.status_code == 502 and response.json()["error"]["code"] == "LLM_INVALID_RESPONSE"
        assert state.chat._messages == before and (await state.quota.get_quota(state.owner.id)).used == 1


@pytest.mark.parametrize("operation,code", [("find_session", "CHAT_UNAVAILABLE"),
                                          ("recent_messages", "CHAT_UNAVAILABLE"),
                                          ("append_assistant_message", "CHAT_SAVE_FAILED")])
async def test_database_errors_are_safe_and_release_admission_for_retry(operation, code):
    async with application() as state:
        path, _ = await seed_reply(state)
        before = dict(state.chat._messages)
        error = OperationalError("SELECT private_table", None, Exception("private-database-password"))
        with patch.object(state.chat, operation, AsyncMock(side_effect=error)):
            response = await state.client.post(path + "/explanations", json={"mode": "simplify"})
        assert response.status_code == 503 and response.json()["error"]["code"] == code
        assert all(secret not in response.text for secret in ("private_table", "private-database-password"))
        assert state.chat._messages == before and (await state.quota.get_quota(state.owner.id)).used == 1
        assert (await state.client.post(path + "/explanations", json={"mode": "simplify"})).status_code == 201


async def test_parallel_explanation_requests_do_not_trigger_two_paid_generations():
    async with application() as state:
        path, _ = await seed_reply(state)
        entered, release = asyncio.Event(), asyncio.Event()
        original = state.model.generate
        async def delayed(messages):
            entered.set()
            await release.wait()
            return await original(messages)
        state.model.generate = delayed
        pending = asyncio.create_task(state.client.post(path + "/explanations", json={"mode": "simplify"}))
        await asyncio.wait_for(entered.wait(), timeout=3)
        try:
            blocked = await state.client.post(path + "/explanations", json={"mode": "example"})
            assert blocked.status_code == 409 and blocked.json()["error"]["code"] == "CHAT_BUSY"
        finally:
            release.set()
            assert (await pending).status_code == 201
        assert len(state.model.calls) == 2 and len(state.chat._messages) == 3
