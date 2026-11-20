"""TK-065 on a randomly named MySQL test database, never the project database."""

from decimal import Decimal

import httpx
import pytest
from sqlalchemy import event

from app.config import Settings
from app.main import create_app
from app.models import ChatMessage, ChatSession, Quiz
from app.repositories.sqlalchemy_dashboard_repository import SqlAlchemyDashboardRepository
from test_database_integration import database, make_catalog
from test_dashboard_api import NoAi, NoQuota, ZERO
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


async def test_mysql_owner_aggregates_do_not_multiply_quizzes_by_sessions_or_messages(database):
    engine, sessions = database
    with sessions.begin() as db:
        owner, subject, topic = make_catalog(db)
        other, _, other_topic = make_catalog(db)
        owner_id, other_id = owner.id, other.id
        for score in (Decimal("0"), Decimal("60"), Decimal("100"), None):
            db.add(Quiz(user_id=owner.id, topic_id=topic.id, difficulty="easy", status="completed", score=score))
        db.add(Quiz(user_id=owner.id, topic_id=topic.id, difficulty="easy", status="in_progress", score=100))
        db.add(Quiz(user_id=other.id, topic_id=other_topic.id, difficulty="easy", status="completed", score=100))
        for _ in range(4):
            db.add(ChatSession(user_id=owner.id, topic_id=topic.id))
        other_session = ChatSession(user_id=other.id, topic_id=other_topic.id)
        db.add(other_session)
        db.flush()
        for _ in range(7):
            db.add(ChatMessage(session_id=other_session.id, role="user", content="Stored message"))
        subject.is_active = topic.is_active = False

    captured = []
    def capture(connection, cursor, statement, parameters, context, executemany):
        captured.append(statement)
    event.listen(engine, "before_cursor_execute", capture)
    try:
        stats = await SqlAlchemyDashboardRepository(sessions).get_stats(owner_id)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert len(captured) == 1  # Aggregate in SQL; do not load full quiz/question/message histories.
    assert stats.total_quizzes == 4 and stats.total_chat_sessions == 4
    assert round(stats.average_score, 2) == Decimal("53.33")
    other_stats = await SqlAlchemyDashboardRepository(sessions).get_stats(other_id)
    assert other_stats.total_quizzes == other_stats.total_chat_sessions == 1
    assert other_stats.average_score == Decimal("100")
    empty = await SqlAlchemyDashboardRepository(sessions).get_stats(2**31 - 1)
    assert empty.total_quizzes == empty.total_chat_sessions == empty.average_score == 0


async def test_mysql_dashboard_tracks_real_quiz_submission_and_survives_app_reload(database):
    _, sessions = database
    with sessions.begin() as db:
        owner, _, topic = make_catalog(db)
        owner_id, topic_id = owner.id, topic.id
    settings = Settings(jwt_secret="dashboard-sql-tests-" + "x" * 40)
    app = create_app(session_factory=sessions, settings=settings, llm_client=NoAi())
    owner = await app.state.user_repository.find_by_id(owner_id)
    headers = {"Authorization": "Bearer " + app.state.token_service.create_access_token(owner_id).access_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        assert (await client.get("/api/dashboard")).json() == ZERO
        created = await client.post("/api/chat/sessions", json={"topicId": topic_id})
        assert created.status_code == 201
        quiz = (await app.state.quiz_service.save_generated_quiz(owner, topic_id, "medium", valid_payload())).quiz
        assert (await client.get("/api/dashboard")).json()["dashboard"] == {
            "totalQuizzes": 0, "averageScore": 0, "totalChatSessions": 1,
        }
        payload = {"answers": [{"questionId": q.id, "userAnswer": "B" if index < 3 else "A"}
                               for index, q in enumerate(quiz.questions)]}
        assert (await client.post(f"/api/quizzes/{quiz.id}/submit", json=payload)).status_code == 200
        assert (await client.post(f"/api/quizzes/{quiz.id}/submit", json=payload)).status_code == 409
    restored = create_app(session_factory=sessions, settings=settings, llm_client=NoAi())
    restored.state.quota_service = restored.state.ai_quota_service = NoQuota()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=restored), base_url="http://test", headers=headers) as client:
        response = await client.get("/api/dashboard?userId=2147483647")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"dashboard": {"totalQuizzes": 1, "averageScore": 60, "totalChatSessions": 1}}


async def test_mysql_score_average_preserves_decimal_rounding_with_null_legacy_scores(database):
    _, sessions = database
    with sessions.begin() as db:
        owner, _, topic = make_catalog(db)
        owner_id = owner.id
        for score in (Decimal("0.01"), Decimal("0"), None):
            db.add(Quiz(user_id=owner.id, topic_id=topic.id, difficulty="easy", status="completed", score=score))
    app = create_app(session_factory=sessions, settings=Settings(jwt_secret="dashboard-rounding-" + "x" * 40))
    headers = {"Authorization": "Bearer " + app.state.token_service.create_access_token(owner_id).access_token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        assert (await client.get("/api/dashboard")).json() == {
            "dashboard": {"totalQuizzes": 3, "averageScore": 0.01, "totalChatSessions": 0},
        }
