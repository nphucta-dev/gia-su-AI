"""TK-079: Tách kiểm tra quota khỏi GET lịch sử và GET dashboard/tiến độ."""

from decimal import Decimal

import httpx
import pytest

from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import InMemoryChatRepository
from app.repositories.progress_repository import InMemoryProgressRepository, ProgressRecord
from app.repositories.user_repository import InMemoryUserRepository
from app.services.llm_client import LLMReply
from app.utils.errors import AppError


class ExhaustedQuotaService:
    async def ensure_within_quota(self, user):
        raise AppError(429, "AI_QUOTA_EXCEEDED", "Bạn đã dùng hết lượt hỏi đáp AI trong ngày.")


class FakeLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages):
        self.calls += 1
        return LLMReply(content="Gợi ý", token_count=10)


@pytest.mark.anyio
async def test_history_and_progress_get_endpoints_remain_accessible_when_quota_exhausted():
    users = InMemoryUserRepository()
    catalog = InMemoryCatalogRepository()
    chat_repo = InMemoryChatRepository(catalog)
    progress_repo = InMemoryProgressRepository([
        ProgressRecord(1, user_id=1, topic_id=1, total_quizzes=1, correct_count=4, total_count=5, mastery_percent=Decimal("80.00"), last_studied_at="2026-11-18T10:00:00Z"),
    ])
    llm = FakeLLMClient()
    app = create_app(
        user_repository=users,
        catalog_repository=catalog,
        chat_repository=chat_repo,
        progress_repository=progress_repo,
        llm_client=llm,
        password_hasher=lambda raw: f"hash:{raw}",
    )

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/auth/register", json={
            "fullName": "Nguyễn Văn A",
            "email": "quota@example.com",
            "password": "Password123!",
            "birthYear": 2002,
        })
        assert reg.status_code == 201
        headers = {"Authorization": f"Bearer {reg.json()['token']}"}

        created = await client.post("/api/chat/sessions", json={"topicId": 1}, headers=headers)
        assert created.status_code == 201
        session_id = created.json()["session"]["id"]

        # Bật trạng thái hết quota sau khi đã có phiên chat
        app.state.quota_service = ExhaustedQuotaService()

        # Các endpoint gọi AI bị chặn 429 và không gọi LLM
        assert (await client.post(f"/api/chat/sessions/{session_id}/messages", json={"content": "Hỏi tiếp"}, headers=headers)).status_code == 429
        assert (await client.post(f"/api/chat/sessions/{session_id}/hints", headers=headers)).status_code == 429
        assert (await client.post(f"/api/chat/sessions/{session_id}/solution", json={"confirmed": True}, headers=headers)).status_code == 429
        assert llm.calls == 0

        # Các endpoint GET lịch sử và GET tiến độ/dashboard vẫn hoạt động bình thường
        assert (await client.get("/api/chat/sessions", headers=headers)).status_code == 200
        assert (await client.get(f"/api/chat/sessions/{session_id}", headers=headers)).status_code == 200
        assert (await client.get(f"/api/chat/sessions/{session_id}/messages", headers=headers)).status_code == 200
        assert (await client.get("/api/progress", headers=headers)).status_code == 200
