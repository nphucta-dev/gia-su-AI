"""TK-059 grades once from the server key and publishes consistent completion/progress."""

import asyncio
from copy import deepcopy
from dataclasses import replace
from decimal import Decimal

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.services.quiz_service import QuizService
from app.utils.errors import AppError
from test_quiz_ownership_api import quiz_api
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


def payload_for(state, correct=3, quiz_id=None):
    questions = state.repository._quizzes[quiz_id or state.quiz_id].questions
    return {"answers": [
        {"questionId": question.id, "userAnswer": "B" if index < correct else "A"}
        for index, question in enumerate(questions)
    ]}


def answer_map(payload):
    return {item["questionId"]: item["userAnswer"] for item in payload["answers"]}


@pytest.mark.parametrize("correct", range(6))
async def test_submit_grades_zero_to_hundred_and_updates_progress_once(correct):
    async with quiz_api() as state:
        payload = payload_for(state, correct)
        headers = state.headers[state.owner.id]
        path = f"/api/quizzes/{state.quiz_id}"
        response = await state.client.post(path + "/submit", headers=headers, json=payload)
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        body = response.json()["submission"]
        assert body["status"] == "accepted" and body["savedCount"] == 5
        assert body["quizStatus"] == "completed" and body["score"] == correct * 20
        assert body["correctCount"] == correct and body["totalCount"] == 5
        assert body["answers"] == payload["answers"]
        assert body["completedAt"].endswith("Z")
        for private in ("correctAnswer", "correct_answer", "explanation", state.owner.email):
            assert private not in response.text
        stored = state.repository._quizzes[state.quiz_id]
        assert stored.status == "completed" and stored.score == Decimal(correct * 20)
        assert stored.completed_at == body["completedAt"]
        progress = next(iter(state.repository.progress_repository._records.values()))
        assert progress.user_id == state.owner.id and progress.topic_id == state.topic_id
        assert (progress.total_quizzes, progress.correct_count, progress.total_count) == (1, correct, 5)
        assert progress.mastery_percent == correct * 20
        assert progress.last_studied_at == body["completedAt"]
        snapshot = deepcopy(state.repository.progress_repository._records)
        assert (await state.client.post(path + "/submit", headers=headers, json=payload)).status_code == 409
        assert (await state.client.post(path + "/grade", headers=headers)).status_code == 409
        assert state.repository.progress_repository._records == snapshot
        assert len(state.repository._answers) == 5
        readback = await state.client.get(path, headers=headers)
        assert readback.status_code == 200 and readback.json()["quiz"]["status"] == "completed"
        assert "explanation" not in readback.text and "correctAnswer" not in readback.text


async def test_multiple_quizzes_accumulate_progress_and_rounded_mastery():
    async with quiz_api() as state:
        headers = state.headers[state.owner.id]
        second = await state.app.state.quiz_service.save_generated_quiz(state.owner, state.topic_id, "hard", valid_payload())
        for quiz_id, correct in ((state.quiz_id, 3), (second.quiz.id, 4)):
            response = await state.client.post(
                f"/api/quizzes/{quiz_id}/submit", headers=headers, json=payload_for(state, correct, quiz_id),
            )
            assert response.status_code == 200
        rows = list(state.repository.progress_repository._records.values())
        assert len(rows) == 1
        assert (rows[0].total_quizzes, rows[0].correct_count, rows[0].total_count, rows[0].mastery_percent) == (2, 7, 10, Decimal("70.00"))


async def test_legacy_saved_choices_are_immutable_and_correctness_is_recomputed():
    async with quiz_api() as state:
        path = f"/api/quizzes/{state.quiz_id}"
        headers = state.headers[state.owner.id]
        before = await state.client.post(path + "/grade", headers=headers)
        assert before.status_code == 409 and before.json()["error"]["code"] == "ANSWERS_REQUIRED"
        original = payload_for(state, 3)
        saved = await state.repository.save_answers(state.owner.id, state.quiz_id, answer_map(original))
        for item in saved:
            state.repository._answers[item.question_id] = replace(item, is_correct=False)
        original_ids_and_dates = {item.question_id: (item.id, item.created_at) for item in saved}
        replacement = await state.client.post(path + "/grade", headers=headers, json=payload_for(state, 5))
        assert replacement.status_code == 422
        assert state.repository._quizzes[state.quiz_id].status == "in_progress"
        assert state.repository.progress_repository._records == {}
        response = await state.client.post(path + "/grade", headers=headers)
        assert response.status_code == 200
        body = response.json()["submission"]
        assert body["score"] == 60 and body["answers"] == original["answers"]
        assert sum(item.is_correct for item in state.repository._answers.values()) == 3
        assert {qid: (item.id, item.created_at) for qid, item in state.repository._answers.items()} == original_ids_and_dates
        assert (await state.client.post(path + "/grade", headers=headers)).status_code == 409


async def test_partial_legacy_answers_are_not_completed_or_counted():
    async with quiz_api() as state:
        await state.repository.save_answers(state.owner.id, state.quiz_id, answer_map(payload_for(state)))
        state.repository._answers.pop(next(iter(state.repository._answers)))
        snapshot = deepcopy(state.repository._answers)
        response = await state.client.post(f"/api/quizzes/{state.quiz_id}/grade", headers=state.headers[state.owner.id])
        assert response.status_code == 409
        assert state.repository._quizzes[state.quiz_id].status == "in_progress"
        assert state.repository._answers == snapshot
        assert state.repository.progress_repository._records == {}


@pytest.mark.parametrize("who", ["other", "admin"])
@pytest.mark.parametrize("suffix", ["submit", "grade"])
async def test_other_accounts_and_admin_cannot_grade_private_quizzes(who, suffix):
    async with quiz_api() as state:
        user = getattr(state, who)
        options = {"json": payload_for(state)} if suffix == "submit" else {}
        path = f"/api/quizzes/{state.quiz_id}/{suffix}?user_id={state.owner.id}"
        foreign = await state.client.post(path, headers=state.headers[user.id], **options)
        missing = await state.client.post(f"/api/quizzes/2147483647/{suffix}", headers=state.headers[user.id], **options)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json()
        assert foreign.headers["cache-control"] == "no-store"
        assert state.repository._answers == {} and state.repository.progress_repository._records == {}


@pytest.mark.parametrize("mutation", ["duplicate", "foreign", "few", "bad-choice", "forged-score"])
async def test_invalid_submission_does_not_publish_answers_or_progress(mutation):
    async with quiz_api() as state:
        payload = payload_for(state)
        if mutation == "duplicate":
            payload["answers"][4]["questionId"] = payload["answers"][0]["questionId"]
        elif mutation == "foreign":
            payload["answers"][4]["questionId"] = state.repository._quizzes[state.other_quiz_id].questions[0].id
        elif mutation == "few":
            payload["answers"].pop()
        elif mutation == "bad-choice":
            payload["answers"][4]["userAnswer"] = "E"
        else:
            payload["score"] = 100
        response = await state.client.post(f"/api/quizzes/{state.quiz_id}/submit", headers=state.headers[state.owner.id], json=payload)
        assert response.status_code == 422
        assert state.repository._quizzes[state.quiz_id].status == "in_progress"
        assert state.repository._answers == {} and state.repository.progress_repository._records == {}


async def test_concurrent_submit_and_legacy_grade_do_not_count_twice():
    async with quiz_api() as state:
        path = f"/api/quizzes/{state.quiz_id}"
        headers = state.headers[state.owner.id]
        responses = await asyncio.gather(
            state.client.post(path + "/submit", headers=headers, json=payload_for(state)),
            state.client.post(path + "/grade", headers=headers),
        )
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert len(state.repository._answers) == 5
        row = next(iter(state.repository.progress_repository._records.values()))
        assert row.total_quizzes == 1 and row.total_count == 5


async def test_concurrent_conflicting_submissions_keep_only_winning_answers_and_score():
    async with quiz_api() as state:
        path = f"/api/quizzes/{state.quiz_id}/submit"
        headers = state.headers[state.owner.id]
        payloads = [payload_for(state, correct) for correct in (0, 5)]
        responses = await asyncio.gather(*(
            state.client.post(path, headers=headers, json=payload) for payload in payloads
        ))
        assert sorted(response.status_code for response in responses) == [200, 409]
        winner = next(index for index, response in enumerate(responses) if response.status_code == 200)
        loser = responses[1 - winner]
        assert loser.json()["error"]["code"] == "ALREADY_SUBMITTED"
        expected_score = winner * 100
        quiz = state.repository._quizzes[state.quiz_id]
        assert quiz.score == expected_score and quiz.status == "completed"
        assert len(state.repository._answers) == 5
        assert {qid: answer.user_answer for qid, answer in state.repository._answers.items()} == answer_map(payloads[winner])
        row = next(iter(state.repository.progress_repository._records.values()))
        assert (row.total_quizzes, row.correct_count, row.total_count, row.mastery_percent) == (1, winner * 5, 5, expected_score)
        result = await state.client.get(f"/api/quizzes/{state.quiz_id}/result", headers=headers)
        assert result.status_code == 200
        assert result.json()["result"]["score"] == expected_score


async def test_disabled_catalog_does_not_prevent_finishing_owned_quiz():
    async with quiz_api() as state:
        state.catalog._subjects[state.subject_id]["is_active"] = False
        state.catalog._topics[state.topic_id]["is_active"] = False
        response = await state.client.post(f"/api/quizzes/{state.quiz_id}/submit", headers=state.headers[state.owner.id], json=payload_for(state))
        assert response.status_code == 200 and response.json()["submission"]["quizStatus"] == "completed"


@pytest.mark.parametrize("suffix", ["submit", "grade"])
@pytest.mark.parametrize("access,status", [("guest", 401), ("invalid", 401), ("inactive", 403)])
async def test_grading_requires_active_authentication(suffix, access, status):
    async with quiz_api() as state:
        headers = {} if access == "guest" else {"Authorization": "Bearer invalid"} if access == "invalid" else state.headers[state.owner.id]
        if access == "inactive":
            state.users._users[state.owner.id] = replace(state.owner, is_active=False)
        options = {"json": payload_for(state)} if suffix == "submit" else {}
        response = await state.client.post(f"/api/quizzes/{state.quiz_id}/{suffix}", headers=headers, **options)
        assert response.status_code == status
        assert response.headers["cache-control"] == "no-store"
        assert state.repository._answers == {} and state.repository.progress_repository._records == {}


async def test_grading_storage_failure_is_safe_and_retryable():
    class BrokenRepository:
        async def grade_quiz(self, *args):
            raise SQLAlchemyError("private-db-details")
    async with quiz_api() as state:
        with pytest.raises(AppError) as caught:
            await QuizService(BrokenRepository()).grade_saved_answers(state.owner, state.quiz_id)
        assert caught.value.status_code == 503
        assert caught.value.code == "QUIZ_SAVE_FAILED"
        assert "private-db-details" not in caught.value.message
