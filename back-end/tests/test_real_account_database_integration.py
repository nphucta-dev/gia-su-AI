"""Regression flows for real account history/context/sources in isolated MySQL."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.models import ChatMessage, ChatSession, Document, DocumentChunk, Subject, Topic, User
from app.services.llm_client import LLMReply
from test_database_integration import database, make_catalog
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


class RecordingProvider:
    def __init__(self):
        self.calls = []

    async def generate(self, messages):
        self.calls.append(messages)
        return LLMReply("Hãy đối chiếu điều kiện và kiểm tra từng bước.", 20)


def application(sessions, tmp_path, model=None):
    return create_app(
        session_factory=sessions, upload_dir=tmp_path, llm_client=model or RecordingProvider(),
        settings=Settings(jwt_secret="account-regression-mysql-" + "x" * 40),
    )


def authorization(app, user_id):
    return {"Authorization": "Bearer " + app.state.token_service.create_access_token(user_id).access_token}


async def test_mysql_quiz_history_is_private_paginated_and_retains_closed_catalog(database, tmp_path):
    _, sessions = database
    with sessions.begin() as db:
        owner, subject, topic = make_catalog(db)
        admin = User(email=f"admin-{uuid4().hex}@example.com", full_name="Admin", password_hash="test-hash", role="ADMIN")
        db.add(admin)
        db.flush()
        owner_id, admin_id, subject_id, topic_id = owner.id, admin.id, subject.id, topic.id
    model = RecordingProvider()
    app = application(sessions, tmp_path, model)
    owner = await app.state.user_repository.find_by_id(owner_id)
    service = app.state.quiz_service
    first = (await service.save_generated_quiz(owner, topic_id, "easy", valid_payload())).quiz
    second = (await service.save_generated_quiz(owner, topic_id, "hard", valid_payload())).quiz
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        auth = authorization(app, owner_id)
        graded = await client.post(f"/api/quizzes/{first.id}/submit", headers=auth, json={"answers": [
            {"questionId": question.id, "userAnswer": "B" if index < 3 else "A"}
            for index, question in enumerate(first.questions)
        ]})
        assert graded.status_code == 200, graded.text
        with sessions.begin() as db:
            db.get(Subject, subject_id).is_active = False
            db.get(Topic, topic_id).is_active = False
        pages = []
        for offset in (0, 1, 2):
            response = await client.get(f"/api/quizzes?limit=1&offset={offset}", headers=auth)
            assert response.status_code == 200, response.text
            assert response.headers["cache-control"] == "no-store"
            assert not any(key in response.text for key in ("correctAnswer", "explanation", "questions", "password_hash", "userId"))
            pages.append(response.json())
        assert [pages[0]["quizzes"][0]["id"], pages[1]["quizzes"][0]["id"]] == [second.id, first.id]
        assert [page["hasMore"] for page in pages] == [True, False, False]
        assert pages[2]["quizzes"] == []
        assert pages[0]["quizzes"][0]["status"] == "in_progress" and pages[0]["quizzes"][0]["score"] is None
        completed = pages[1]["quizzes"][0]
        assert completed["status"] == "completed" and completed["score"] == 60 and completed["completedAt"]
        assert completed["topicId"] == topic_id and completed["topicName"] and completed["subjectName"]
        foreign = await client.get(f"/api/quizzes?userId={owner_id}", headers=authorization(app, admin_id))
        assert foreign.status_code == 200 and foreign.json()["quizzes"] == []
        assert (await client.get("/api/quizzes")).status_code == 401
    assert model.calls == []


async def test_mysql_long_context_keeps_question_and_highest_hint_outside_recent_window(database, tmp_path):
    _, sessions = database
    yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    with sessions.begin() as db:
        owner, _, topic = make_catalog(db)
        chat = ChatSession(user_id=owner.id, topic_id=topic.id, title="Long context", created_at=yesterday, updated_at=yesterday)
        db.add(chat)
        db.flush()
        question = ChatMessage(session_id=chat.id, role="user", content="ORIGINAL_QUESTION: explain quadratic roots", created_at=yesterday)
        db.add(question)
        db.flush()
        highest = ChatMessage(session_id=chat.id, role="assistant", content="Highest hint already delivered", hint_level=3, created_at=yesterday)
        db.add(highest)
        db.flush()
        for index in range(40):
            db.add(ChatMessage(session_id=chat.id, role="assistant", content=f"Explanation number {index}", created_at=yesterday))
        db.flush()
        owner_id, session_id, question_id, highest_id = owner.id, chat.id, question.id, highest.id
    provider = RecordingProvider()
    app = application(sessions, tmp_path, provider)
    repository = app.state.chat_service._repository
    recent = await repository.recent_messages(owner_id, session_id, limit=24)
    assert question_id not in {message.id for message in recent}
    context = await repository.context_messages(owner_id, session_id, limit=24)
    ids = [message.id for message in context]
    assert ids == sorted(set(ids)) and len(ids) <= 26
    assert question_id in ids and highest_id in ids and context[-1].content == "Explanation number 39"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test", headers=authorization(app, owner_id),
    ) as client:
        path = f"/api/chat/sessions/{session_id}"
        hint = await client.post(path + "/hints")
        assert hint.status_code == 409 and hint.json()["error"]["code"] == "HINT_LIMIT_REACHED"
        assert provider.calls == []
        explanation = await client.post(path + "/explanations", json={"mode": "simplify"})
        assert explanation.status_code == 201, explanation.text
        prompt = str(provider.calls[-1])
        assert "ORIGINAL_QUESTION" in prompt and "Explanation number 39" in prompt
        solution = await client.post(path + "/solution", json={"confirmed": True})
        assert solution.status_code == 201, solution.text
        assert solution.json()["assistantMessage"]["isFullSolution"] is True
        assert len(provider.calls) == 2
        hint = await client.post(path + "/hints")
        assert hint.status_code == 409 and hint.json()["error"]["code"] == "HINT_LIMIT_REACHED"


async def test_mysql_sources_and_history_agree_after_admin_disables_document(database, tmp_path):
    _, sessions = database
    with sessions.begin() as db:
        owner, _, topic = make_catalog(db)
        admin = User(email=f"sources-admin-{uuid4().hex}@example.com", full_name="Admin", password_hash="test-hash", role="ADMIN")
        db.add(admin)
        document = Document(topic_id=topic.id, title="Real source", file_path="source.txt", status="ready", is_active=True)
        chat = ChatSession(user_id=owner.id, topic_id=topic.id, title="Sources")
        db.add_all([document, chat])
        db.flush()
        chunk = DocumentChunk(document_id=document.id, chunk_index=0, content="Phương trình bậc hai có biệt thức delta.")
        db.add(chunk)
        db.flush()
        message = ChatMessage(session_id=chat.id, role="assistant", content="Stored reply", source_refs=[{
            "documentId": document.id, "chunkId": chunk.id, "title": document.title, "chunkIndex": 0,
        }])
        db.add(message)
        db.flush()
        owner_id, admin_id, document_id, session_id, message_id = owner.id, admin.id, document.id, chat.id, message.id
    app = application(sessions, tmp_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        owner_headers = authorization(app, owner_id)
        source_path = f"/api/chat/messages/{message_id}/sources"
        before = await client.get(source_path, headers=owner_headers)
        assert before.status_code == 200, before.text
        assert before.json()["hasSources"] is True and before.json()["sourceRefs"][0]["available"] is True
        disabled = await client.patch(f"/api/admin/documents/{document_id}", headers=authorization(app, admin_id), json={"isActive": False})
        assert disabled.status_code == 200, disabled.text
        after = await client.get(source_path, headers=owner_headers)
        assert after.status_code == 200 and after.json()["hasSources"] is False
        assert after.json()["sourceRefs"][0]["available"] is False and after.json()["notice"]
        history = await client.get(f"/api/chat/sessions/{session_id}/messages", headers=owner_headers)
        assert history.status_code == 200
        stored = next(row for row in history.json()["messages"] if row["id"] == message_id)
        assert stored["content"] == "Stored reply" and stored["sourcesStatus"] == "unavailable"
        assert stored["sourceRefs"][0]["available"] is False
        assert (await client.get(source_path, headers=authorization(app, admin_id))).status_code == 404
