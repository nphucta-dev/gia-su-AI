from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import datetime, timezone
import json
from unittest.mock import MagicMock

import httpx
import pytest

from app.config import Settings
from app.main import create_app
from app.models.user import User as UserModel
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.repositories.user_repository import InMemoryUserRepository

pytestmark = pytest.mark.anyio
PROFILE = "/api/profile"


@asynccontextmanager
async def profile_api(role="LEARNER"):
    repository = InMemoryUserRepository()
    current = await repository.create(
        name="Nguyễn Văn An", email="an@example.com", password_hash="private-hash", role=role,
    )
    other = await repository.create(
        name="Tài khoản khác", email="other@example.com", password_hash="other-hash", role="LEARNER",
    )
    app = create_app(user_repository=repository, settings=Settings(jwt_secret="profile-tests-" + "x" * 40))
    token = app.state.token_service.create_access_token(current.id).access_token
    headers = {"Authorization": f"Bearer {token}"}
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, headers, repository, current, other


@pytest.mark.parametrize("role", ["LEARNER", "ADMIN"])
async def test_profile_get_is_current_user_and_exposes_no_secrets(role):
    async with profile_api(role) as (client, headers, _, current, _):
        response = await client.get(PROFILE, headers=headers)
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {"user": {
            "id": current.id, "name": current.name, "email": current.email,
            "role": role, "createdAt": current.created_at, "birthYear": None,
        }}
        assert "password" not in response.text.lower()
        assert "private-hash" not in response.text


@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_profile_requires_valid_login(method):
    async with profile_api() as (client, _, _, _, _):
        options = {"json": {"name": "Tên mới"}} if method == "PATCH" else {}
        response = await client.request(method, PROFILE, **options)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
        invalid = await client.request(method, PROFILE, headers={"Authorization": "Bearer invalid"}, **options)
        assert invalid.status_code == 401


@pytest.mark.parametrize("method", ["GET", "PATCH"])
async def test_inactive_account_cannot_read_or_change_profile(method):
    async with profile_api() as (client, headers, repository, current, _):
        repository._users[current.id] = replace(current, is_active=False)
        options = {"json": {"name": "Tên mới"}} if method == "PATCH" else {}
        response = await client.request(method, PROFILE, headers=headers, **options)
        assert response.status_code == 403
        assert (await repository.find_by_id(current.id)).name == current.name


@pytest.mark.parametrize("role", ["LEARNER", "ADMIN"])
async def test_profile_patch_persists_only_own_name_and_birth_year(role):
    async with profile_api(role) as (client, headers, repository, current, other):
        response = await client.patch(PROFILE, headers=headers, json={"name": "  Nguyễn   Minh   An  ", "birthYear": 2000})
        assert response.status_code == 200
        assert response.json()["message"] == "Cập nhật hồ sơ thành công."
        assert response.json()["user"]["name"] == "Nguyễn Minh An"
        assert response.json()["user"]["birthYear"] == 2000
        saved = await repository.find_by_id(current.id)
        assert saved.name == "Nguyễn Minh An" and saved.birth_year == 2000
        assert (saved.id, saved.email, saved.password_hash, saved.role, saved.is_active, saved.created_at) == (
            current.id, current.email, current.password_hash, current.role, current.is_active, current.created_at,
        )
        assert await repository.find_by_id(other.id) == other
        assert (await client.get(PROFILE, headers=headers)).json()["user"] == response.json()["user"]
        me = await client.get("/api/auth/me", headers=headers)
        assert me.json()["user"]["name"] == "Nguyễn Minh An"
        assert sorted(me.json()["user"]) == ["createdAt", "email", "id", "name", "role"]


async def test_partial_patch_keeps_omitted_fields_and_null_clears_birth_year():
    async with profile_api() as (client, headers, _, _, _):
        year_only = await client.patch(PROFILE, headers=headers, json={"birthYear": 1995})
        assert year_only.json()["user"]["name"] == "Nguyễn Văn An"
        name_only = await client.patch(PROFILE, headers=headers, json={"name": "An mới"})
        assert name_only.json()["user"]["birthYear"] == 1995
        cleared = await client.patch(PROFILE, headers=headers, json={"birthYear": None})
        assert cleared.json()["user"]["birthYear"] is None
        assert cleared.json()["user"]["name"] == "An mới"


@pytest.mark.parametrize("field,value", [
    ("name", ""), ("name", "  "), ("name", None), ("name", 42),
    ("name", "x" * 121), ("name", "An\x00"), ("name", "An\ud800"),
    ("birthYear", True), ("birthYear", "2000"), ("birthYear", 2000.5),
    ("birthYear", 1899), ("birthYear", datetime.now(timezone.utc).year + 1),
])
async def test_invalid_profile_fields_return_422_and_do_not_write(field, value):
    async with profile_api() as (client, headers, repository, current, _):
        # ensure_ascii cho phép kiểm thử JSON chứa surrogate đơn lẻ mà không encode lỗi ở client.
        response = await client.patch(
            PROFILE, headers={**headers, "Content-Type": "application/json"},
            content=json.dumps({field: value}),
        )
        assert response.status_code == 422
        assert field in response.json()["error"]["fields"]
        assert await repository.find_by_id(current.id) == current


@pytest.mark.parametrize("extra,value", [
    ("id", 2), ("user_id", 2), ("email", "takeover@example.com"),
    ("role", "ADMIN"), ("password", "new-password"), ("is_active", False),
])
async def test_profile_rejects_sensitive_fields_and_target_ids(extra, value):
    async with profile_api() as (client, headers, repository, current, other):
        response = await client.patch(PROFILE, headers=headers, json={"name": "Không lưu", extra: value})
        assert response.status_code == 422
        assert await repository.find_by_id(current.id) == current
        assert await repository.find_by_id(other.id) == other
        assert (await client.patch(f"{PROFILE}/{other.id}", headers=headers, json={"name": "Không lưu"})).status_code == 404


@pytest.mark.parametrize("body", [{}, None, [], "profile", 123])
async def test_profile_invalid_body_is_rejected(body):
    async with profile_api() as (client, headers, repository, current, _):
        response = await client.patch(
            PROFILE, headers={**headers, "Content-Type": "application/json"}, content=json.dumps(body),
        )
        assert response.status_code == 422
        assert await repository.find_by_id(current.id) == current


async def test_profile_rejects_invalid_json_and_non_json_media_type():
    async with profile_api() as (client, headers, _, _, _):
        response = await client.patch(PROFILE, headers=headers, content="name=An")
        assert response.status_code == 415
        response = await client.patch(PROFILE, headers={**headers, "Content-Type": "application/json"}, content="{")
        assert response.status_code == 400


async def test_sql_repository_updates_allowed_columns_in_one_transaction():
    model = UserModel(
        id=7, full_name="Tên cũ", birth_year=1990, email="an@example.com", password_hash="hash",
        role="LEARNER", is_active=True, created_at=datetime.now(timezone.utc),
    )
    sessions = MagicMock()
    session = sessions.begin.return_value.__enter__.return_value
    session.get.return_value = model
    repository = SqlAlchemyUserRepository(sessions)
    result = await repository.update_profile(7, name="Tên mới", birth_year=None, update_birth_year=True)
    session.get.assert_called_once_with(UserModel, 7, with_for_update=True)
    assert result.name == "Tên mới" and result.birth_year is None
    assert (model.email, model.password_hash, model.role, model.is_active) == ("an@example.com", "hash", "LEARNER", True)
    sessions.begin.return_value.__exit__.assert_called_once_with(None, None, None)


async def test_sql_repository_keeps_year_when_patch_does_not_include_it():
    model = UserModel(
        id=7, full_name="Tên cũ", birth_year=1990, email="an@example.com", password_hash="hash",
        role="LEARNER", is_active=True, created_at=datetime.now(timezone.utc),
    )
    sessions = MagicMock()
    sessions.begin.return_value.__enter__.return_value.get.return_value = model
    result = await SqlAlchemyUserRepository(sessions).update_profile(7, name="Tên mới")
    assert result.name == "Tên mới" and result.birth_year == 1990


async def test_sql_repository_does_not_write_when_account_was_disabled_after_authentication():
    model = UserModel(
        id=7, full_name="Tên cũ", birth_year=1990, email="an@example.com", password_hash="hash",
        role="LEARNER", is_active=False, created_at=datetime.now(timezone.utc),
    )
    sessions = MagicMock()
    session = sessions.begin.return_value.__enter__.return_value
    session.get.return_value = model
    result = await SqlAlchemyUserRepository(sessions).update_profile(7, name="Tên mới", birth_year=2000, update_birth_year=True)
    assert not result.is_active
    assert model.full_name == "Tên cũ" and model.birth_year == 1990
    session.flush.assert_not_called()


async def test_sql_repository_commit_failure_never_returns_a_successful_update():
    model = UserModel(
        id=7, full_name="Tên cũ", birth_year=1990, email="an@example.com", password_hash="hash",
        role="LEARNER", is_active=True, created_at=datetime.now(timezone.utc),
    )
    sessions = MagicMock()
    sessions.begin.return_value.__enter__.return_value.get.return_value = model
    sessions.begin.return_value.__exit__.side_effect = RuntimeError("commit failed")
    with pytest.raises(RuntimeError, match="commit failed"):
        await SqlAlchemyUserRepository(sessions).update_profile(7, name="Tên mới")
