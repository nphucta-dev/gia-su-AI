"""TK-036: API xem lời giải yêu cầu cờ xác nhận hợp lệ (confirmed=true)."""

import json

import pytest
from pydantic import ValidationError

from app.prompts.socratic import SocraticTopic
from app.schemas.chat import RequestFullSolutionRequest
from app.services.chat_context import FULL_SOLUTION_INSTRUCTION, build_full_solution_messages
from test_chat_api import ROOT, api, create_session, history

TOPIC = SocraticTopic("Toán", "Phương trình bậc hai", "THPT", "Đại số", "Biệt thức và nghiệm")


def test_request_full_solution_schema_enforces_strict_boolean_and_forbids_extra():
    assert RequestFullSolutionRequest(confirmed=True).confirmed is True
    assert RequestFullSolutionRequest(confirmed=False).confirmed is False
    for bad in ({"confirmed": "true"}, {"confirmed": 1}, {}, {"confirmed": True, "isFullSolution": True}):
        with pytest.raises(ValidationError):
            RequestFullSolutionRequest.model_validate(bad)


def test_build_full_solution_messages_sets_instruction_and_redacts_pii():
    messages = build_full_solution_messages(
        topic=TOPIC,
        history=[{"role": "user", "content": "Tôi là Nguyễn Văn An, email an@example.com. Giải x² − 5x + 6 = 0"}],
        known_name="Nguyễn Văn An",
        known_email="an@example.com",
    )
    assert messages[0]["role"] == "system"
    assert FULL_SOLUTION_INSTRUCTION in messages[0]["content"]
    request = json.loads(messages[-1]["content"])
    assert request == {"type": "learning_request", "action": "provide_full_solution", "confirmed": True}
    serialized = json.dumps(messages, ensure_ascii=False)
    assert "Nguyễn Văn An" not in serialized and "an@example.com" not in serialized


@pytest.mark.anyio
async def test_solution_api_requires_confirmed_true_and_never_calls_llm_otherwise():
    async with api() as state:
        session = await create_session(state)
        await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Giải x² − 5x + 6 = 0"})
        calls_before = len(state.model.calls)

        unconfirmed = await state.client.post(f"{ROOT}/{session['id']}/solution", json={"confirmed": False})
        assert unconfirmed.status_code == 422
        assert unconfirmed.json()["error"]["code"] == "CONFIRMATION_REQUIRED"
        assert len(state.model.calls) == calls_before

        for invalid_body in ({}, {"confirmed": "true"}, {"confirmed": 1}, {"confirmed": True, "extra": 1}):
            resp = await state.client.post(f"{ROOT}/{session['id']}/solution", json=invalid_body)
            assert resp.status_code == 422
            assert len(state.model.calls) == calls_before


@pytest.mark.anyio
async def test_solution_api_returns_full_solution_when_confirmed():
    async with api() as state:
        session = await create_session(state)
        no_question = await state.client.post(f"{ROOT}/{session['id']}/solution", json={"confirmed": True})
        assert no_question.status_code == 409
        assert no_question.json()["error"]["code"] == "CHAT_QUESTION_REQUIRED"

        await state.client.post(f"{ROOT}/{session['id']}/messages", json={"content": "Giải x² − 5x + 6 = 0"})
        response = await state.client.post(f"{ROOT}/{session['id']}/solution", json={"confirmed": True})
        assert response.status_code == 201, response.text
        body = response.json()
        assert body["userMessage"] is None
        assert body["assistantMessage"]["role"] == "assistant"
        assert body["assistantMessage"]["isFullSolution"] is True
        assert body["assistantMessage"]["hintLevel"] is None

        stored = await history(state, session["id"])
        assert stored[-1]["isFullSolution"] is True
        assert stored[-1]["hintLevel"] is None

        foreign = await state.client.post(
            f"{ROOT}/{session['id']}/solution", json={"confirmed": True}, headers=state.other_headers,
        )
        assert foreign.status_code == 404
