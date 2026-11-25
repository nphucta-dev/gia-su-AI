"""Real account history and chat recovery regressions; no model/network or DB writes."""

from dataclasses import replace
import json

import pytest
from sqlalchemy.exc import SQLAlchemyError

from test_ai_chat_complete import application
from test_ai_quiz_api import quiz_app
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio


async def test_quiz_history_is_owner_scoped_paginated_and_does_not_expose_answer_keys():
    async with quiz_app() as state:
        service = state.app.state.quiz_service
        owned = [await service.save_generated_quiz(state.owner, state.topic_id, "easy", valid_payload()) for _ in range(3)]
        foreign = await service.save_generated_quiz(state.other, state.topic_id, "hard", valid_payload())
        first = owned[0].quiz
        await state.client.post(f"/api/quizzes/{first.id}/submit", json={"answers": [
            {"questionId": question.id, "userAnswer": "B" if index < 3 else "A"}
            for index, question in enumerate(first.questions)
        ]})
        # Stable tie-breaking and history names even after catalog entries close.
        for record in list(state.repository._quizzes.values()):
            state.repository._quizzes[record.id] = replace(record, created_at="2026-11-21T00:00:00Z")
        state.catalog._subjects[state.subject_id]["is_active"] = False
        state.catalog._topics[state.topic_id]["is_active"] = False
        page = await state.client.get("/api/quizzes?limit=2&offset=0")
        assert page.status_code == 200 and page.headers["cache-control"] == "no-store"
        body = page.json()
        assert body["hasMore"] is True
        assert [row["id"] for row in body["quizzes"]] == [owned[2].quiz.id, owned[1].quiz.id]
        assert all(row["topicName"] == "Phương trình" and row["subjectName"] == "Toán" for row in body["quizzes"])
        assert all(row["score"] is None for row in body["quizzes"])
        last = (await state.client.get("/api/quizzes?limit=2&offset=2")).json()
        assert last["hasMore"] is False and len(last["quizzes"]) == 1
        assert last["quizzes"][0]["id"] == first.id
        assert last["quizzes"][0]["score"] == 60
        for forbidden in ("questions", "correctAnswer", "correct_answer", "explanation", state.owner.email):
            assert forbidden not in page.text
        other = await state.client.get("/api/quizzes", headers=state.headers[state.other.id])
        assert [row["id"] for row in other.json()["quizzes"]] == [foreign.quiz.id]
        admin = await state.client.get(f"/api/quizzes?userId={state.owner.id}", headers=state.headers[state.admin.id])
        assert admin.json()["quizzes"] == []
        assert state.model.calls == []  # History/grade never ask the model to manufacture activity.


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1", "offset=100001"])
async def test_history_rejects_invalid_pagination(query):
    async with quiz_app() as state:
        assert (await state.client.get("/api/quizzes?" + query)).status_code == 422


async def test_history_authentication_empty_account_and_safe_storage_error():
    async with quiz_app() as state:
        empty = await state.client.get("/api/quizzes")
        assert empty.status_code == 200 and empty.json()["quizzes"] == [] and not empty.json()["hasMore"]
        assert (await state.client.get("/api/quizzes", headers={"Authorization": ""})).status_code == 401
        state.users._users[state.owner.id] = replace(state.owner, is_active=False)
        assert (await state.client.get("/api/quizzes")).status_code == 403
        state.users._users[state.owner.id] = state.owner

        async def unavailable(*args, **kwargs):
            raise SQLAlchemyError("private SQL detail")

        state.repository.list_quizzes = unavailable
        failed = await state.client.get("/api/quizzes")
        assert failed.status_code == 503 and failed.json()["error"]["code"] == "QUIZ_UNAVAILABLE"
        assert "private SQL detail" not in failed.text


async def test_long_explanation_history_keeps_question_and_hint_progression():
    async with application(limit=100) as state:
        path = f"/api/chat/sessions/{state.session_id}"
        question = "Giải phương trình bậc hai"
        assert (await state.client.post(path + "/messages", json={"content": question})).status_code == 201
        for level in (2, 3):
            hint = await state.client.post(path + "/hints")
            assert hint.status_code == 201 and hint.json()["assistantMessage"]["hintLevel"] == level
        for _ in range(26):
            explained = await state.client.post(path + "/explanations", json={"mode": "simplify"})
            assert explained.status_code == 201, explained.text
        assert question in json.dumps(state.model.calls[-1], ensure_ascii=False)
        assert len(state.model.calls[-1]) <= 12
        limited = await state.client.post(path + "/hints")
        assert limited.status_code == 409 and limited.json()["error"]["code"] == "HINT_LIMIT_REACHED"
        solution = await state.client.post(path + "/solution", json={"confirmed": True})
        assert solution.status_code == 201 and solution.json()["assistantMessage"]["isFullSolution"] is True
        assert (await state.client.post(path + "/messages", json={"content": "Giải phương trình mới"})).status_code == 201
        next_hint = await state.client.post(path + "/hints")
        assert next_hint.status_code == 201 and next_hint.json()["assistantMessage"]["hintLevel"] == 2
        foreign = await state.chat.context_messages(state.other.id, state.session_id, limit=24)
        assert foreign == []


async def test_sources_endpoint_matches_history_when_source_disabled_or_deleted():
    async with application() as state:
        path = f"/api/chat/sessions/{state.session_id}/messages"
        reply = await state.client.post(path, json={"content": "Giải phương trình"})
        message_id = reply.json()["assistantMessage"]["id"]
        endpoint = f"/api/chat/messages/{message_id}/sources"
        active = await state.client.get(endpoint)
        assert active.status_code == 200 and active.json()["hasSources"]
        assert all(ref["available"] for ref in active.json()["sourceRefs"])
        state.docs._documents[state.document.id] = replace(state.docs._documents[state.document.id], is_active=False)
        inactive = (await state.client.get(endpoint)).json()
        assert inactive["hasSources"] is False and inactive["sourceRefs"][0]["available"] is False
        assert inactive["notice"] and "?" not in inactive["notice"]
        history = (await state.client.get(path)).json()["messages"]
        assert history[-1]["sourcesStatus"] == "unavailable"
        assert (await state.client.get(endpoint, headers=state.auth(state.other))).status_code == 404
        del state.docs._documents[state.document.id]
        assert (await state.client.get(endpoint)).json()["hasSources"] is False
