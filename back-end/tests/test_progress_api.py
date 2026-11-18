"""TK-082: guessing IDs or supplying an owner never exposes another account's progress."""

from contextlib import asynccontextmanager
from dataclasses import replace
from decimal import Decimal
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.progress_repository import InMemoryProgressRepository, ProgressRecord
from app.repositories.user_repository import InMemoryUserRepository

pytestmark = pytest.mark.anyio
ROOT = "/api/progress"


def progress_record(record_id, user_id, topic_id, *, studied="2026-11-18T00:00:00.000000Z"):
    return ProgressRecord(
        id=record_id, user_id=user_id, topic_id=topic_id, total_quizzes=2,
        correct_count=7, total_count=10, mastery_percent=Decimal("70.00"), last_studied_at=studied,
    )


@asynccontextmanager
async def api():
    users = InMemoryUserRepository()
    owner = await users.create(name="Người học", email="learner@example.com", password_hash="private-hash", role="LEARNER")
    other = await users.create(name="Người khác", email="other@example.com", password_hash="other-hash", role="LEARNER")
    admin = await users.create(name="Quản trị", email="admin@example.com", password_hash="admin-hash", role="ADMIN")
    records = [
        progress_record(11, owner.id, 1),
        progress_record(12, owner.id, 2, studied=None),
        progress_record(13, other.id, 1),
        progress_record(14, admin.id, 1),
    ]
    repository = InMemoryProgressRepository(records)
    app = create_app(
        user_repository=users, progress_repository=repository,
        settings=Settings(jwt_secret="progress-tests-" + "x" * 40),
    )
    def headers(user):
        token = app.state.token_service.create_access_token(user.id).access_token
        return {"Authorization": "Bearer " + token}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        headers=headers(owner),
    ) as client:
        yield SimpleNamespace(
            client=client, users=users, app=app, repository=repository,
            owner=owner, other=other, admin=admin, headers=headers,
        )


async def test_owner_reads_stored_progress_without_owner_or_account_data():
    async with api() as state:
        response = await state.client.get(ROOT + "/11")
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"progress": {
            "id": 11, "topicId": 1, "totalQuizzes": 2, "correctCount": 7, "totalCount": 10,
            "masteryPercent": 70.0, "lastStudiedAt": "2026-11-18T00:00:00.000000Z",
        }}
        other = await state.client.get(ROOT + "/13", headers=state.headers(state.other))
        admin = await state.client.get(ROOT + "/14", headers=state.headers(state.admin))
        assert other.status_code == admin.status_code == 200
        assert other.json()["progress"]["id"] == 13
        assert admin.json()["progress"]["id"] == 14


@pytest.mark.parametrize("role", ["other", "admin"])
async def test_foreign_and_missing_progress_are_indistinguishable_even_to_admin(role):
    async with api() as state:
        headers = state.headers(getattr(state, role))
        foreign = await state.client.get(ROOT + "/11", headers=headers)
        missing = await state.client.get(ROOT + "/999999", headers=headers)
        assert foreign.status_code == missing.status_code == 404
        assert foreign.json() == missing.json() == {
            "error": {"code": "PROGRESS_NOT_FOUND", "message": "Không tìm thấy tiến độ học tập của bạn."},
        }
        assert foreign.headers["cache-control"] == missing.headers["cache-control"] == "no-store"


async def test_pagination_is_scoped_before_offset_and_has_more_are_computed():
    async with api() as state:
        first = (await state.client.get(ROOT + "?limit=1&offset=0")).json()
        second = (await state.client.get(ROOT + "?limit=1&offset=1")).json()
        empty = (await state.client.get(ROOT + "?limit=1&offset=2")).json()
        assert [row["id"] for row in first["progress"]] == [11]
        assert first["limit"] == 1 and first["offset"] == 0 and first["hasMore"] is True
        assert [row["id"] for row in second["progress"]] == [12]
        assert second["progress"][0]["lastStudiedAt"] is None and second["hasMore"] is False
        assert empty == {"progress": [], "limit": 1, "offset": 2, "hasMore": False}
        admin = (await state.client.get(ROOT, headers=state.headers(state.admin))).json()
        assert [row["id"] for row in admin["progress"]] == [14]


@pytest.mark.parametrize("owner_field", ["user_id", "userId", "owner_id", "ownerId"])
async def test_client_owner_queries_cannot_change_list_or_resource_scope(owner_field):
    async with api() as state:
        query = f"?{owner_field}={state.other.id}"
        listing = await state.client.get(ROOT + query)
        assert listing.status_code == 200
        assert [row["id"] for row in listing.json()["progress"]] == [11, 12]
        own = await state.client.get(ROOT + "/11" + query)
        assert own.status_code == 200 and own.json()["progress"]["id"] == 11
        foreign = await state.client.get(ROOT + "/13" + query)
        assert foreign.status_code == 404


@pytest.mark.parametrize("path", [ROOT, ROOT + "/11"])
@pytest.mark.parametrize("access,status", [("guest", 401), ("invalid", 401), ("inactive", 403), ("deleted", 401)])
async def test_reads_require_current_active_authenticated_account(path, access, status):
    async with api() as state:
        headers = {}
        if access == "guest":
            headers["Authorization"] = ""
        elif access == "invalid":
            headers["Authorization"] = "Bearer invalid-token"
        elif access == "inactive":
            state.users._users[state.owner.id] = replace(state.owner, is_active=False)
        else:
            del state.users._users[state.owner.id]
        response = await state.client.get(path, headers=headers)
        assert response.status_code == status
        assert "progress" not in response.json()
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("path", [
    ROOT + "/0", ROOT + "/-1", ROOT + "/2147483648", ROOT + "/not-an-id",
    ROOT + "?limit=0", ROOT + "?limit=101", ROOT + "?offset=-1", ROOT + "?offset=100001",
])
async def test_ids_and_pagination_are_bounded(path):
    async with api() as state:
        response = await state.client.get(path)
        assert response.status_code == 422


async def test_read_api_cannot_transfer_progress_or_write_scores():
    async with api() as state:
        before = dict(state.repository._records)
        response = await state.client.patch(ROOT + "/11", json={"userId": state.other.id, "masteryPercent": 100})
        assert response.status_code == 405
        assert state.repository._records == before


async def test_default_memory_progress_is_empty_instead_of_demo_data():
    users = InMemoryUserRepository()
    user = await users.create(name="Người học", email="empty@example.com", password_hash="hash", role="LEARNER")
    app = create_app(user_repository=users, settings=Settings(jwt_secret="empty-progress-" + "x" * 40))
    token = app.state.token_service.create_access_token(user.id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test", headers={"Authorization": "Bearer " + token},
    ) as client:
        response = await client.get(ROOT)
        assert response.status_code == 200
        assert response.json() == {"progress": [], "limit": 20, "offset": 0, "hasMore": False}
