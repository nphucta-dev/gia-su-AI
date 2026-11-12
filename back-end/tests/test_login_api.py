import json
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.repositories.user_repository import InMemoryUserRepository
from app.utils.password import hash_password

LOGIN = "/api/auth/login"
SECRET = "khoa-kiem-thu-dang-nhap-" + "x" * 40
pytestmark = pytest.mark.anyio


def fast_hasher(password: str) -> str:
    return hash_password(password, n=1024, r=8, p=1)


@asynccontextmanager
async def api():
    repository = InMemoryUserRepository()
    app = create_app(
        user_repository=repository,
        password_hasher=fast_hasher,
        settings=Settings(jwt_secret=SECRET),
    )
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, repository


async def create_user(repository, *, password="MatKhau@123", role="LEARNER"):
    return await repository.create(
        name="Nguyễn Văn An", email="an@example.com", password_hash=fast_hasher(password), role=role
    )


async def test_register_then_login_and_use_issued_token_for_me():
    async with api() as (client, _):
        registered = await client.post(
            "/api/auth/register",
            json={
                "name": "Nguyễn Văn An",
                "email": "an@example.com",
                "password": "MatKhau@123",
                "confirmPassword": "MatKhau@123",
                "consent": True,
            },
        )
        assert registered.status_code == 201
        response = await client.post(LOGIN, json={"email": "an@example.com", "password": "MatKhau@123"})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        result = response.json()
        assert result["token_type"] == "Bearer"
        assert result["expires_in"] == 30 * 60
        assert sorted(result) == ["access_token", "expires_in", "message", "token_type", "user"]
        assert result["user"] == registered.json()["user"]
        assert sorted(result["user"]) == ["createdAt", "email", "id", "name", "role"]
        assert "password" not in response.text.lower()
        assert "scrypt$" not in response.text
        assert "MatKhau@123" not in response.text
        me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {result['access_token']}"})
        assert me.status_code == 200
        assert me.json()["user"] == result["user"]


async def test_wrong_password_and_unknown_email_have_same_public_error():
    async with api() as (client, repository):
        await create_user(repository)
        wrong = await client.post(LOGIN, json={"email": "an@example.com", "password": "WrongPassword"})
        missing = await client.post(LOGIN, json={"email": "missing@example.com", "password": "WrongPassword"})
        assert wrong.status_code == missing.status_code == 401
        assert wrong.json() == missing.json()
        assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
        assert wrong.headers["www-authenticate"] == missing.headers["www-authenticate"] == "Bearer"
        assert "access_token" not in wrong.json()


async def test_disabled_account_only_disclosed_after_correct_password():
    async with api() as (client, repository):
        user = await create_user(repository)
        repository._users[user.id] = replace(user, is_active=False)
        wrong = await client.post(LOGIN, json={"email": "an@example.com", "password": "WrongPassword"})
        correct = await client.post(LOGIN, json={"email": "an@example.com", "password": "MatKhau@123"})
        assert wrong.status_code == 401
        assert wrong.json()["error"]["code"] == "INVALID_CREDENTIALS"
        assert correct.status_code == 403
        assert correct.json()["error"]["code"] == "FORBIDDEN"
        assert "access_token" not in correct.json()


async def test_email_normalized_and_role_from_body_is_ignored():
    async with api() as (client, repository):
        user = await create_user(repository)
        response = await client.post(
            LOGIN,
            json={"email": "  AN@EXAMPLE.COM  ", "password": "MatKhau@123", "role": "ADMIN", "id": "other"},
        )
        assert response.status_code == 200
        assert response.json()["user"]["id"] == user.id
        assert response.json()["user"]["role"] == "LEARNER"


async def test_short_legacy_password_is_checked_without_register_length_rule():
    async with api() as (client, repository):
        await create_user(repository, password="short")
        response = await client.post(LOGIN, json={"email": "an@example.com", "password": "short"})
        assert response.status_code == 200


async def test_leading_and_trailing_password_spaces_are_preserved():
    async with api() as (client, repository):
        await create_user(repository, password="  MatKhau@123  ")
        correct = await client.post(LOGIN, json={"email": "an@example.com", "password": "  MatKhau@123  "})
        trimmed = await client.post(LOGIN, json={"email": "an@example.com", "password": "MatKhau@123"})
        assert correct.status_code == 200
        assert trimmed.status_code == 401


async def test_admin_role_returned_from_account_record():
    async with api() as (client, repository):
        await create_user(repository, role="ADMIN")
        response = await client.post(LOGIN, json={"email": "an@example.com", "password": "MatKhau@123"})
        assert response.status_code == 200
        assert response.json()["user"]["role"] == "ADMIN"


@pytest.mark.parametrize("body", [None, [], "not-an-object", 123])
async def test_non_object_login_body_has_validation_error(body):
    async with api() as (client, _):
        response = await client.post(
            LOGIN, content=json.dumps(body), headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


@pytest.mark.parametrize(
    "body,fields",
    [
        ({}, {"email", "password"}),
        ({"email": "invalid", "password": "ok"}, {"email"}),
        ({"email": "an@example.com", "password": ""}, {"password"}),
        ({"email": "an@example.com", "password": 123}, {"password"}),
        ({"email": "an@example.com", "password": "x" * 129}, {"password"}),
    ],
)
async def test_login_validation_reports_field_errors(body, fields):
    async with api() as (client, _):
        response = await client.post(LOGIN, json=body)
        assert response.status_code == 422
        assert set(response.json()["error"]["fields"]) == fields


async def test_login_requires_json_and_reports_malformed_json():
    async with api() as (client, _):
        wrong_media = await client.post(LOGIN, content="email=an@example.com", headers={"Content-Type": "text/plain"})
        assert wrong_media.status_code == 415
        assert wrong_media.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"
        malformed = await client.post(LOGIN, content='{"email":', headers={"Content-Type": "application/json"})
        assert malformed.status_code == 400
        assert malformed.json()["error"]["code"] == "INVALID_JSON"


async def test_login_openapi_describes_request_and_token_response():
    async with api() as (client, _):
        schema = (await client.get("/openapi.json")).json()
        operation = schema["paths"][LOGIN]["post"]
        body = operation["requestBody"]["content"]["application/json"]["schema"]
        assert set(body["properties"]) == {"email", "password"}
        assert {"200", "401", "403", "415", "422"} <= set(operation["responses"])
