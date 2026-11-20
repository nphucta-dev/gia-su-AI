"""Generation/result persistence uses only the existing random MySQL fixture."""

import json

import httpx
import pytest
from sqlalchemy import func, select

from app.config import Settings
from app.main import create_app
from app.models import Quiz, QuizQuestion
from app.services.llm_client import LLMReply
from app.services.quiz_service import QuizService
from test_database_integration import database, make_catalog
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


class QuizModel:
    def __init__(self, content=None):
        self.content = content if content is not None else json.dumps(valid_payload(), ensure_ascii=False)
        self.calls = 0

    async def generate(self, messages):
        self.calls += 1
        return LLMReply(self.content, 50)


def app_for_quiz(sessions, model):
    with sessions.begin() as db:
        user, _, topic = make_catalog(db)
        owner_id, topic_id = user.id, topic.id
    settings = Settings(jwt_secret="ai-quiz-mysql-test-" + "x" * 40)
    app = create_app(session_factory=sessions, llm_client=model, settings=settings)
    app.state.quiz_service = QuizService(
        app.state.quiz_service._repository, catalog_service=app.state.catalog_service,
        llm_client=model, settings=settings, retrieval_service=app.state.document_retrieval_service,
    )
    token = app.state.token_service.create_access_token(owner_id).access_token
    return app, owner_id, topic_id, {"Authorization": "Bearer " + token}


async def test_mysql_generated_quiz_can_be_graded_and_reloaded_with_private_explanations(database):
    _, sessions = database
    model = QuizModel()
    app, owner_id, topic_id, headers = app_for_quiz(sessions, model)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test", headers=headers,
    ) as client:
        generated = await client.post("/api/quizzes", json={"topicId": topic_id, "difficulty": "hard"})
        assert generated.status_code == 201, generated.text
        quiz = generated.json()["quiz"]
        assert "correctAnswer" not in generated.text and "explanation" not in generated.text
        assert (await client.get(f"/api/quizzes/{quiz['id']}/result")).status_code == 409
        submitted = await client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": [
            {"questionId": question["id"], "userAnswer": "B" if index < 4 else "A"}
            for index, question in enumerate(quiz["questions"])
        ]})
        assert submitted.status_code == 200 and submitted.json()["submission"]["score"] == 80
        result_response = await client.get(f"/api/quizzes/{quiz['id']}/result")
        assert result_response.status_code == 200, result_response.text
        result = result_response.json()["result"]
        assert result["score"] == 80 and result["correctCount"] == 4 and result["totalCount"] == 5
        assert all(question["correctAnswer"] == "B" and question["explanation"] for question in result["questions"])
        assert (await client.get("/api/progress")).json()["progress"][0]["masteryPercent"] == 80
    assert model.calls == 1
    with sessions() as db:
        saved = db.get(Quiz, quiz["id"])
        assert saved.user_id == owner_id and saved.status == "completed"


async def test_mysql_invalid_generation_has_no_quiz_or_question_to_read(database):
    _, sessions = database
    app, owner_id, topic_id, headers = app_for_quiz(sessions, QuizModel('{"questions":[]}'))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test", headers=headers,
    ) as client:
        response = await client.post("/api/quizzes", json={"topicId": topic_id, "difficulty": "easy"})
        assert response.status_code == 502 and response.json()["error"]["code"] == "QUIZ_INVALID_RESPONSE"
    with sessions() as db:
        assert db.scalar(select(func.count()).select_from(Quiz).where(Quiz.user_id == owner_id)) == 0
        assert db.scalar(select(func.count()).select_from(QuizQuestion).join(Quiz).where(Quiz.user_id == owner_id)) == 0
