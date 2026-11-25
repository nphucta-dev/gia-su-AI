"""Optional provider smoke test: two live calls, synthetic data, no MySQL writes."""

import os

import httpx
import pytest

from app.config import load_settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.user_repository import InMemoryUserRepository


@pytest.mark.anyio
@pytest.mark.skipif(os.environ.get("RUN_LIVE_LLM_TESTS") != "1", reason="Bật RUN_LIVE_LLM_TESTS=1 để gọi provider thật.")
async def test_live_vietnamese_chat_and_five_question_quiz():
    settings = load_settings()
    users = InMemoryUserRepository()
    user = await users.create(
        name="LLM Smoke Learner", email="llm-smoke@example.invalid",
        password_hash="unused-smoke-hash", role="LEARNER",
    )
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(
        subject_id, "Đại số", "Phương trình bậc hai",
        "Phương trình ax² + bx + c = 0 (a khác 0), biệt thức Δ = b² − 4ac.",
    )
    app = create_app(user_repository=users, catalog_repository=catalog, settings=settings)
    token = app.state.token_service.create_access_token(user.id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        created = await client.post("/api/chat/sessions", json={"topicId": topic_id})
        assert created.status_code == 201, created.text
        session_id = created.json()["session"]["id"]
        chat = await client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "Em nên bắt đầu giải x² − 5x + 6 = 0 như thế nào?"},
        )
        assert chat.status_code == 201, chat.text
        assistant = chat.json()["assistantMessage"]
        assert assistant["hintLevel"] == 1 and not assistant["isFullSolution"]
        assert any(ord(char) > 127 for char in assistant["content"])
        history = (await client.get(f"/api/chat/sessions/{session_id}/messages")).json()["messages"]
        assert [message["role"] for message in history] == ["user", "assistant"]

        generated = await client.post("/api/quizzes", json={"topicId": topic_id, "difficulty": "easy"})
        assert generated.status_code == 201, generated.text
        quiz = generated.json()["quiz"]
        assert len(quiz["questions"]) == 5
        assert all(set(question["options"]) == set("ABCD") for question in quiz["questions"])
        assert "correctAnswer" not in generated.text and "explanation" not in generated.text
        record = await app.state.quiz_service._repository.find_quiz(user.id, quiz["id"])
        assert all(question.correct_answer in "ABCD" and question.explanation for question in record.questions)
        assert (await client.get("/api/ai/quota")).json()["used"] == 2
