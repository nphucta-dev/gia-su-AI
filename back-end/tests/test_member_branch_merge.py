"""Contracts brought by member branches remain usable after integration."""
import pytest
from test_ai_chat_complete import application
from test_quiz_validation import valid_payload
from app.schemas.quiz import SubmitQuizAnswersRequest

pytestmark = pytest.mark.anyio

async def test_member_feedback_sources_quota_and_result_contracts():
    async with application() as state:
        reply = await state.client.post(f"/api/chat/sessions/{state.session_id}/messages", json={"content": "Ph??ng tr?nh b?c hai"})
        message_id = reply.json()["assistantMessage"]["id"]
        feedback = await state.client.patch(f"/api/chat/messages/{message_id}/feedback", json={"feedback": 1})
        assert feedback.status_code == 200 and feedback.json()["message"]["feedback"] == 1
        sources = await state.client.get(f"/api/chat/messages/{message_id}/sources")
        assert sources.status_code == 200 and sources.json()["hasSources"]
        quiz = (await state.app.state.quiz_service.save_generated_quiz(state.owner, state.topic_id, "easy", valid_payload())).quiz
        await state.app.state.quiz_service.submit_answers(state.owner, quiz.id, SubmitQuizAnswersRequest.model_validate({"answers": [{"questionId": q.id, "userAnswer": "B"} for q in quiz.questions]}))
        result = await state.app.state.quiz_service.get_quiz_result(state.owner, quiz.id)
        assert result.result.id == quiz.id and result.result.score == 100
        old_quota = (await state.client.get("/api/quota")).json()["quota"]
        quota = (await state.client.get("/api/ai/quota")).json()
        assert old_quota["remaining"] == quota["remaining"] == 28
        review = await state.client.get("/api/progress/review-topics")
        assert review.status_code == 200
