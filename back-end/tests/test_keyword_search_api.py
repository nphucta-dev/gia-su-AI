"""Authenticated keyword lookup is exposed without model calls or file-path leaks."""

from contextlib import asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.main import create_app
from app.repositories.user_repository import InMemoryUserRepository
from test_keyword_retrieval import add_source, make_repository


pytestmark = pytest.mark.anyio
ROOT = "/api/catalog/topics/1/chunks"


@asynccontextmanager
async def api(*, role="LEARNER", missing_repository=False):
    users = InMemoryUserRepository()
    user = await users.create(name="Người học", email="keywords@example.com", password_hash="private-hash", role=role)
    repository = make_repository()
    await add_source(repository, ["Hàm số có đạo hàm.", "Hàm số"], title="Tài liệu đúng")
    await add_source(repository, ["Nguồn tắt: hàm số"], active=False)
    app = create_app(
        user_repository=users, document_repository=None if missing_repository else repository,
        settings=Settings(jwt_secret="keyword-search-test-" + "x" * 40),
    )
    token = app.state.token_service.create_access_token(user.id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
        headers={"Authorization": "Bearer " + token},
    ) as client:
        yield SimpleNamespace(client=client, users=users, user=user, repository=repository, app=app)


@pytest.mark.parametrize("role", ["LEARNER", "ADMIN"])
async def test_authored_search_route_returns_ranked_source_content_without_private_paths(role):
    async with api(role=role) as state:
        response = await state.client.get(ROOT, params={"q": "HAM SO", "limit": 1})
        assert response.status_code == 200, response.text
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert body["topicId"] == 1 and body["query"] == "HAM SO" and body["limit"] == 1
        assert len(body["chunks"]) == 1
        chunk = body["chunks"][0]
        assert set(chunk) == {"id", "documentId", "documentTitle", "topicId", "chunkIndex", "content", "score"}
        assert chunk["documentTitle"] == "Tài liệu đúng" and chunk["score"] == 2
        assert chunk["content"] == "Hàm số có đạo hàm."
        for private in ("file_path", "filePath", "private-server-path", "password", state.user.email):
            assert private not in response.text


async def test_no_matching_keyword_returns_an_empty_success_response():
    async with api() as state:
        response = await state.client.get(ROOT, params={"q": "khongtonTai"})
        assert response.status_code == 200
        assert response.json() == {"topicId": 1, "query": "khongtonTai", "limit": 5, "chunks": []}


@pytest.mark.parametrize("access,status", [("missing", 401), ("invalid", 401), ("inactive", 403), ("deleted", 401)])
async def test_search_requires_a_current_active_authenticated_account(access, status):
    async with api() as state:
        headers = {}
        if access == "missing":
            headers = {"Authorization": ""}
        elif access == "invalid":
            headers = {"Authorization": "Bearer invalid-token"}
        elif access == "inactive":
            state.users._users[state.user.id] = replace(state.user, is_active=False)
        else:
            state.users._users.pop(state.user.id)
        response = await state.client.get(ROOT, params={"q": "ham"}, headers=headers)
        assert response.status_code == status
        assert response.headers["cache-control"] == "no-store"
        assert "Hàm số có đạo hàm" not in response.text


@pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": " "}, {"q": "%_"}, {"q": "\u200b"}, {"q": "ham\x00"}, {"q": "x" * 401}, {"q": "ham", "limit": 0}, {"q": "ham", "limit": 21}])
async def test_invalid_query_or_limit_is_rejected(params):
    async with api() as state:
        response = await state.client.get(ROOT, params=params)
        assert response.status_code == 422


@pytest.mark.parametrize("path", ["/api/catalog/topics/0/chunks", "/api/catalog/topics/2147483648/chunks", "/api/catalog/topics/not-an-id/chunks"])
async def test_topic_ids_are_bounded(path):
    async with api() as state:
        assert (await state.client.get(path, params={"q": "ham"})).status_code == 422


async def test_missing_or_disabled_topic_returns_404_and_disabled_source_disappears_immediately():
    async with api() as state:
        assert (await state.client.get("/api/catalog/topics/999/chunks", params={"q": "ham"})).status_code == 404
        state.repository._documents[1] = replace(state.repository._documents[1], is_active=False)
        empty = await state.client.get(ROOT, params={"q": "ham"})
        assert empty.status_code == 200 and empty.json()["chunks"] == []
        state.repository._topics[1] = replace(state.repository._topics[1], is_active=False)
        assert (await state.client.get(ROOT, params={"q": "ham"})).status_code == 404


async def test_missing_repository_and_database_errors_have_safe_unavailable_responses():
    async with api(missing_repository=True) as state:
        assert (await state.client.get(ROOT, params={"q": "ham"})).status_code == 503
    async with api() as state:
        async def failed_query(topic_id):
            raise SQLAlchemyError("private-database-connection-details")
        state.repository.find_upload_topic = failed_query
        response = await state.client.get(ROOT, params={"q": "ham"})
        assert response.status_code == 503
        assert response.headers["cache-control"] == "no-store"
        assert "private-database" not in response.text
