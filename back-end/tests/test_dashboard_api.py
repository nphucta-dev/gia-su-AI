"""TK-065: summary reads from the app's real stores, scoped to the token owner."""

from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.user_repository import InMemoryUserRepository
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio
URL = "/api/dashboard"
ZERO = {"dashboard": {"totalQuizzes": 0, "averageScore": 0.0, "totalChatSessions": 0}}


class NoAi:
    async def generate(self, *args):
        pytest.fail("Dashboard reads must not call a model")


class NoQuota:
    async def get_quota(self, *args):
        pytest.fail("Dashboard reads must remain accessible when quota is exhausted")

    async def ensure_within_quota(self, *args):
        pytest.fail("Dashboard reads must not check generation quota")

    def generation(self, *args):
        pytest.fail("Dashboard reads must not consume generation quota")


@asynccontextmanager
async def api():
    users, catalog = InMemoryUserRepository(), InMemoryCatalogRepository()
    people = [await users.create(name=name, email=email, password_hash="private-hash", role=role) for name, email, role in (
        ("Người học", "dashboard@example.com", "LEARNER"),
        ("Người khác", "other@example.com", "LEARNER"),
        ("Quản trị", "admin@example.com", "ADMIN"),
    )]
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phương trình")
    app = create_app(user_repository=users, catalog_repository=catalog, llm_client=NoAi(),
                     settings=Settings(jwt_secret="dashboard-tests-" + "x" * 40))
    def headers(person):
        return {"Authorization": "Bearer " + app.state.token_service.create_access_token(person.id).access_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
                                 base_url="http://test", headers=headers(people[0])) as client:
        yield SimpleNamespace(app=app, client=client, users=users, catalog=catalog,
                              owner=people[0], other=people[1], admin=people[2], headers=headers,
                              topic_id=topic_id, subject_id=subject_id,
                              quizzes=app.state.quiz_service._repository,
                              chat=app.state.chat_service._repository)


async def create_quiz(state, person, *, correct=None):
    quiz = (await state.app.state.quiz_service.save_generated_quiz(person, state.topic_id, "easy", valid_payload())).quiz
    if correct is not None:
        submitted = await state.client.post(f"/api/quizzes/{quiz.id}/submit", headers=state.headers(person), json={
            "answers": [{"questionId": q.id, "userAnswer": "B" if index < correct else "A"}
                        for index, q in enumerate(quiz.questions)],
        })
        assert submitted.status_code == 200, submitted.text
    return quiz


async def test_new_account_has_zero_counters_without_demo_data():
    async with api() as state:
        response = await state.client.get(URL)
        assert response.status_code == 200 and response.json() == ZERO
        assert response.headers["cache-control"] == "no-store"


async def test_summary_updates_after_grading_and_ignores_in_progress_and_other_owners():
    async with api() as state:
        first = await create_quiz(state, state.owner)
        assert (await state.client.get(URL)).json() == ZERO
        answers = {"answers": [{"questionId": q.id, "userAnswer": "B"} for q in first.questions]}
        await state.client.post(f"/api/quizzes/{first.id}/submit", json=answers)
        await create_quiz(state, state.owner, correct=3)
        await create_quiz(state, state.owner, correct=0)
        pending = await create_quiz(state, state.owner)
        # A stored score alone does not qualify an unfinished quiz for dashboard statistics.
        state.quizzes._quizzes[pending.id] = replace(state.quizzes._quizzes[pending.id], score=Decimal("100"))
        await create_quiz(state, state.other, correct=5)
        await create_quiz(state, state.admin, correct=1)
        session = None
        for _ in range(4):
            session = await state.chat.create_session(state.owner.id, state.topic_id)
        for _ in range(7):
            await state.chat.append_user_message(state.owner.id, session.id, "Tin nhắn đã lưu")
        await state.chat.create_session(state.other.id, state.topic_id)
        expected = {"dashboard": {"totalQuizzes": 3, "averageScore": 53.33, "totalChatSessions": 4}}
        assert (await state.client.get(URL)).json() == expected
        # Retries, repeated reads and a rejected second submission cannot increment counters.
        assert (await state.client.post(f"/api/quizzes/{first.id}/submit", json=answers)).status_code == 409
        assert (await state.client.get(URL)).json() == expected
        # Closed content stays part of the owner's historical totals.
        state.catalog._subjects[state.subject_id]["is_active"] = False
        state.catalog._topics[state.topic_id]["is_active"] = False
        assert (await state.client.get(URL)).json() == expected
        other = (await state.client.get(URL, headers=state.headers(state.other))).json()["dashboard"]
        admin = (await state.client.get(URL, headers=state.headers(state.admin))).json()["dashboard"]
        assert other == {"totalQuizzes": 1, "averageScore": 100.0, "totalChatSessions": 1}
        assert admin == {"totalQuizzes": 1, "averageScore": 20.0, "totalChatSessions": 0}


@pytest.mark.parametrize("owner_field", ["user_id", "userId", "owner_id", "ownerId"])
async def test_client_cannot_select_a_different_owner(owner_field):
    async with api() as state:
        await create_quiz(state, state.other, correct=5)
        response = await state.client.get(URL, params={owner_field: state.other.id})
        assert response.status_code == 200 and response.json() == ZERO
        assert state.other.email not in response.text and "private-hash" not in response.text


@pytest.mark.parametrize("access,status", [("guest", 401), ("invalid", 401), ("inactive", 403), ("deleted", 401)])
async def test_dashboard_requires_an_active_authenticated_account(access, status):
    async with api() as state:
        headers = None
        if access == "guest":
            headers = {"Authorization": ""}
        elif access == "invalid":
            headers = {"Authorization": "Bearer invalid-token"}
        elif access == "inactive":
            state.users._users[state.owner.id] = replace(state.owner, is_active=False)
        else:
            del state.users._users[state.owner.id]
        response = await state.client.get(URL, **({"headers": headers} if headers is not None else {}))
        assert response.status_code == status
        assert "dashboard" not in response.json() and response.headers["cache-control"] == "no-store"


async def test_chat_only_account_and_exhausted_quota_can_read_without_ai_calls():
    async with api() as state:
        await state.chat.create_session(state.owner.id, state.topic_id)
        state.app.state.quota_service = state.app.state.ai_quota_service = NoQuota()
        response = await state.client.get(URL)
        assert response.status_code == 200
        assert response.json() == {"dashboard": {"totalQuizzes": 0, "averageScore": 0, "totalChatSessions": 1}}


async def test_average_ignores_legacy_null_scores_and_rounds_half_up_to_two_places():
    async with api() as state:
        for score in (Decimal("0.01"), Decimal("0"), None):
            quiz = await create_quiz(state, state.owner)
            state.quizzes._quizzes[quiz.id] = replace(state.quizzes._quizzes[quiz.id], status="completed", score=score)
        assert (await state.client.get(URL)).json() == {
            "dashboard": {"totalQuizzes": 3, "averageScore": 0.01, "totalChatSessions": 0},
        }


async def test_database_failure_is_retryable_and_does_not_expose_sql_or_credentials():
    class BrokenRepository:
        async def get_stats(self, user_id):
            raise OperationalError("SELECT private_table", None, Exception("mysql-password secret"))
    async with api() as state:
        service = state.app.state.dashboard_service
        original = service._repository
        service._repository = BrokenRepository()
        response = await state.client.get(URL)
        assert response.status_code == 503
        assert response.json() == {"error": {"code": "DASHBOARD_UNAVAILABLE", "message": "Chưa thể tải thống kê học tập. Vui lòng thử lại."}}
        assert response.headers["cache-control"] == "no-store"
        service._repository = original
        assert (await state.client.get(URL)).json() == ZERO


@pytest.mark.parametrize("method", ["POST", "PATCH", "DELETE"])
async def test_dashboard_is_read_only(method):
    async with api() as state:
        assert (await state.client.request(method, URL, json={"totalQuizzes": 999})).status_code == 405
        assert (await state.client.get(URL)).json() == ZERO
