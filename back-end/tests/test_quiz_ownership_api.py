"""TK-082: guessed IDs and account hints cannot reveal another account's quiz."""

from contextlib import asynccontextmanager
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.quiz_repository import InMemoryQuizRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.quiz_service import QuizService
from app.utils.errors import AppError
from test_quiz_validation import valid_payload


pytestmark = pytest.mark.anyio


@asynccontextmanager
async def quiz_api():
    users, catalog = InMemoryUserRepository(), InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phép cộng")
    repository = InMemoryQuizRepository(catalog)
    owner = await users.create(name="Chủ bài", email="owner@example.com", password_hash="owner-hash", role="LEARNER")
    other = await users.create(name="Người học khác", email="other@example.com", password_hash="other-hash", role="LEARNER")
    admin = await users.create(name="Quản trị", email="admin@example.com", password_hash="admin-hash", role="ADMIN")
    app = create_app(
        user_repository=users, catalog_repository=catalog, quiz_repository=repository,
        settings=Settings(jwt_secret="quiz-ownership-tests-" + "x" * 40),
    )
    payload = valid_payload()
    payload["questions"][0]["question_text"] = "OWNER_QUESTION_PRIVATE_SENTINEL"
    payload["questions"][0]["explanation"] = "OWNER_ANSWER_EXPLANATION_PRIVATE_SENTINEL"
    saved = await app.state.quiz_service.save_generated_quiz(owner, topic_id, "medium", payload)
    other_payload = valid_payload()
    other_payload["questions"][0]["question_text"] = "OTHER_QUESTION_PRIVATE_SENTINEL"
    other_saved = await app.state.quiz_service.save_generated_quiz(other, topic_id, "easy", other_payload)
    headers = {
        user.id: {"Authorization": "Bearer " + app.state.token_service.create_access_token(user.id).access_token}
        for user in (owner, other, admin)
    }
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
    ) as client:
        yield SimpleNamespace(
            client=client, app=app, users=users, owner=owner, other=other, admin=admin,
            repository=repository, catalog=catalog, subject_id=subject_id, topic_id=topic_id,
            quiz_id=saved.quiz.id, other_quiz_id=other_saved.quiz.id, headers=headers,
        )


async def test_owner_reads_saved_quiz_with_only_its_questions_and_no_answer_key():
    async with quiz_api() as state:
        response = await state.client.get(f"/api/quizzes/{state.quiz_id}", headers=state.headers[state.owner.id])
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        quiz = response.json()["quiz"]
        assert quiz["id"] == state.quiz_id and quiz["topicId"] == state.topic_id
        assert len(quiz["questions"]) == 5
        assert [item["position"] for item in quiz["questions"]] == [1, 2, 3, 4, 5]
        assert quiz["questions"][0]["questionText"] == "OWNER_QUESTION_PRIVATE_SENTINEL"
        assert "OTHER_QUESTION_PRIVATE_SENTINEL" not in response.text
        assert "OWNER_ANSWER_EXPLANATION_PRIVATE_SENTINEL" not in response.text
        assert all(set(item) == {"id", "position", "questionText", "options"} for item in quiz["questions"])
        for private in ("correct_answer", "correctAnswer", "explanation", "user_id", "userId", state.owner.email, state.owner.password_hash):
            assert private not in response.text
        other = await state.client.get(f"/api/quizzes/{state.other_quiz_id}", headers=state.headers[state.other.id])
        assert other.status_code == 200
        assert other.json()["quiz"]["questions"][0]["questionText"] == "OTHER_QUESTION_PRIVATE_SENTINEL"


@pytest.mark.parametrize("account", ["other", "admin"])
async def test_foreign_and_missing_quiz_ids_are_indistinguishable_even_for_admin(account):
    async with quiz_api() as state:
        headers = state.headers[getattr(state, account).id]
        before = deepcopy(state.repository._quizzes)
        foreign = await state.client.get(f"/api/quizzes/{state.quiz_id}", headers=headers)
        missing = await state.client.get("/api/quizzes/2147483647", headers=headers)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.headers["cache-control"] == missing.headers["cache-control"] == "no-store"
        assert foreign.json() == missing.json() == {
            "error": {"code": "QUIZ_NOT_FOUND", "message": "Không tìm thấy bài luyện tập của bạn."},
        }
        assert "OWNER_QUESTION_PRIVATE_SENTINEL" not in foreign.text
        assert state.repository._quizzes == before


@pytest.mark.parametrize("query", ["user_id", "userId", "ownerId"])
async def test_client_account_override_never_controls_resource_ownership(query):
    async with quiz_api() as state:
        own = await state.client.get(
            f"/api/quizzes/{state.quiz_id}?{query}={state.other.id}", headers=state.headers[state.owner.id],
        )
        assert own.status_code == 200
        assert own.json()["quiz"]["id"] == state.quiz_id
        foreign = await state.client.get(
            f"/api/quizzes/{state.quiz_id}?{query}={state.owner.id}", headers=state.headers[state.other.id],
        )
        assert foreign.status_code == 404


@pytest.mark.parametrize("access,status", [("guest", 401), ("invalid", 401), ("inactive", 403)])
async def test_quiz_reads_require_current_active_authenticated_account(access, status):
    async with quiz_api() as state:
        headers = {}
        if access == "invalid":
            headers = {"Authorization": "Bearer invalid-token"}
        elif access == "inactive":
            headers = state.headers[state.owner.id]
            state.users._users[state.owner.id] = replace(state.owner, is_active=False)
        response = await state.client.get(f"/api/quizzes/{state.quiz_id}", headers=headers)
        assert response.status_code == status
        assert response.headers["cache-control"] == "no-store"
        assert "OWNER_QUESTION_PRIVATE_SENTINEL" not in response.text


@pytest.mark.parametrize("quiz_id", ["0", "-1", "2147483648", "not-an-id", "1.5"])
async def test_invalid_ids_do_not_reveal_quiz_data(quiz_id):
    async with quiz_api() as state:
        response = await state.client.get(f"/api/quizzes/{quiz_id}", headers=state.headers[state.owner.id])
        assert response.status_code == 422
        assert "OWNER_QUESTION_PRIVATE_SENTINEL" not in response.text


@pytest.mark.parametrize("closed", ["topic", "subject"])
async def test_owner_can_still_read_history_when_catalog_is_disabled(closed):
    async with quiz_api() as state:
        if closed == "topic":
            state.catalog._topics[state.topic_id]["is_active"] = False
        else:
            state.catalog._subjects[state.subject_id]["is_active"] = False
        response = await state.client.get(f"/api/quizzes/{state.quiz_id}", headers=state.headers[state.owner.id])
        assert response.status_code == 200
        foreign = await state.client.get(f"/api/quizzes/{state.quiz_id}", headers=state.headers[state.other.id])
        assert foreign.status_code == 404


async def test_repository_requires_owner_when_reading_quiz_and_questions():
    async with quiz_api() as state:
        record = await state.repository.find_quiz(state.owner.id, state.quiz_id)
        assert record.user_id == state.owner.id and len(record.questions) == 5
        assert await state.repository.find_quiz(state.other.id, state.quiz_id) is None
        assert await state.repository.find_quiz(state.admin.id, state.quiz_id) is None
        assert await state.repository.find_quiz(state.owner.id, 999) is None


async def test_service_rejects_foreign_record_even_if_repository_returns_it():
    async with quiz_api() as state:
        class BrokenRepository:
            async def find_quiz(self, user_id, quiz_id):
                return state.repository._quizzes[state.quiz_id]
        with pytest.raises(AppError) as caught:
            await QuizService(BrokenRepository()).get_quiz(state.other, state.quiz_id)
        assert caught.value.status_code == 404


async def test_database_read_errors_use_safe_message():
    async with quiz_api() as state:
        class BrokenRepository:
            async def find_quiz(self, user_id, quiz_id):
                raise SQLAlchemyError("private SQL account and answer details")
        state.app.state.quiz_service = QuizService(BrokenRepository())
        response = await state.client.get(f"/api/quizzes/{state.quiz_id}", headers=state.headers[state.owner.id])
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert response.json()["error"]["code"] == "QUIZ_UNAVAILABLE"
        assert "private SQL" not in response.text
