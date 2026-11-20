"""TK-047: Lưu danh sách nguồn tham khảo của phản hồi trong source_refs."""

from dataclasses import replace

import httpx
import pytest

from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.document_repository import (
    DocumentChunkRecord,
    InMemoryDocumentRepository,
    SubjectRecord,
    TopicRecord,
)
from app.repositories.user_repository import InMemoryUserRepository
from app.services.chat_service import build_source_refs
from app.services.llm_client import LLMReply


class FakeLLMClient:
    async def generate(self, messages):
        return LLMReply(content="Gợi ý: Hãy thử phân tích nghiệm theo công thức delta.", token_count=42)


def test_build_source_refs_deduplicates_and_formats_fields():
    chunks = [
        DocumentChunkRecord(
            id=10, document_id=1, document_title="SGK Toán 10", topic_id=1,
            chunk_index=0, content="Nội dung 1", source_url="https://example.edu/toan10",
        ),
        DocumentChunkRecord(
            id=10, document_id=1, document_title="SGK Toán 10", topic_id=1,
            chunk_index=0, content="Nội dung 1 trùng", source_url="https://example.edu/toan10",
        ),
        DocumentChunkRecord(
            id=11, document_id=1, document_title="SGK Toán 10", topic_id=1,
            chunk_index=1, content="Nội dung 2", source_url=None,
        ),
    ]
    refs = build_source_refs(chunks)
    assert refs == [
        {
            "document_id": 1,
            "chunk_id": 10,
            "title": "SGK Toán 10",
            "chunk_index": 0,
            "source_url": "https://example.edu/toan10",
        },
        {
            "document_id": 1,
            "chunk_id": 11,
            "title": "SGK Toán 10",
            "chunk_index": 1,
        },
    ]


@pytest.mark.anyio
async def test_chat_persists_source_refs_for_assistant_and_empty_for_user():
    users = InMemoryUserRepository()
    catalog = InMemoryCatalogRepository()
    subject_id = catalog.add_subject("Toán", "THPT")
    catalog.add_topic(subject_id, "Đại số", "Phương trình bậc hai")
    chat_repo = InMemoryChatRepository(catalog)
    doc_repo = InMemoryDocumentRepository(
        subjects=[SubjectRecord(id=1, name="Toán", grade_level="THPT")],
        topics=[TopicRecord(id=1, subject_id=1, name="Phương trình bậc hai")],
    )

    ready_active = await doc_repo.create(topic_id=1, title="Giáo trình Đại số", file_path="daiso.txt")
    await doc_repo.finish_processing(ready_active.id, chunks=["Công thức nghiệm bậc hai", "Định lý Vi-ét"])
    doc_repo._documents[ready_active.id] = replace(doc_repo._documents[ready_active.id], is_active=True)

    inactive = await doc_repo.create(topic_id=1, title="Tài liệu chưa bật", file_path="off.txt")
    await doc_repo.finish_processing(inactive.id, chunks=["Không được trích dẫn"])

    app = create_app(
        user_repository=users,
        catalog_repository=catalog,
        chat_repository=chat_repo,
        document_repository=doc_repo,
        llm_client=FakeLLMClient(),
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        register = await client.post("/api/auth/register", json={
            "name": "Nguyễn Văn A",
            "email": "learner@example.com",
            "password": "Password123!",
            "confirmPassword": "Password123!",
            "consent": True,
        })
        assert register.status_code == 201
        logged_in = await client.post("/api/auth/login", json={"email": "learner@example.com", "password": "Password123!"})
        assert logged_in.status_code == 200
        token = logged_in.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        created = await client.post("/api/chat/sessions", json={"topicId": 1}, headers=headers)
        assert created.status_code == 201
        session_id = created.json()["session"]["id"]

        sent = await client.post(
            f"/api/chat/sessions/{session_id}/messages",
            json={"content": "Công thức nghiệm và định lý Vi-ét giúp giải phương trình bậc hai x^2 - 5x + 6 = 0 như thế nào?"},
            headers=headers,
        )
        assert sent.status_code == 201
        payload = sent.json()
        assert payload["userMessage"]["sourceRefs"] == []
        refs = payload["assistantMessage"]["sourceRefs"]
        assert len(refs) == 2
        assert refs[0]["documentId"] == ready_active.id
        assert refs[0]["title"] == "Giáo trình Đại số"
        assert refs[0]["chunkIndex"] == 0
        assert refs[1]["chunkIndex"] == 1

        history = await client.get(f"/api/chat/sessions/{session_id}/messages", headers=headers)
        assert history.status_code == 200
        messages = history.json()["messages"]
        assert len(messages) == 2
        assert messages[0]["sourceRefs"] == []
        assert messages[1]["sourceRefs"] == refs
