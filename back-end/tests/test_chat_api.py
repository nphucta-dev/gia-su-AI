"""API chat với model giả lập; câu hỏi/lịch sử được lưu thật trong repository."""

import asyncio
import copy
import json
from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.llm_client import LLMReply
from app.utils.errors import AppError

pytestmark = pytest.mark.anyio
ROOT = "/api/chat/sessions"
JWT_SECRET = "chat-api-tests-" + "x" * 40
PRIVATE_KEY = "private-api-key-for-chat-tests"
_DEFAULT_CLIENT = object()


class FakeLLM:
    def __init__(self, content="Bạn thử xác định dữ kiện đã biết trước nhé?"):
        self.content = content
        self.calls = []
        self.failure = None

    async def generate(self, messages):
        self.calls.append(copy.deepcopy(messages))
        if self.failure is not None:
            raise self.failure
        return LLMReply(content=self.content, token_count=17)


@asynccontextmanager
async def api(*, role="LEARNER", model=_DEFAULT_CLIENT, repository_factory=InMemoryChatRepository):
    users, catalog = InMemoryUserRepository(), InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phương trình", "Cách tiếp cận phương trình bậc hai")
    chat = repository_factory(catalog)
    current = await users.create(name="Nguyễn Văn An", email="an@example.com", password_hash="private-account-hash", role=role)
    other = await users.create(name="Người học khác", email="other@example.com", password_hash="other-hash", role="LEARNER")
    model = FakeLLM() if model is _DEFAULT_CLIENT else model
    app = create_app(
        user_repository=users, catalog_repository=catalog, chat_repository=chat,
        llm_client=model, settings=Settings(jwt_secret=JWT_SECRET, llm_api_key=PRIVATE_KEY),
    )
    token = app.state.token_service.create_access_token(current.id).access_token
    other_token = app.state.token_service.create_access_token(other.id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        yield SimpleNamespace(
            client=client, app=app, users=users, catalog=catalog, repository=chat, model=model,
            current=current, other=other, other_headers={"Authorization": "Bearer " + other_token},
            subject_id=subject_id, topic_id=topic_id,
        )


async def create_session(state, **fields):
    response = await state.client.post(ROOT, json={"topicId": state.topic_id, **fields})
    assert response.status_code == 201, response.text
    return response.json()["session"]


async def history(state, session_id):
    response = await state.client.get(f"{ROOT}/{session_id}/messages")
    assert response.status_code == 200, response.text
    return response.json()["messages"]


@pytest.mark.parametrize("role", ["LEARNER", "ADMIN"])
async def test_create_session_and_send_persisted_first_turn_with_server_controlled_metadata(role):
    async with api(role=role) as state:
        session = await create_session(state)
        assert type(session["id"]) is int and session["topicId"] == state.topic_id
        assert session["title"] is None and session["topicName"] == "Phương trình"
        assert session["subjectName"] == "Toán" and session["gradeLevel"] == "THPT"
        assert "userId" not in session and "password" not in json.dumps(session)
        response = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Giải x² − 5x + 6 = 0"})
        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        question, answer = body["userMessage"], body["assistantMessage"]
        assert question["role"] == "user" and question["hintLevel"] is None
        assert answer["role"] == "assistant" and answer["hintLevel"] == 1
        assert question["id"] < answer["id"] and answer["sessionId"] == session["id"]
        assert question["tokenCount"] is None and answer["tokenCount"] == 17
        assert question["isFullSolution"] is answer["isFullSolution"] is False
        assert datetime.fromisoformat(answer["createdAt"]).utcoffset() == timedelta(0)
        assert body["session"]["updatedAt"] == answer["createdAt"]
        assert body["session"]["title"] == "Giải x² − 5x + 6 = 0"
        assert await history(state, session["id"]) == [question, answer]
        assert [item["role"] for item in state.model.calls[0]] == ["system", "user"]


@pytest.mark.parametrize("method,suffix,body", [
    ("GET", "", None), ("POST", "", {"topicId": 1}), ("GET", "/1", None),
    ("GET", "/1/messages", None), ("POST", "/1/messages", {"content": "Câu hỏi"}),
    ("POST", "/1/hints", None),
])
@pytest.mark.parametrize("access,status", [("guest", 401), ("invalid", 401), ("inactive", 403)])
async def test_chat_routes_require_an_active_authenticated_account(method, suffix, body, access, status):
    async with api() as state:
        headers = {}
        if access == "guest":
            headers["Authorization"] = ""
        elif access == "invalid":
            headers["Authorization"] = "Bearer not-a-token"
        else:
            state.users._users[state.current.id] = replace(state.current, is_active=False)
        options = {"json": body} if body is not None else {}
        response = await state.client.request(method, ROOT + suffix, headers=headers, **options)
        assert response.status_code == status
        assert response.headers["cache-control"] == "no-store"
        assert state.repository._sessions == state.repository._messages == {}
        assert state.model.calls == []


async def test_owned_chat_history_is_filtered_and_unavailable_ids_do_not_accept_writes():
    async with api() as state:
        session = await create_session(state)
        await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Câu hỏi riêng tư"})
        listing = await state.client.get(ROOT, headers=state.other_headers)
        assert listing.json()["sessions"] == []
        before = await history(state, session["id"])
        for method, suffix, body in (
            ("GET", "", None), ("GET", "/messages", None),
            ("POST", "/messages", {"content": "Không được ghi"}), ("POST", "/hints", None),
        ):
            options = {"json": body} if body is not None else {}
            response = await state.client.request(method, f"{ROOT}/{session['id']}{suffix}", headers=state.other_headers, **options)
            assert response.status_code == 404
            assert response.json()["error"]["code"] == "CHAT_SESSION_NOT_FOUND"
        assert await history(state, session["id"]) == before
        assert len(state.model.calls) == 1


async def test_sessions_and_messages_are_paginated_in_their_expected_order():
    async with api() as state:
        first, second, third = [await create_session(state) for _ in range(3)]
        await state.client.post(f"{ROOT}/{first['id']}/messages", json={"content": "Phiên có hoạt động gần nhất"})
        listing = (await state.client.get(ROOT, params={"limit": 2})).json()
        assert [item["id"] for item in listing["sessions"]] == [first["id"], third["id"]]
        assert listing["hasMore"] is True and listing["limit"] == 2 and listing["offset"] == 0
        tail = (await state.client.get(ROOT, params={"limit": 2, "offset": 2})).json()
        assert [item["id"] for item in tail["sessions"]] == [second["id"]]
        assert tail["hasMore"] is False
        assert (await state.client.post(f"{ROOT}/{first['id']}/hints")).status_code == 201
        assert (await state.client.post(f"{ROOT}/{first['id']}/hints")).status_code == 201
        page = (await state.client.get(f"{ROOT}/{first['id']}/messages", params={"limit": 2})).json()
        later = (await state.client.get(f"{ROOT}/{first['id']}/messages", params={"limit": 2, "offset": 2})).json()
        assert page["hasMore"] is True and later["hasMore"] is False
        messages = page["messages"] + later["messages"]
        assert [item["id"] for item in messages] == sorted(item["id"] for item in messages)
        assert [item["role"] for item in messages] == ["user", "assistant", "assistant", "assistant"]


@pytest.mark.parametrize("parent", ["topic", "subject"])
async def test_closed_catalog_blocks_new_learning_but_keeps_old_history_readable(parent):
    async with api() as state:
        session = await create_session(state)
        await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Nội dung đã lưu"})
        collection, key = (state.catalog._topics, state.topic_id) if parent == "topic" else (state.catalog._subjects, state.subject_id)
        collection[key]["is_active"] = False
        assert (await state.client.post(ROOT, json={"topicId": state.topic_id})).status_code == 404
        assert (await state.client.get(f"{ROOT}/{session['id']}")).status_code == 200
        assert len(await history(state, session["id"])) == 2
        for suffix, options in (("messages", {"json": {"content": "Câu hỏi mới"}}), ("hints", {})):
            response = await state.client.post(f"{ROOT}/{session['id']}/{suffix}", **options)
            assert response.status_code == 409 and response.json()["error"]["code"] == "TOPIC_CLOSED"
        assert len(state.model.calls) == 1


async def test_hint_levels_advance_only_after_success_and_reset_for_a_new_question():
    async with api() as state:
        session = await create_session(state)
        assert (await state.client.post(f"{ROOT}/{session['id']}/hints")).json()["error"]["code"] == "CHAT_QUESTION_REQUIRED"
        await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Câu hỏi thứ nhất"})
        state.model.failure = AppError(504, "LLM_TIMEOUT", "Model chưa phản hồi.")
        failed = await state.client.post(f"{ROOT}/{session['id']}/hints")
        assert failed.status_code == 504
        assert [item["hintLevel"] for item in await history(state, session["id"])] == [None, 1]
        state.model.failure = None
        for level in (2, 3):
            response = await state.client.post(f"{ROOT}/{session['id']}/hints")
            assert response.status_code == 201 and response.json()["userMessage"] is None
            assert response.json()["assistantMessage"]["hintLevel"] == level
        call_count = len(state.model.calls)
        exhausted = await state.client.post(f"{ROOT}/{session['id']}/hints")
        assert exhausted.status_code == 409 and exhausted.json()["error"]["code"] == "HINT_LIMIT_REACHED"
        assert len(state.model.calls) == call_count
        next_question = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Câu hỏi tiếp theo"})
        assert next_question.status_code == 201 and next_question.json()["assistantMessage"]["hintLevel"] == 1


async def test_missing_model_configuration_retains_question_without_fake_assistant():
    async with api(model=None) as state:
        session = await create_session(state)
        response = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Câu hỏi cần giữ khi chưa có model"})
        assert response.status_code == 503 and response.json()["error"]["code"] == "LLM_NOT_CONFIGURED"
        stored = await history(state, session["id"])
        assert len(stored) == 1 and stored[0]["role"] == "user"
        assert stored[0]["content"] == "Câu hỏi cần giữ khi chưa có model"
        assert PRIVATE_KEY not in response.text and JWT_SECRET not in response.text


@pytest.mark.parametrize("status,code", [(429, "LLM_RATE_LIMITED"), (502, "LLM_INVALID_RESPONSE"), (504, "LLM_TIMEOUT")])
async def test_model_failure_does_not_erase_question_or_advance_hint(status, code):
    fake = FakeLLM()
    fake.failure = AppError(status, code, "Không thể lấy phản hồi model.")
    async with api(model=fake) as state:
        session = await create_session(state)
        response = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Bài cần giải"})
        assert response.status_code == status and response.json()["error"]["code"] == code
        assert len(await history(state, session["id"])) == 1
        fake.failure = None
        recovered = await state.client.post(f"{ROOT}/{session['id']}/hints")
        assert recovered.status_code == 201 and recovered.json()["assistantMessage"]["hintLevel"] == 1
        assert recovered.json()["userMessage"] is None
        assert len(await history(state, session["id"])) == 2


async def test_only_redacted_academic_copy_is_sent_to_model_while_private_history_retains_question():
    raw = f"Nguyễn Văn An; an@example.com; password: MatKhauTest!; api_key: {PRIVATE_KEY}; Giải x² = 4."
    fake = FakeLLM(f"Nguyễn Văn An, an@example.com, {PRIVATE_KEY}, {JWT_SECRET}: bạn hãy kiểm tra dữ kiện.")
    async with api(model=fake) as state:
        session = await create_session(state)
        response = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": raw})
        assert response.status_code == 201
        payload = json.dumps(fake.calls, ensure_ascii=False)
        for private in (state.current.name, state.current.email, "MatKhauTest!", PRIVATE_KEY, JWT_SECRET, state.current.password_hash):
            assert private not in payload
        assert all("user_id" not in message and "password_hash" not in message for message in fake.calls[0])
        answer = response.json()["assistantMessage"]["content"]
        for private in (state.current.name, state.current.email, PRIVATE_KEY, JWT_SECRET):
            assert private not in answer
        assert (await history(state, session["id"]))[0]["content"] == raw


async def test_context_only_contains_recent_messages_from_the_current_session():
    async with api() as state:
        session = await create_session(state)
        other = await create_session(state)
        await state.repository.append_user_message(state.current.id, other["id"], "PRIVATE_OTHER_SESSION_SENTINEL")
        for index in range(20):
            await state.repository.append_user_message(state.current.id, session["id"], f"QUESTION_{index:02d}_SENTINEL")
        response = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "LATEST_QUESTION_SENTINEL"})
        assert response.status_code == 201
        messages = state.model.calls[-1]
        assert len(messages) <= 12 and sum(len(item["content"]) for item in messages) <= 20000
        payload = json.dumps(messages, ensure_ascii=False)
        assert "LATEST_QUESTION_SENTINEL" in payload and "QUESTION_19_SENTINEL" in payload
        assert "QUESTION_00_SENTINEL" not in payload and "PRIVATE_OTHER_SESSION_SENTINEL" not in payload
        assert len(await history(state, session["id"])) == 22


async def test_client_cannot_choose_assistant_role_or_hint_level():
    async with api() as state:
        session = await create_session(state)
        response = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Giả mạo", "role": "assistant", "hintLevel": 3})
        assert response.status_code == 422
        assert await history(state, session["id"]) == [] and state.model.calls == []


async def test_pending_generation_keeps_history_readable_and_rejects_overlapping_writes():
    class WaitingLLM(FakeLLM):
        def __init__(self):
            super().__init__()
            self.started, self.release = asyncio.Event(), asyncio.Event()

        async def generate(self, messages):
            self.started.set()
            await self.release.wait()
            return await super().generate(messages)

    fake = WaitingLLM()
    async with api(model=fake) as state:
        session = await create_session(state)
        pending = asyncio.create_task(state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Câu hỏi đang chờ"}))
        try:
            await asyncio.wait_for(fake.started.wait(), timeout=2)
            assert len(await history(state, session["id"])) == 1
            for suffix, options in (("messages", {"json": {"content": "Không được ghi chồng"}}), ("hints", {})):
                response = await state.client.post(f"{ROOT}/{session['id']}/{suffix}", **options)
                assert response.status_code == 409 and response.json()["error"]["code"] == "CHAT_BUSY"
        finally:
            fake.release.set()
            result = await pending
        assert result.status_code == 201 and len(await history(state, session["id"])) == 2


async def test_reply_for_a_stale_snapshot_is_discarded_without_losing_new_user_message():
    fake = FakeLLM()
    async with api(model=fake) as state:
        session = await create_session(state)

        async def generate(messages):
            await state.repository.append_user_message(state.current.id, session["id"], "Tin từ tiến trình khác")
            return LLMReply(content="Phản hồi của ngữ cảnh đã cũ", token_count=12)

        fake.generate = generate
        response = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Câu hỏi trước"})
        assert response.status_code == 409 and response.json()["error"]["code"] == "CHAT_CHANGED"
        assert [message["role"] for message in await history(state, session["id"])] == ["user", "user"]


async def test_failed_assistant_database_write_retains_user_question_without_exposing_internal_error():
    class FailingRepository(InMemoryChatRepository):
        async def append_assistant_message(self, *args, **kwargs):
            raise RuntimeError("private database detail")

    async with api(repository_factory=FailingRepository) as state:
        session = await create_session(state)
        response = await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Giữ câu hỏi này"})
        assert response.status_code == 500 and "private database detail" not in response.text
        assert [message["role"] for message in await history(state, session["id"])] == ["user"]
