from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import Settings
from app.main import create_app
from app.repositories.user_repository import InMemoryUserRepository

pytestmark = pytest.mark.anyio


def make_app(repository=None, **options):
    return create_app(
        user_repository=repository or InMemoryUserRepository(),
        settings=Settings(jwt_secret="system-test-secret-" + "x" * 40),
        **options,
    )


async def test_database_check_executes_a_query_and_returns_connected():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    app = make_app(session_factory=sessionmaker(bind=engine))
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/database")
        assert response.status_code == 200
        assert response.json()["database"] == "connected"
        assert response.json()["status"] == "ok"
    finally:
        engine.dispose()


async def test_database_failure_is_503_and_does_not_expose_connection_details():
    factory = Mock(side_effect=SQLAlchemyError("private-host password=do-not-show"))
    app = make_app(session_factory=factory)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/database")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"
    assert "private-host" not in response.text and "do-not-show" not in response.text


async def test_database_check_without_a_configured_factory_is_503():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=make_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/database")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DATABASE_UNAVAILABLE"


async def test_admin_endpoint_enforces_bearer_token_and_database_role():
    repository = InMemoryUserRepository()
    app = make_app(repository)
    learner = await repository.create(
        name="Learner", email="learner@example.com", password_hash="unused", role="LEARNER"
    )
    admin = await repository.create(
        name="Admin", email="admin@example.com", password_hash="unused", role="ADMIN"
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        assert (await client.get("/api/admin/access")).status_code == 401
        for user, expected in ((learner, 403), (admin, 200)):
            token = app.state.token_service.create_access_token(user.id).access_token
            response = await client.get(
                "/api/admin/access", headers={"Authorization": f"Bearer {token}"}
            )
            assert response.status_code == expected
            if expected == 200:
                assert response.json()["role"] == "ADMIN"
