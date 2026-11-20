"""Real quiz flows use a fake provider, with no synthetic quiz returned on failure."""

from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
import asyncio
import json
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.document_repository import InMemoryDocumentRepository, SubjectRecord, TopicRecord
from app.repositories.quiz_repository import InMemoryQuizRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.catalog_service import CatalogService
from app.services.document_retrieval import DocumentRetrievalService
from app.services.llm_client import LLMReply
from app.services.quiz_service import QuizService
from app.utils.errors import AppError
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


class FakeQuizModel:
    def __init__(self, content=None, failure=None):
        self.content = json.dumps(valid_payload(), ensure_ascii=False) if content is None else content
        self.failure = failure
        self.calls = []

    async def generate(self, messages):
        self.calls.append(deepcopy(messages))
        if self.failure:
            raise self.failure
        return LLMReply(self.content, 77)


@asynccontextmanager
async def quiz_app(*, model=None, private_context=False):
    users, catalog = InMemoryUserRepository(), InMemoryCatalogRepository()
    owner = await users.create(name="Nguyễn Văn An", email="an@example.com", password_hash="private-user-password-hash", role="LEARNER")
    other = await users.create(name="Người khác", email="other@example.com", password_hash="other-hash", role="LEARNER")
    admin = await users.create(name="Quản trị", email="admin@example.com", password_hash="admin-hash", role="ADMIN")
    subject_id = catalog.add_subject("Toán", "THPT")
    description = "Phép cộng và phương trình"
    settings = Settings(jwt_secret="quiz-generation-secret-" + "x" * 40, llm_api_key="private-provider-key")
    if private_context:
        description += f"; Nguyễn Văn An; an@example.com; password: privatepass; api_key: {settings.llm_api_key}"
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phương trình", description)
    documents = InMemoryDocumentRepository(
        subjects=[SubjectRecord(subject_id, "Toán", "THPT")],
        topics=[TopicRecord(topic_id, subject_id, "Phương trình", "Đại số")],
    )
    if private_context:
        doc = await documents.create(topic_id=topic_id, title="Tài liệu Nguyễn Văn An", file_path="private-file.txt")
        await documents.finish_processing(doc.id, chunks=["Phương trình. Nguyễn Văn An, an@example.com; password: sourcepass"])
        documents._documents[doc.id] = replace(documents._documents[doc.id], is_active=True)
    repository = InMemoryQuizRepository(catalog)
    model = model or FakeQuizModel()
    app = create_app(
        user_repository=users, catalog_repository=catalog, quiz_repository=repository,
        document_repository=documents, llm_client=model, settings=settings,
    )
    # Direct injection keeps the route test independent of main's provider wiring tests.
    app.state.quiz_service = QuizService(
        repository, catalog_service=CatalogService(catalog), llm_client=model, settings=settings,
        retrieval_service=DocumentRetrievalService(documents),
    )
    headers = {
        user.id: {"Authorization": "Bearer " + app.state.token_service.create_access_token(user.id).access_token}
        for user in (owner, other, admin)
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        headers=headers[owner.id],
    ) as client:
        yield SimpleNamespace(
            client=client, app=app, users=users, catalog=catalog, repository=repository,
            owner=owner, other=other, admin=admin, headers=headers, model=model,
            topic_id=topic_id, subject_id=subject_id,
        )


@pytest.mark.parametrize("difficulty", ["easy", "medium", "hard"])
async def test_generate_persists_real_model_questions_and_returns_safe_quiz(difficulty):
    async with quiz_app() as state:
        response = await state.client.post("/api/quizzes", json={"topicId": state.topic_id, "difficulty": difficulty})
        assert response.status_code == 201, response.text
        assert response.headers["cache-control"] == "no-store"
        quiz = response.json()["quiz"]
        assert quiz["difficulty"] == difficulty and quiz["status"] == "in_progress"
        assert len(quiz["questions"]) == 5
        assert state.repository._quizzes[quiz["id"]].user_id == state.owner.id
        assert len(state.model.calls) == 1
        sent = json.loads(state.model.calls[0][-1]["content"])
        assert sent["difficulty"] == difficulty and sent["topic"]["name"] == "Phương trình"
        assert "correctAnswer" not in response.text and "explanation" not in response.text


async def test_generation_filters_private_topic_source_and_response_copies():
    generated = valid_payload()
    generated["questions"][0]["question_text"] = "Nguyễn Văn An, an@example.com: 1 + 1?"
    generated["questions"][0]["explanation"] = "api_key: private-provider-key"
    async with quiz_app(model=FakeQuizModel(json.dumps(generated, ensure_ascii=False)), private_context=True) as state:
        response = await state.client.post("/api/quizzes", json={"topicId": state.topic_id, "difficulty": "easy"})
        assert response.status_code == 201, response.text
        payload = json.dumps(state.model.calls, ensure_ascii=False)
        for private in (state.owner.name, state.owner.email, "privatepass", "sourcepass", "private-provider-key", state.owner.password_hash):
            assert private not in payload and private not in response.text
        assert "reference_passages" in payload and "Phương trình" in payload
        assert "private-file.txt" not in payload


async def test_complete_json_fence_is_supported_without_accepting_arbitrary_prose():
    model = FakeQuizModel("```json\n" + json.dumps(valid_payload()) + "\n```")
    async with quiz_app(model=model) as state:
        assert (await state.client.post("/api/quizzes", json={"topicId": state.topic_id, "difficulty": "easy"})).status_code == 201


@pytest.mark.parametrize("content", ["not json", "Here is your quiz: {}", '{"questions":[]}', json.dumps({"questions": valid_payload()["questions"][:4]})])
async def test_invalid_model_output_never_creates_a_partial_quiz(content):
    async with quiz_app(model=FakeQuizModel(content)) as state:
        response = await state.client.post("/api/quizzes", json={"topicId": state.topic_id, "difficulty": "easy"})
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "QUIZ_INVALID_RESPONSE"
        assert state.repository._quizzes == {}


@pytest.mark.parametrize("duplicate", ["question", "option"])
async def test_generated_duplicate_questions_or_options_are_rejected(duplicate):
    payload = valid_payload()
    if duplicate == "question":
        payload["questions"][4]["question_text"] = payload["questions"][0]["question_text"]
    else:
        payload["questions"][4]["options"]["D"] = "  " + payload["questions"][4]["options"]["A"] + "  "
    async with quiz_app(model=FakeQuizModel(json.dumps(payload))) as state:
        response = await state.client.post("/api/quizzes", json={"topicId": state.topic_id, "difficulty": "easy"})
        assert response.status_code == 502
        assert state.repository._quizzes == {}


@pytest.mark.parametrize("code,status", [("LLM_TIMEOUT", 504), ("LLM_RATE_LIMITED", 429), ("LLM_NOT_CONFIGURED", 503)])
async def test_provider_errors_preserve_retry_without_creating_quizzes(code, status):
    async with quiz_app(model=FakeQuizModel(failure=AppError(status, code, "Provider unavailable"))) as state:
        response = await state.client.post("/api/quizzes", json={"topicId": state.topic_id, "difficulty": "easy"})
        assert response.status_code == status and response.json()["error"]["code"] == code
        assert state.repository._quizzes == {}
        state.model.failure = None
        assert (await state.client.post("/api/quizzes", json={"topicId": state.topic_id, "difficulty": "easy"})).status_code == 201


@pytest.mark.parametrize("closed", ["topic", "subject", "missing"])
async def test_generation_checks_open_catalog_before_calling_model(closed):
    async with quiz_app() as state:
        topic_id = state.topic_id
        if closed == "topic":
            state.catalog._topics[topic_id]["is_active"] = False
        elif closed == "subject":
            state.catalog._subjects[state.subject_id]["is_active"] = False
        else:
            topic_id = 2147483647
        response = await state.client.post("/api/quizzes", json={"topicId": topic_id, "difficulty": "easy"})
        assert response.status_code == 404
        assert state.model.calls == [] and state.repository._quizzes == {}


@pytest.mark.parametrize("body", [
    {"topicId": True, "difficulty": "easy"}, {"topicId": 1, "difficulty": "unknown"},
    {"topicId": 1, "difficulty": "easy", "userId": 99},
    {"topicId": 1, "difficulty": "easy", "questions": []},
])
async def test_client_cannot_supply_identity_or_answer_key(body):
    async with quiz_app() as state:
        assert (await state.client.post("/api/quizzes", json=body)).status_code == 422
        assert state.model.calls == []


async def test_owner_only_completed_results_include_choices_and_explanations():
    async with quiz_app() as state:
        quiz = (await state.client.post("/api/quizzes", json={"topicId": state.topic_id, "difficulty": "medium"})).json()["quiz"]
        path = f"/api/quizzes/{quiz['id']}/result"
        pending = await state.client.get(path)
        assert pending.status_code == 409 and "explanation" not in pending.text
        for intruder in (state.other, state.admin):
            foreign = await state.client.get(path, headers=state.headers[intruder.id])
            missing = await state.client.get("/api/quizzes/2147483647/result", headers=state.headers[intruder.id])
            assert foreign.status_code == missing.status_code == 404 and foreign.json() == missing.json()
        response = await state.client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": [
            {"questionId": question["id"], "userAnswer": "B" if index < 3 else "A"}
            for index, question in enumerate(quiz["questions"])
        ]})
        assert response.status_code == 200
        result_response = await state.client.get(path)
        assert result_response.status_code == 200 and result_response.headers["cache-control"] == "no-store"
        result = result_response.json()["result"]
        assert (result["score"], result["correctCount"], result["totalCount"]) == (60, 3, 5)
        assert result["status"] == "completed" and result["completedAt"]
        assert [question["isCorrect"] for question in result["questions"]] == [True, True, True, False, False]
        assert all(question["correctAnswer"] == "B" and question["explanation"] for question in result["questions"])
        assert state.owner.email not in result_response.text and state.owner.password_hash not in result_response.text
        assert "correctAnswer" not in (await state.client.get(f"/api/quizzes/{quiz['id']}")).text
        assert len(state.model.calls) == 1  # Grading and result reads never call the provider.


@pytest.mark.parametrize("path", ["/api/quizzes", "/api/quizzes/1/result"])
async def test_generation_and_result_require_active_authentication(path):
    async with quiz_app() as state:
        method = "POST" if path == "/api/quizzes" else "GET"
        kwargs = {"json": {"topicId": state.topic_id, "difficulty": "easy"}} if method == "POST" else {}
        assert (await state.client.request(method, path, headers={"Authorization": ""}, **kwargs)).status_code == 401
        state.users._users[state.owner.id] = replace(state.owner, is_active=False)
        assert (await state.client.request(method, path, **kwargs)).status_code == 403
        assert state.model.calls == []


@pytest.mark.parametrize("invalid_first", [False, True])
async def test_main_wires_shared_provider_quota_and_real_quiz_result_flow(invalid_first):
    users, catalog = InMemoryUserRepository(), InMemoryCatalogRepository()
    owner = await users.create(name="Người học", email="main-wiring@example.com", password_hash="hash", role="LEARNER")
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phép cộng")
    model = FakeQuizModel()
    app = create_app(
        user_repository=users, catalog_repository=catalog, llm_client=model,
        settings=Settings(jwt_secret="main-ai-quiz-wiring-" + "x" * 40),
    )
    token = app.state.token_service.create_access_token(owner.id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        quota_before = await client.get("/api/ai/quota")
        assert quota_before.status_code == 200, quota_before.text
        if invalid_first:
            model.content = '{"questions":[]}'
            failed = await client.post("/api/quizzes", json={"topicId": topic_id, "difficulty": "easy"})
            assert failed.status_code == 502
            assert (await client.get("/api/ai/quota")).json() == quota_before.json()
            model.content = json.dumps(valid_payload())
        quiz_response = await client.post("/api/quizzes", json={"topicId": topic_id, "difficulty": "easy"})
        assert quiz_response.status_code == 201, quiz_response.text
        quiz = quiz_response.json()["quiz"]
        quota_after = await client.get("/api/ai/quota")
        before = quota_before.json().get("quota", quota_before.json())
        after = quota_after.json().get("quota", quota_after.json())
        assert after["remaining"] == before["remaining"] - 1
        submitted = await client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": [
            {"questionId": question["id"], "userAnswer": "B"} for question in quiz["questions"]
        ]})
        assert submitted.status_code == 200 and submitted.json()["submission"]["score"] == 100
        result = await client.get(f"/api/quizzes/{quiz['id']}/result")
        assert result.status_code == 200 and result.json()["result"]["score"] == 100
        assert (await client.get("/api/ai/quota")).json() == quota_after.json()
        assert len(model.calls) == (2 if invalid_first else 1)


async def test_cancelling_generation_keeps_quota_guard_until_persistence_finishes():
    async with quiz_app() as state:
        quota = state.app.state.ai_quota_service
        service = state.app.state.quiz_service
        service._quota = quota
        started, finish = asyncio.Event(), asyncio.Event()
        original_create = state.repository.create_quiz

        async def delayed_save(*args, **kwargs):
            started.set()
            await finish.wait()
            return await original_create(*args, **kwargs)

        state.repository.create_quiz = delayed_save
        generation = asyncio.create_task(service.generate_quiz(state.owner, state.topic_id, "easy"))
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            generation.cancel()
            await asyncio.sleep(0)
            assert not generation.done()
            with pytest.raises(AppError) as caught:
                async with quota.generation(state.owner.id):
                    pytest.fail("Account admission must remain locked while a cancelled request is saving")
            assert caught.value.code == "AI_REQUEST_BUSY"
        finally:
            finish.set()
            with pytest.raises(asyncio.CancelledError):
                await generation

        assert len(state.repository._quizzes) == 1
        assert (await quota.get_quota(state.owner.id)).used == 1
        async with quota.generation(state.owner.id):
            pass
