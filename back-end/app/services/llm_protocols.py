"""Translate the application's text messages to supported HTTP API protocols."""

import ipaddress
from urllib.parse import quote

import httpx

PROVIDERS = {"auto", "openai", "openai_compatible", "responses", "gemini", "anthropic", "ollama"}


def protocol_for(endpoint: str, provider: str = "auto") -> str:
    if not isinstance(provider, str) or provider not in PROVIDERS:
        raise ValueError("Unknown API protocol")
    if provider != "auto":
        return "openai" if provider == "openai_compatible" else provider
    url = httpx.URL(endpoint)
    path = url.path.rstrip("/")
    if path.endswith("/responses"):
        return "responses"
    if path.endswith("/api/chat"):
        return "ollama"
    if path.endswith("/messages") or url.host == "api.anthropic.com":
        return "anthropic"
    google_openai = path.endswith("/openai") or "/openai/" in path
    if ":generateContent" in path or (url.host == "generativelanguage.googleapis.com" and not google_openai):
        return "gemini"
    return "openai"


def key_is_optional(endpoint: str, protocol: str) -> bool:
    if protocol == "ollama":
        return True
    host = httpx.URL(endpoint).host
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def make_request(endpoint: str, key: str, model: str, messages: list[dict[str, str]], *,
                 provider: str = "auto", max_tokens: int = 4096, api_version: str = "2023-06-01") -> tuple[str, str, dict, dict]:
    protocol = protocol_for(endpoint, provider)
    url = httpx.URL(endpoint)
    path = url.path.rstrip("/")
    headers = {"Accept": "application/json", "Accept-Encoding": "identity"}
    system = "\n\n".join(item["content"] for item in messages if item["role"] == "system")
    dialogue = [item for item in messages if item["role"] in {"user", "assistant"}]
    if protocol == "openai":
        if not path:
            path = "/v1/chat/completions"
        elif path.endswith(("/v1", "/openai")):
            path += "/chat/completions"
        body = {"model": model, "messages": messages}
        if key:
            headers["Authorization"] = "Bearer " + key
    elif protocol == "responses":
        if not path or path.endswith("/v1"):
            path = (path or "/v1") + "/responses"
        body = {"model": model, "input": dialogue, "store": False}
        if system:
            body["instructions"] = system
        if key:
            headers["Authorization"] = "Bearer " + key
    elif protocol == "gemini":
        if "{model}" in path:
            path = path.replace("{model}", quote(model.removeprefix("models/"), safe=""))
        elif ":generateContent" in path and "/models/" in path:
            path = path.split("/models/", 1)[0] + "/models/" + quote(model.removeprefix("models/"), safe="") + ":generateContent"
        elif ":generateContent" not in path:
            path = (path or "/v1beta") + "/models/" + quote(model.removeprefix("models/"), safe="") + ":generateContent"
        body = {"contents": [
            {"role": "model" if item["role"] == "assistant" else "user", "parts": [{"text": item["content"]}]}
            for item in dialogue
        ]}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        headers["x-goog-api-key"] = key
    elif protocol == "anthropic":
        if not path or path.endswith("/v1"):
            path = (path or "/v1") + "/messages"
        body = {"model": model, "messages": dialogue, "max_tokens": max_tokens}
        if system:
            body["system"] = system
        headers.update({"x-api-key": key, "anthropic-version": api_version})
    else:
        if not path:
            path = "/api/chat"
        elif path == "/api":
            path += "/chat"
        body = {"model": model, "messages": messages, "stream": False}
        if key:
            headers["Authorization"] = "Bearer " + key
    return protocol, str(url.copy_with(path=path)), headers, body


def extract_text(body: dict, protocol: str) -> tuple[str, object]:
    if not isinstance(body, dict):
        raise ValueError("Invalid model response")
    if protocol == "openai":
        content = body["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "\n".join(item["text"] for item in content if isinstance(item, dict) and item.get("type") == "text")
        usage = body.get("usage") or {}
        count = usage.get("completion_tokens") if isinstance(usage, dict) else None
    elif protocol == "responses":
        if body.get("status") in {"failed", "incomplete", "cancelled"} or body.get("error"):
            raise ValueError("Incomplete model response")
        texts = [part["text"] for item in body.get("output", [])
                 if isinstance(item, dict) and item.get("type") == "message"
                 for part in item.get("content", [])
                 if isinstance(part, dict) and part.get("type") == "output_text"]
        content = "\n".join(texts)
        usage = body.get("usage") or {}
        count = usage.get("output_tokens") if isinstance(usage, dict) else None
    elif protocol == "gemini":
        candidate = body["candidates"][0]
        content = "\n".join(part["text"] for part in candidate["content"]["parts"]
                            if isinstance(part, dict) and isinstance(part.get("text"), str) and not part.get("thought"))
        usage = body.get("usageMetadata") or {}
        count = usage.get("candidatesTokenCount") if isinstance(usage, dict) else None
    elif protocol == "anthropic":
        content = "\n".join(part["text"] for part in body["content"]
                            if isinstance(part, dict) and part.get("type") == "text")
        usage = body.get("usage") or {}
        count = usage.get("output_tokens") if isinstance(usage, dict) else None
    else:
        content = body["message"]["content"]
        count = body.get("eval_count")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Missing text response")
    return content, count
