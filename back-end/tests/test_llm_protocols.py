"""Model/provider changes stay behind one text-client interface, without live calls."""

import json

import httpx
import pytest

from app.config import Settings, load_settings
from app.services.llm_client import ChatCompletionsClient
from app.utils.errors import AppError

MESSAGES = [
    {"role": "system", "content": "Hướng dẫn bằng câu hỏi."},
    {"role": "user", "content": "Em bắt đầu từ đâu?"},
    {"role": "assistant", "content": "Em biết dữ kiện nào?"},
    {"role": "user", "content": "Em đã tìm được hệ số."},
]

CASES = [
    ("auto", "https://provider.invalid/v1", "/v1/chat/completions", "Authorization", {"choices": [{"message": {"content": "Em thử bước tiếp theo nhé?"}}], "usage": {"completion_tokens": 7}}),
    ("auto", "https://provider.invalid/v1/responses", "/v1/responses", "Authorization", {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Em thử bước tiếp theo nhé?"}]}], "usage": {"output_tokens": 7}}),
    ("gemini", "https://provider.invalid/v1beta", "/v1beta/models/model-b:generateContent", "x-goog-api-key", {"candidates": [{"content": {"parts": [{"thought": True, "text": "private reasoning"}, {"text": "Em thử bước tiếp theo nhé?"}]}}], "usageMetadata": {"candidatesTokenCount": 7}}),
    ("anthropic", "https://provider.invalid/v1", "/v1/messages", "x-api-key", {"content": [{"type": "thinking", "thinking": "private reasoning"}, {"type": "text", "text": "Em thử bước tiếp theo nhé?"}], "usage": {"output_tokens": 7}}),
    ("ollama", "http://localhost:11434", "/api/chat", "Authorization", {"message": {"content": "Em thử bước tiếp theo nhé?", "thinking": "private reasoning"}, "eval_count": 7}),
]


@pytest.mark.anyio
@pytest.mark.parametrize("suffix", ["", "/"])
async def test_google_openai_base_url_is_not_mistaken_for_native_gemini(suffix):
    def handle(request):
        assert request.url.path == "/v1beta/openai/chat/completions"
        assert json.loads(request.content)["messages"] == MESSAGES
        return httpx.Response(200, json={"choices": [{"message": {"content": "Gợi ý"}}]})
    client = ChatCompletionsClient(Settings(
        llm_api_key="private-key", llm_model="model-b",
        llm_api_url="https://generativelanguage.googleapis.com/v1beta/openai" + suffix,
    ), transport=httpx.MockTransport(handle))
    assert (await client.generate(MESSAGES)).content == "Gợi ý"


@pytest.mark.anyio
@pytest.mark.parametrize("provider,url,path,header,payload", CASES)
async def test_protocols_translate_requests_and_normalize_replies(provider, url, path, header, payload):
    captured = []
    def handle(request):
        captured.append(request)
        assert request.url.path == path
        assert "private-key" not in str(request.url)
        assert request.headers[header] in {"private-key", "Bearer private-key"}
        body = json.loads(request.content)
        if "generateContent" in path:
            assert body["systemInstruction"]["parts"][0]["text"] == MESSAGES[0]["content"]
            assert [item["role"] for item in body["contents"]] == ["user", "model", "user"]
        elif provider == "anthropic":
            assert body["system"] == MESSAGES[0]["content"] and body["messages"] == MESSAGES[1:]
            assert body["max_tokens"] == 4096
            assert request.headers["anthropic-version"] == "2023-06-01"
        elif path.endswith("/responses"):
            assert body["instructions"] == MESSAGES[0]["content"]
            assert body["input"] == MESSAGES[1:] and body["store"] is False
        else:
            assert body["messages"] == MESSAGES
        if "generateContent" not in path:
            assert body["model"] == "model-b"
        return httpx.Response(200, json=payload)
    settings = Settings(llm_api_url=url, llm_api_key="private-key", llm_model="model-b", llm_provider=provider)
    result = await ChatCompletionsClient(settings, transport=httpx.MockTransport(handle)).generate(MESSAGES)
    assert result.content == "Em thử bước tiếp theo nhé?" and result.token_count == 7
    assert len(captured) == 1


@pytest.mark.anyio
async def test_auto_native_gemini_switches_model_without_editing_full_endpoint():
    seen = []
    def handle(request):
        seen.append(request.url.path)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": "Câu hỏi tiếp theo?"}]}}]})
    settings = Settings(llm_api_url="https://generativelanguage.googleapis.com/v1beta/models/old-model:generateContent", llm_api_key="key", llm_model="new-model")
    await ChatCompletionsClient(settings, transport=httpx.MockTransport(handle)).generate(MESSAGES)
    assert seen == ["/v1beta/models/new-model:generateContent"]


@pytest.mark.anyio
@pytest.mark.parametrize("provider,url", [("auto", "http://localhost:11434/v1"), ("ollama", "http://local-server:11434/api/chat")])
async def test_local_models_work_without_an_api_key(provider, url):
    def handle(request):
        assert "authorization" not in request.headers
        return httpx.Response(200, json={"message": {"content": "Local reply"}} if provider == "ollama" else {"choices": [{"message": {"content": "Local reply"}}]})
    settings = Settings(llm_api_url=url, llm_model="local-model", llm_provider=provider)
    assert (await ChatCompletionsClient(settings, transport=httpx.MockTransport(handle)).generate(MESSAGES)).content == "Local reply"


@pytest.mark.anyio
@pytest.mark.parametrize("provider,payload", [("gemini", {"candidates": []}), ("anthropic", {"content": [{"type": "thinking", "thinking": "private"}]}), ("responses", {"status": "incomplete", "output": []}), ("ollama", {"message": {"content": ""}})])
async def test_invalid_native_response_has_same_safe_error(provider, payload):
    settings = Settings(llm_api_url="https://provider.invalid/endpoint", llm_api_key="secret", llm_model="model", llm_provider=provider)
    with pytest.raises(AppError) as caught:
        await ChatCompletionsClient(settings, transport=httpx.MockTransport(lambda request: httpx.Response(200, json=payload))).generate(MESSAGES)
    assert caught.value.code == "LLM_INVALID_RESPONSE" and caught.value.status_code == 502
    assert "private" not in caught.value.message and "secret" not in caught.value.message


def test_unknown_provider_is_not_silently_sent_using_another_protocol():
    settings = Settings(llm_api_url="https://provider.invalid/chat", llm_api_key="key", llm_model="model", llm_provider="unknown")
    with pytest.raises(AppError) as caught:
        ChatCompletionsClient(settings)._configuration()
    assert caught.value.code == "LLM_NOT_CONFIGURED"


def test_optional_protocol_settings_load_without_selecting_a_specific_model(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ANTHROPIC")
    monkeypatch.setenv("LLM_MAX_TOKENS", "2048")
    monkeypatch.setenv("LLM_API_VERSION", "2026-10-21")
    settings = load_settings()
    assert settings.llm_provider == "anthropic" and settings.llm_max_tokens == 2048
    assert settings.llm_api_version == "2026-10-21"
