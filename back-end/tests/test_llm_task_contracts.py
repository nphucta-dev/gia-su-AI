"""TK-020/TK-051 reject incomplete or empty AI output before saving a success."""

import json

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.llm_client import ChatCompletionsClient
from app.utils.errors import AppError
from app.validators.quiz import validate_generated_quiz
from test_ai_chat_complete import application
from test_ai_provider_workflows import provider_response
from test_ai_quiz_api import FakeQuizModel, quiz_app
from test_quiz_validation import valid_payload


def with_completion(protocol, content, completion):
    body = provider_response(protocol, content)
    target = body
    if protocol == "openai":
        target = body["choices"][0]
    elif protocol == "gemini":
        target = body["candidates"][0]
    target.update(completion)
    return body


INCOMPLETE = [
    ("openai", {"finish_reason": "length"}),
    ("openai", {"finish_reason": "content_filter"}),
    ("openai", {"finish_reason": "tool_calls"}),
    ("openai", {"finish_reason": None}),
    ("responses", {"status": "incomplete"}),
    ("responses", {"status": "in_progress"}),
    ("responses", {"status": "queued"}),
    ("gemini", {"finishReason": "MAX_TOKENS"}),
    ("gemini", {"finishReason": "SAFETY"}),
    ("anthropic", {"stop_reason": "max_tokens"}),
    ("anthropic", {"stop_reason": "tool_use"}),
    ("anthropic", {"stop_reason": "pause_turn"}),
    ("anthropic", {"stop_reason": "refusal"}),
    ("ollama", {"done": False}),
    ("ollama", {"done": True, "done_reason": "length"}),
]
COMPLETE = [
    ("openai", {"finish_reason": "stop"}),
    ("responses", {"status": "completed"}),
    ("gemini", {"finishReason": "STOP"}),
    ("anthropic", {"stop_reason": "end_turn"}),
    ("anthropic", {"stop_reason": "stop_sequence"}),
    ("ollama", {"done": True, "done_reason": "stop"}),
]


@pytest.mark.parametrize("protocol,completion", INCOMPLETE)
def test_incomplete_provider_output_is_rejected_even_when_quiz_json_is_valid(protocol, completion):
    body = with_completion(protocol, json.dumps(valid_payload()), completion)
    with pytest.raises(AppError) as caught:
        ChatCompletionsClient._parse_reply(json.dumps(body).encode(), protocol)
    assert (caught.value.status_code, caught.value.code) == (502, "LLM_INVALID_RESPONSE")


@pytest.mark.parametrize("protocol,completion", COMPLETE)
def test_completed_provider_output_is_accepted(protocol, completion):
    text = "Em thử xác định hệ số của phương trình trước nhé."
    body = with_completion(protocol, text, completion)
    assert ChatCompletionsClient._parse_reply(json.dumps(body).encode(), protocol).content == text


@pytest.mark.parametrize("protocol", ["openai", "responses", "gemini", "anthropic", "ollama"])
@pytest.mark.parametrize("text", ["\u200b\ufeff", "\u034f\ufe0f", "\u00a0\u200d\n\t"])
def test_provider_text_requires_visible_content(protocol, text):
    body = provider_response(protocol, text)
    with pytest.raises(AppError) as caught:
        ChatCompletionsClient._parse_reply(json.dumps(body).encode(), protocol)
    assert caught.value.code == "LLM_INVALID_RESPONSE"


@pytest.mark.parametrize("field", ["question_text", "explanation", "option"])
@pytest.mark.parametrize("text", ["\u200b\ufeff", "\u034f\ufe0f", "\u00a0\u200d\n\t"])
def test_quiz_fields_require_visible_content(field, text):
    payload = valid_payload()
    question = payload["questions"][0]
    if field == "option":
        question["options"]["A"] = text
    else:
        question[field] = text
    with pytest.raises(AppError) as caught:
        validate_generated_quiz(payload)
    assert caught.value.code == "QUIZ_INVALID_RESPONSE"


@pytest.mark.parametrize("duplicate", ["question", "option"])
def test_shared_quiz_validator_rejects_normalized_duplicates(duplicate):
    payload = valid_payload()
    if duplicate == "question":
        payload["questions"][4]["question_text"] = "  " + payload["questions"][0]["question_text"].upper() + "\n"
    else:
        payload["questions"][0]["options"]["D"] = "\uff11"  # Full-width 1 equals option A.
    with pytest.raises(AppError) as caught:
        validate_generated_quiz(payload)
    assert caught.value.code == "QUIZ_INVALID_RESPONSE"


@pytest.mark.anyio
@pytest.mark.parametrize("protocol,completion", [
    ("openai", {"finish_reason": "length"}),
    ("responses", {"status": "in_progress"}),
    ("gemini", {"finishReason": "MAX_TOKENS"}),
    ("anthropic", {"stop_reason": "max_tokens"}),
    ("ollama", {"done": False}),
])
async def test_incomplete_chat_and_quiz_do_not_consume_quota_and_can_be_retried(protocol, completion):
    provider = {"complete": False, "quiz": False}
    requests = []

    def handle(request):
        requests.append(request)
        content = json.dumps(valid_payload()) if provider["quiz"] else "Em thử tìm hệ số trước nhé."
        return httpx.Response(200, json=with_completion(protocol, content, {} if provider["complete"] else completion))

    settings = Settings(
        jwt_secret="llm-task-contracts-" + "x" * 40,
        llm_api_key="private-provider-key", llm_api_url="https://provider.invalid",
        llm_model="chosen-text-model", llm_provider=protocol,
    )
    users = InMemoryUserRepository()
    user = await users.create(name="Người học", email="learner@example.com", password_hash="private-hash", role="LEARNER")
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phương trình")
    model = ChatCompletionsClient(settings, transport=httpx.MockTransport(handle))
    app = create_app(user_repository=users, catalog_repository=catalog, settings=settings, llm_client=model)
    token = app.state.token_service.create_access_token(user.id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        session = (await client.post("/api/chat/sessions", json={"topicId": topic_id})).json()["session"]
        path = f"/api/chat/sessions/{session['id']}"
        failed_chat = await client.post(path + "/messages", json={"content": "Giải phương trình thế nào?"})
        assert failed_chat.status_code == 502, failed_chat.text
        assert failed_chat.json()["error"]["code"] == "LLM_INVALID_RESPONSE"
        assert failed_chat.json()["error"]["fields"]["messageSaved"] == "true"
        history = (await client.get(path + "/messages")).json()["messages"]
        assert [message["role"] for message in history] == ["user"]

        provider["quiz"] = True
        failed_quiz = await client.post("/api/quizzes", json={"topicId": topic_id, "difficulty": "easy"})
        assert failed_quiz.status_code == 502, failed_quiz.text
        assert (await client.get("/api/quizzes")).json()["quizzes"] == []
        assert (await client.get("/api/ai/quota")).json()["used"] == 0

        provider.update(complete=True, quiz=False)
        retried = await client.post(path + "/retry")
        assert retried.status_code == 201, retried.text
        history = (await client.get(path + "/messages")).json()["messages"]
        assert [message["role"] for message in history] == ["user", "assistant"]
        provider["quiz"] = True
        generated = await client.post("/api/quizzes", json={"topicId": topic_id, "difficulty": "easy"})
        assert generated.status_code == 201, generated.text
        assert len(generated.json()["quiz"]["questions"]) == 5
        assert "correctAnswer" not in generated.text and "explanation" not in generated.text
        assert (await client.get("/api/ai/quota")).json()["used"] == 2
        assert len(requests) == 4  # Retrying remains an explicit user action.


@pytest.mark.parametrize("kind", ["refusal", "tool_call", "incomplete_message"])
def test_nonfinal_text_in_successful_envelopes_is_rejected(kind):
    if kind == "incomplete_message":
        protocol = "responses"
        body = with_completion(protocol, "Partial answer", {"status": "completed"})
        body["output"][0]["status"] = "in_progress"
    else:
        protocol = "openai"
        body = with_completion(protocol, "Partial answer", {"finish_reason": "stop"})
        message = body["choices"][0]["message"]
        message.update({"refusal": "Declined"} if kind == "refusal" else {"tool_calls": [{"type": "function"}]})
    with pytest.raises(AppError) as caught:
        ChatCompletionsClient._parse_reply(json.dumps(body).encode(), protocol)
    assert caught.value.code == "LLM_INVALID_RESPONSE"


@pytest.mark.anyio
@pytest.mark.parametrize("text", ["\u200b\ufeff", "\u034f\ufe0f", "\u00a0\u200d\n\t"])
async def test_chat_service_also_rejects_empty_output_from_an_injected_adapter(text):
    async with application() as state:
        state.model.content = text
        path = f"/api/chat/sessions/{state.session_id}"
        response = await state.client.post(path + "/messages", json={"content": "Giải phương trình thế nào?"})
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "LLM_INVALID_RESPONSE"
        history = (await state.client.get(path + "/messages")).json()["messages"]
        assert [message["role"] for message in history] == ["user"]
        assert (await client_quota(state.client))["used"] == 0


async def client_quota(client):
    return (await client.get("/api/ai/quota")).json()


@pytest.mark.anyio
@pytest.mark.parametrize("duplicate", ["question", "option"])
async def test_quiz_is_revalidated_after_private_values_are_redacted(duplicate):
    payload = valid_payload()
    if duplicate == "question":
        payload["questions"][0]["question_text"] = "Giải phương trình: an@example.com"
        payload["questions"][4]["question_text"] = "Giải phương trình: other@example.net"
    else:
        payload["questions"][0]["options"].update(A="an@example.com", D="other@example.net")
    validate_generated_quiz(payload)  # Distinct before both emails become [EMAIL].
    async with quiz_app(model=FakeQuizModel(json.dumps(payload))) as state:
        state.app.state.quiz_service._quota = state.app.state.ai_quota_service
        response = await state.client.post("/api/quizzes", json={"topicId": state.topic_id, "difficulty": "easy"})
        assert response.status_code == 502, response.text
        assert response.json()["error"]["code"] == "QUIZ_INVALID_RESPONSE"
        assert state.repository._quizzes == {}
        assert (await client_quota(state.client))["used"] == 0
