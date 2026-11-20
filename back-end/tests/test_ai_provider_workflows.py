"""Each supported wire protocol drives the same chat and quiz API workflows."""

import json

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.document_repository import InMemoryDocumentRepository, SubjectRecord, TopicRecord
from app.repositories.user_repository import InMemoryUserRepository
from app.services.llm_client import ChatCompletionsClient
from test_quiz_validation import valid_payload


def provider_response(protocol, content):
    if protocol == "responses":
        return {"status": "completed", "output": [{"type": "message", "content": [{"type": "output_text", "text": content}]}]}
    if protocol == "gemini":
        return {"candidates": [{"content": {"parts": [{"text": content}]}}]}
    if protocol == "anthropic":
        return {"content": [{"type": "text", "text": content}]}
    if protocol == "ollama":
        return {"message": {"content": content}}
    return {"choices": [{"message": {"content": content}}]}


@pytest.mark.anyio
@pytest.mark.parametrize("protocol", ["openai", "responses", "gemini", "anthropic", "ollama"])
async def test_protocol_supports_chat_sources_quiz_grading_and_shared_quota(protocol):
    requests = []
    def handle(request):
        requests.append(request)
        wire = request.content.decode()
        for secret in ("learner@example.com", "Nguoi Hoc", "private-hash"):
            assert secret not in wire
        content = "Em thử xác định hệ số trước nhé. [1]" if len(requests) == 1 else json.dumps(valid_payload())
        return httpx.Response(200, json=provider_response(protocol, content))

    settings = Settings(
        jwt_secret="provider-workflow-" + "x" * 40, llm_provider=protocol,
        llm_api_key="private-provider-key", llm_api_url="https://provider.invalid", llm_model="chosen-text-model",
    )
    model = ChatCompletionsClient(settings, transport=httpx.MockTransport(handle))
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    topic_id = catalog.add_topic(subject_id, "Đại số", "Phương trình")
    documents = InMemoryDocumentRepository(
        subjects=[SubjectRecord(subject_id, "Toán", "THPT")],
        topics=[TopicRecord(topic_id, subject_id, "Phương trình")],
    )
    document = await documents.create(topic_id=topic_id, title="Nguồn đại số", file_path="lesson.txt")
    await documents.finish_processing(document.id, chunks=["Phương trình có các hệ số a, b, c."])
    await documents.set_document_active(document.id, True)
    users = InMemoryUserRepository()
    user = await users.create(name="Nguoi Hoc", email="learner@example.com", password_hash="private-hash", role="LEARNER")
    app = create_app(user_repository=users, catalog_repository=catalog, document_repository=documents, llm_client=model, settings=settings)
    token = app.state.token_service.create_access_token(user.id).access_token
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer " + token}) as client:
        session = (await client.post("/api/chat/sessions", json={"topicId": topic_id})).json()["session"]
        reply = await client.post(f"/api/chat/sessions/{session['id']}/messages", json={"content": "Giải phương trình thế nào?"})
        assert reply.status_code == 201, reply.text
        assert reply.json()["assistantMessage"]["sourceRefs"][0]["documentId"] == document.id
        generated = await client.post("/api/quizzes", json={"topicId": topic_id, "difficulty": "easy"})
        assert generated.status_code == 201, generated.text
        assert "correctAnswer" not in generated.text and "explanation" not in generated.text
        quiz = generated.json()["quiz"]
        submitted = await client.post(f"/api/quizzes/{quiz['id']}/submit", json={"answers": [
            {"questionId": question["id"], "userAnswer": "B"} for question in quiz["questions"]
        ]})
        assert submitted.status_code == 200 and submitted.json()["submission"]["score"] == 100
        result = await client.get(f"/api/quizzes/{quiz['id']}/result")
        assert result.status_code == 200 and result.json()["result"]["correctCount"] == 5
        quota = (await client.get("/api/ai/quota")).json()
        assert quota["used"] == 2 and quota["remaining"] == 28
        assert len(requests) == 2
