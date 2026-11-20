"""TK-056: bad model output is private, atomic and retryable through the API."""

from copy import deepcopy
import json

import httpx
import pytest

from app.config import Settings
from app.services.llm_client import ChatCompletionsClient
from test_ai_quiz_api import FakeQuizModel, quiz_app
from test_quiz_validation import valid_payload

pytestmark = pytest.mark.anyio

INVALID_ERROR = {"error": {
    "code": "QUIZ_INVALID_RESPONSE",
    "message": "Dữ liệu bài luyện tập chưa hợp lệ. Chưa có bài nào được lưu. Vui lòng tạo lại bài.",
}}


def invalid_outputs():
    for name, value in (
        ("truncated", '{"questions":'), ("prose", 'Here is your quiz: {}'),
        ("null", "null"), ("array", "[]"), ("empty", " "),
        ("too-large", "x" * 128_001), ("non-text", False), ("missing-content", None),
        ("too-deep", "[" * 2000 + "0" + "]" * 2000),
    ):
        yield pytest.param(value, id=name)
    for count in (0, 4, 6):
        payload = valid_payload()
        payload["questions"] = (payload["questions"] * 2)[:count]
        yield pytest.param(json.dumps(payload), id=f"question-count-{count}")
    for name in ("missing-option", "invalid-answer", "blank-explanation", "unicode",
                 "duplicate-question", "duplicate-option", "extra-field"):
        payload = valid_payload()
        last = payload["questions"][-1]
        if name == "missing-option":
            del last["options"]["D"]
        elif name == "invalid-answer":
            last["correct_answer"] = "E"
        elif name == "blank-explanation":
            last["explanation"] = " \n "
        elif name == "unicode":
            last["question_text"] = "\ud800"
        elif name == "duplicate-question":
            last["question_text"] = payload["questions"][0]["question_text"].upper() + "  "
        elif name == "duplicate-option":
            last["options"]["D"] = "  " + last["options"]["A"] + "  "
        else:
            payload["user_id"] = 99
        yield pytest.param(json.dumps(payload), id=name)
    raw = json.dumps(valid_payload())
    yield pytest.param(raw.replace('"correct_answer": "B"', '"correct_answer": "A", "correct_answer": "B"', 1), id="duplicate-json-key")
    for field in ("question_text", "explanation", "option"):
        for control in ("\x7f", "\x85"):
            payload = valid_payload()
            question = payload["questions"][-1]
            if field == "option":
                question["options"]["D"] = "Option" + control + "text"
            else:
                question[field] = "Generated" + control + "text"
            yield pytest.param(json.dumps(payload), id=f"control-{field}-{ord(control)}")
    payload = valid_payload()
    payload["questions"][-1]["explanation"] = "SENSITIVE_MODEL_TEXT an@example.com private-provider-key"
    del payload["questions"][-1]["options"]["D"]
    yield pytest.param(json.dumps(payload), id="private-invalid-output")


@pytest.mark.parametrize("invalid_content", list(invalid_outputs()))
async def test_invalid_output_keeps_existing_quizzes_and_quota_then_allows_retry(invalid_content):
    async with quiz_app() as state:
        # Exercise the shared quota and real HTTP route, rather than a service-only stub.
        state.app.state.quiz_service._quota = state.app.state.ai_quota_service
        payload = {"topicId": state.topic_id, "difficulty": "medium"}
        first = await state.client.post("/api/quizzes", json=payload)
        assert first.status_code == 201
        saved = deepcopy(state.repository._quizzes)
        quota = (await state.client.get("/api/ai/quota")).json()

        state.model.content = invalid_content
        failed = await state.client.post("/api/quizzes", json=payload)
        assert failed.status_code == 502, failed.text
        assert failed.json() == INVALID_ERROR
        assert failed.headers["cache-control"] == "no-store"
        assert failed.headers["content-type"].startswith("application/json")
        assert state.repository._quizzes == saved
        assert state.repository._answers == {}
        assert state.repository.progress_repository._records == {}
        assert (await state.client.get("/api/ai/quota")).json() == quota
        assert len(state.model.calls) == 2  # No hidden model retries or repair attempts.

        state.model.content = json.dumps(valid_payload())
        retried = await state.client.post("/api/quizzes", json=payload)
        assert retried.status_code == 201, retried.text
        assert len(state.model.calls) == 3
        assert len(state.repository._quizzes) == 2
        assert retried.json()["quiz"]["id"] != first.json()["quiz"]["id"]
        assert len(retried.json()["quiz"]["questions"]) == 5
        assert "correctAnswer" not in retried.text and "explanation" not in retried.text
        assert (await state.client.get("/api/ai/quota")).json()["remaining"] == quota["remaining"] - 1


async def test_http_provider_with_invalid_quiz_json_can_recover_on_next_request():
    calls = []

    async def provider(request):
        calls.append(json.loads(request.content))
        content = '{"questions":' if len(calls) == 1 else json.dumps(valid_payload())
        return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})

    settings = Settings(
        jwt_secret="quiz-error-adapter-test-" + "x" * 40,
        llm_api_url="https://model.test/v1/chat/completions",
        llm_api_key="fake-test-key", llm_model="fake-test-model",
    )
    model = ChatCompletionsClient(settings, transport=httpx.MockTransport(provider))
    async with quiz_app(model=model) as state:
        state.app.state.quiz_service._quota = state.app.state.ai_quota_service
        payload = {"topicId": state.topic_id, "difficulty": "easy"}
        failed = await state.client.post("/api/quizzes", json=payload)
        assert failed.status_code == 502 and failed.json() == INVALID_ERROR
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 0
        retried = await state.client.post("/api/quizzes", json=payload)
        assert retried.status_code == 201, retried.text
        assert len(calls) == 2 and calls[0]["model"] == "fake-test-model"
        assert len(state.repository._quizzes) == 1
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 1


async def test_generation_errors_are_documented_as_standard_error_responses():
    async with quiz_app(model=FakeQuizModel()) as state:
        responses = state.app.openapi()["paths"]["/api/quizzes"]["post"]["responses"]
        for status in (429, 502, 503, 504):
            schema = responses[str(status)]["content"]["application/json"]["schema"]
            assert schema["$ref"].endswith("/ErrorResponse")


@pytest.mark.parametrize("raw", [b'{"choices":', b'[' * 2000 + b'0' + b']' * 2000], ids=["broken-json", "deep-json"])
async def test_malformed_provider_envelope_returns_safe_error_and_can_retry(raw):
    calls = 0

    async def provider(request):
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(200, content=raw, headers={"Content-Type": "application/json"})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps(valid_payload())}}]})

    settings = Settings(
        jwt_secret="quiz-envelope-test-" + "x" * 40,
        llm_api_url="https://model.test/v1/chat/completions",
        llm_api_key="fake-test-key", llm_model="fake-test-model",
    )
    model = ChatCompletionsClient(settings, transport=httpx.MockTransport(provider))
    async with quiz_app(model=model) as state:
        state.app.state.quiz_service._quota = state.app.state.ai_quota_service
        payload = {"topicId": state.topic_id, "difficulty": "easy"}
        failed = await state.client.post("/api/quizzes", json=payload)
        assert failed.status_code == 502
        assert failed.json() == {"error": {
            "code": "LLM_INVALID_RESPONSE", "message": "Model trả về nội dung chưa hợp lệ. Vui lòng thử lại.",
        }}
        assert state.repository._quizzes == {}
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 0
        retried = await state.client.post("/api/quizzes", json=payload)
        assert retried.status_code == 201 and calls == 2
        assert len(state.repository._quizzes) == 1
        assert (await state.client.get("/api/ai/quota")).json()["used"] == 1
