"""TK-058: API ghi 01 quiz_answer / question_id, gắn submitted answer."""

import pytest
from pydantic import ValidationError

from app.schemas.quiz import SubmitQuizAnswersRequest
from test_quiz_ownership_api import quiz_api


def test_submit_quiz_answers_schema_requires_exact_five_valid_choices():
    valid = SubmitQuizAnswersRequest.model_validate({
        "answers": [
            {"questionId": 1, "userAnswer": "A"},
            {"questionId": 2, "userAnswer": "B"},
            {"questionId": 3, "userAnswer": "C"},
            {"questionId": 4, "userAnswer": "D"},
            {"questionId": 5, "userAnswer": "A"},
        ]
    })
    assert len(valid.answers) == 5

    for invalid in (
        {"answers": []},
        {"answers": [{"questionId": i, "userAnswer": "A"} for i in range(1, 5)]},
        {"answers": [{"questionId": i, "userAnswer": "A"} for i in range(1, 7)]},
        {"answers": [{"questionId": i, "userAnswer": "E"} for i in range(1, 6)]},
        {"answers": [{"questionId": i, "userAnswer": "A", "isCorrect": True} for i in range(1, 6)]},
    ):
        with pytest.raises(ValidationError):
            SubmitQuizAnswersRequest.model_validate(invalid)


@pytest.mark.anyio
async def test_submit_answers_persists_one_answer_per_question_and_blocks_resubmit():
    async with quiz_api() as state:
        quiz = (await state.client.get(f"/api/quizzes/{state.quiz_id}", headers=state.headers[state.owner.id])).json()["quiz"]
        choices = ["A", "B", "C", "D", "B"]
        payload = {
            "answers": [
                {"questionId": q["id"], "userAnswer": choice}
                for q, choice in zip(quiz["questions"], choices)
            ]
        }

        foreign = await state.client.post(
            f"/api/quizzes/{state.quiz_id}/submit", json=payload, headers=state.headers[state.other.id],
        )
        assert foreign.status_code == 404

        response = await state.client.post(
            f"/api/quizzes/{state.quiz_id}/submit", json=payload, headers=state.headers[state.owner.id],
        )
        assert response.status_code == 200, response.text
        submission = response.json()["submission"]
        assert submission["quizId"] == state.quiz_id
        assert submission["status"] == "accepted"
        assert submission["savedCount"] == 5
        assert submission["answers"] == payload["answers"]

        for q, choice in zip(quiz["questions"], choices):
            saved = state.repository._answers[q["id"]]
            assert saved.user_answer == choice
            assert saved.is_correct is (choice == "B")

        duplicate = await state.client.post(
            f"/api/quizzes/{state.quiz_id}/submit", json=payload, headers=state.headers[state.owner.id],
        )
        assert duplicate.status_code == 409
        assert duplicate.json()["error"]["code"] == "ALREADY_SUBMITTED"


@pytest.mark.anyio
async def test_submit_answers_rejects_duplicate_or_foreign_question_ids():
    async with quiz_api() as state:
        quiz = (await state.client.get(f"/api/quizzes/{state.quiz_id}", headers=state.headers[state.owner.id])).json()["quiz"]
        dup_payload = {"answers": [{"questionId": quiz["questions"][0]["id"], "userAnswer": "A"} for _ in range(5)]}
        dup_resp = await state.client.post(
            f"/api/quizzes/{state.quiz_id}/submit", json=dup_payload, headers=state.headers[state.owner.id],
        )
        assert dup_resp.status_code == 422
        assert dup_resp.json()["error"]["code"] == "INVALID_ANSWERS"

        wrong_ids = {"answers": [{"questionId": 9000 + i, "userAnswer": "A"} for i in range(5)]}
        wrong_resp = await state.client.post(
            f"/api/quizzes/{state.quiz_id}/submit", json=wrong_ids, headers=state.headers[state.owner.id],
        )
        assert wrong_resp.status_code == 422
        assert wrong_resp.json()["error"]["code"] == "INVALID_ANSWERS"
        assert state.repository._answers == {}
