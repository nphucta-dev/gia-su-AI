"""TK-082 ownership checks against an isolated, randomly named MySQL test DB."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import select

from app.config import Settings
from app.main import create_app
from app.models import ChatMessage, ChatSession, LearningProgress, Subject, Topic, User
from app.repositories.sqlalchemy_chat_repository import SqlAlchemyChatRepository
from test_database_integration import RecordingChatModel, database, make_catalog
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio
MISSING_ID = 2**31 - 1


def setup_accounts(sessions):
    with sessions.begin() as db:
        owner, subject, topic = make_catalog(db)
        other = User(email=f"other-{uuid4().hex}@example.com", full_name="Người khác", password_hash="test-only")
        admin = User(email=f"admin-{uuid4().hex}@example.com", full_name="Quản trị", password_hash="test-only", role="ADMIN")
        db.add_all([other, admin])
        db.flush()
        ids = (owner.id, other.id, admin.id, subject.id, topic.id)
    model = RecordingChatModel()
    app = create_app(session_factory=sessions, settings=Settings(jwt_secret="ownership-test-key-" + "x" * 40), llm_client=model)

    def headers(user_id):
        token = app.state.token_service.create_access_token(user_id).access_token
        return {"Authorization": f"Bearer {token}"}

    return SimpleNamespace(
        app=app, model=model, owner_id=ids[0], other_id=ids[1], admin_id=ids[2],
        subject_id=ids[3], topic_id=ids[4], headers=headers,
    )


def client_for(state, user_id=None):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=state.app, raise_app_exceptions=False), base_url="http://test",
        headers=state.headers(user_id) if user_id is not None else {},
    )


def no_store(response, expected_status):
    assert response.status_code == expected_status, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


async def save_quiz(state, user_id, marker):
    user = await state.app.state.user_repository.find_by_id(user_id)
    payload = valid_payload()
    for position, item in enumerate(payload["questions"], start=1):
        item["question_text"] = f"{marker}: câu {position}"
        item["explanation"] = f"PRIVATE_EXPLANATION_{marker}"
    return await state.app.state.quiz_service.save_generated_quiz(user, state.topic_id, "medium", payload)


async def test_mysql_quiz_reads_scope_parent_and_questions_to_authenticated_owner(database):
    _, sessions = database
    state = setup_accounts(sessions)
    own = await save_quiz(state, state.owner_id, "OWN_QUIZ_CONTENT")
    other = await save_quiz(state, state.other_id, "FOREIGN_QUIZ_CONTENT")
    admin = await save_quiz(state, state.admin_id, "ADMIN_QUIZ_CONTENT")
    own_path = f"/api/quizzes/{own.quiz.id}"
    async with client_for(state, state.owner_id) as client:
        body = no_store(await client.get(own_path), 200)
        assert [item["id"] for item in body["quiz"]["questions"]] == [item.id for item in own.quiz.questions]
        assert [item["position"] for item in body["quiz"]["questions"]] == [1, 2, 3, 4, 5]
        assert body["quiz"]["status"] == "in_progress"
        for question in body["quiz"]["questions"]:
            assert set(question) == {"id", "position", "questionText", "options"}
        assert "FOREIGN_QUIZ_CONTENT" not in str(body) and "ADMIN_QUIZ_CONTENT" not in str(body)
        assert "PRIVATE_EXPLANATION" not in str(body) and "correct_answer" not in str(body)
        assert no_store(await client.get(own_path, params={"user_id": state.other_id, "userId": state.admin_id}), 200) == body
        missing = no_store(await client.get(f"/api/quizzes/{MISSING_ID}"), 404)
        for foreign_id in (other.quiz.id, admin.quiz.id):
            assert no_store(await client.get(f"/api/quizzes/{foreign_id}", params={"user_id": state.other_id}), 404) == missing
        for intruder_id in (state.other_id, state.admin_id):
            assert no_store(await client.get(own_path, headers=state.headers(intruder_id), params={"userId": state.owner_id}), 404) == missing
    async with client_for(state, state.admin_id) as client:
        assert no_store(await client.get(f"/api/quizzes/{admin.quiz.id}"), 200)["quiz"]["id"] == admin.quiz.id
    with sessions.begin() as db:
        db.get(Subject, state.subject_id).is_active = False
    async with client_for(state, state.owner_id) as client:
        assert no_store(await client.get(own_path), 200) == body
    assert state.model.requests == []


async def test_mysql_progress_detail_and_pagination_never_cross_account_boundaries(database):
    _, sessions = database
    state = setup_accounts(sessions)
    with sessions.begin() as db:
        second_topic = Topic(subject_id=state.subject_id, chapter_name="Chương riêng", name="Chủ đề thứ hai")
        db.add(second_topic)
        db.flush()
        records = [
            LearningProgress(user_id=state.owner_id, topic_id=state.topic_id, total_quizzes=1, correct_count=1, total_count=5, mastery_percent=Decimal("20.00"), last_studied_at=datetime(2026, 11, 17, tzinfo=timezone.utc)),
            LearningProgress(user_id=state.owner_id, topic_id=second_topic.id, total_quizzes=2, correct_count=8, total_count=10, mastery_percent=Decimal("80.00"), last_studied_at=datetime(2026, 11, 18, tzinfo=timezone.utc)),
            LearningProgress(user_id=state.other_id, topic_id=state.topic_id, total_quizzes=1, correct_count=4, total_count=5, mastery_percent=Decimal("80.00")),
            LearningProgress(user_id=state.admin_id, topic_id=state.topic_id, total_quizzes=1, correct_count=5, total_count=5, mastery_percent=Decimal("100.00")),
        ]
        db.add_all(records)
        db.flush()
        owned_ids = {records[0].id, records[1].id}
        own_id, other_id, admin_id = records[0].id, records[2].id, records[3].id
    async with client_for(state, state.owner_id) as client:
        detail = no_store(await client.get(f"/api/progress/{own_id}"), 200)
        assert detail["progress"]["correctCount"] == 1 and detail["progress"]["masteryPercent"] == 20
        assert "user_id" not in detail["progress"] and "userId" not in detail["progress"]
        first = no_store(await client.get("/api/progress", params={"limit": 1, "user_id": state.other_id}), 200)
        second = no_store(await client.get("/api/progress", params={"limit": 1, "offset": 1, "userId": state.admin_id}), 200)
        assert first["hasMore"] is True and second["hasMore"] is False
        assert {first["progress"][0]["id"], second["progress"][0]["id"]} == owned_ids
        assert no_store(await client.get("/api/progress", params={"offset": 2}), 200)["progress"] == []
        missing = no_store(await client.get(f"/api/progress/{MISSING_ID}"), 404)
        for intruder_id in (state.other_id, state.admin_id):
            assert no_store(await client.get(f"/api/progress/{own_id}", headers=state.headers(intruder_id), params={"user_id": state.owner_id}), 404) == missing
        for foreign_id in (other_id, admin_id):
            assert no_store(await client.get(f"/api/progress/{foreign_id}", params={"userId": state.other_id}), 404) == missing
        for user_id, progress_id in ((state.other_id, other_id), (state.admin_id, admin_id)):
            listing = no_store(await client.get("/api/progress", headers=state.headers(user_id), params={"userId": state.owner_id}), 200)
            assert [item["id"] for item in listing["progress"]] == [progress_id]
        with sessions.begin() as db:
            db.get(Subject, state.subject_id).is_active = False
            db.get(Topic, state.topic_id).is_active = False
        assert no_store(await client.get(f"/api/progress/{own_id}"), 200) == detail
        assert {item["id"] for item in no_store(await client.get("/api/progress"), 200)["progress"]} == owned_ids


async def test_mysql_foreign_chat_access_cannot_read_write_change_activity_or_call_model(database):
    _, sessions = database
    state = setup_accounts(sessions)
    repository = SqlAlchemyChatRepository(sessions)
    async with client_for(state, state.owner_id) as client:
        created = no_store(await client.post("/api/chat/sessions", json={"topicId": state.topic_id}), 201)
        session_id = created["session"]["id"]
        path = f"/api/chat/sessions/{session_id}"
        no_store(await client.post(path + "/messages", json={"content": "Câu hỏi riêng tư của chủ phiên"}), 201)
        own_history = no_store(await client.get(path + "/messages"), 200)
        assert [item["role"] for item in own_history["messages"]] == ["user", "assistant"]
        with sessions() as db:
            parent = db.get(ChatSession, session_id)
            activity_before = (parent.title, parent.updated_at)
            message_ids_before = list(db.scalars(select(ChatMessage.id).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id)))
        calls_before = list(state.model.requests)
        assert len(calls_before) == 1
        for intruder_id in (state.other_id, state.admin_id):
            headers = state.headers(intruder_id)
            listing = no_store(await client.get("/api/chat/sessions", headers=headers, params={"user_id": state.owner_id}), 200)
            assert listing["sessions"] == []
            for method, suffix, payload in (("GET", "", None), ("GET", "/messages", None), ("POST", "/messages", {"content": "Không được ghi vào phiên người khác"}), ("POST", "/hints", None)):
                options = {"json": payload} if payload is not None else {}
                foreign = no_store(await client.request(method, path + suffix, headers=headers, params={"userId": state.owner_id}, **options), 404)
                missing = no_store(await client.request(method, f"/api/chat/sessions/{MISSING_ID}" + suffix, headers=headers, **options), 404)
                assert foreign == missing
            assert await repository.list_messages(intruder_id, session_id, limit=20, offset=0) == []
            assert await repository.recent_messages(intruder_id, session_id) == []
            assert await repository.append_user_message(intruder_id, session_id, "Forbidden direct repository write") is None
            assert await repository.append_assistant_message(intruder_id, session_id, "Forbidden assistant write", hint_level=1, token_count=None, expected_last_id=message_ids_before[-1]) is None
        assert no_store(await client.get(path + "/messages"), 200) == own_history
        assert state.model.requests == calls_before
        with sessions() as db:
            parent = db.get(ChatSession, session_id)
            assert (parent.title, parent.updated_at) == activity_before
            assert list(db.scalars(select(ChatMessage.id).where(ChatMessage.session_id == session_id).order_by(ChatMessage.id))) == message_ids_before
        with sessions.begin() as db:
            db.get(Subject, state.subject_id).is_active = False
        assert no_store(await client.get(path + "/messages"), 200)["messages"] == own_history["messages"]


async def test_mysql_private_resources_require_current_active_account(database):
    _, sessions = database
    state = setup_accounts(sessions)
    quiz = await save_quiz(state, state.owner_id, "AUTHENTICATED_ONLY_QUESTION")
    with sessions.begin() as db:
        progress = LearningProgress(user_id=state.owner_id, topic_id=state.topic_id)
        db.add(progress)
        db.flush()
        progress_id = progress.id
    paths = (f"/api/quizzes/{quiz.quiz.id}", "/api/progress", f"/api/progress/{progress_id}")
    async with client_for(state) as client:
        for path in paths:
            no_store(await client.get(path), 401)
            no_store(await client.get(path, headers={"Authorization": "Bearer invalid-test-token"}), 401)
        with sessions.begin() as db:
            db.get(User, state.owner_id).is_active = False
        for path in paths:
            response = await client.get(path, headers=state.headers(state.owner_id))
            no_store(response, 403)
            assert "AUTHENTICATED_ONLY_QUESTION" not in response.text
