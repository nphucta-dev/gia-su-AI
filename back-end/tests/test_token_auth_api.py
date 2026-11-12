from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import timedelta
from typing import Annotated

import httpx
import jwt
import pytest
from fastapi import Depends

from app.config import Settings
from app.dependencies.auth import get_current_user, require_roles
from app.main import create_app
from app.repositories.user_repository import InMemoryUserRepository, User
from app.utils.password import hash_password

ALLOWED_ORIGIN = "http://127.0.0.1:4173"
SECRET = "khoa-bi-mat-dung-cho-test-" + "x" * 50
ME = "/api/auth/me"

pytestmark = pytest.mark.anyio


def fast_hasher(password: str) -> str:
    return hash_password(password, n=1024, r=8, p=1)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@asynccontextmanager
async def api():
    """Trả về (client, app, repository). Có thêm 2 route thử nghiệm dùng dependency xác thực."""
    repository = InMemoryUserRepository()
    app = create_app(
        user_repository=repository,
        password_hasher=fast_hasher,
        cors_origins=[ALLOWED_ORIGIN],
        settings=Settings(jwt_secret=SECRET),
    )

    @app.get("/api/test/private")
    async def private(user: Annotated[User, Depends(get_current_user)]):
        return {"email": user.email}

    @app.get("/api/test/admin", dependencies=[Depends(require_roles("ADMIN"))])
    async def admin_only():
        return {"ok": True}

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, app, repository


async def make_user(repository, *, email="an@example.com", role="LEARNER") -> User:
    return await repository.create(name="Nguyễn Văn An", email=email, password_hash="khong-dung", role=role)


def token_for(app, user_id: int | str, **kwargs) -> str:
    return app.state.token_service.create_access_token(user_id, **kwargs).access_token


# ---------- /api/auth/me ----------


async def test_me_voi_token_hop_le_tra_ve_nguoi_dung_khong_lo_mat_khau():
    async with api() as (client, app, repository):
        user = await make_user(repository)
        response = await client.get(ME, headers=bearer(token_for(app, user.id)))
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        body = response.json()
        assert sorted(body) == ["user"]
        assert body["user"]["id"] == user.id
        assert body["user"]["email"] == "an@example.com"
        assert body["user"]["role"] == "LEARNER"
        assert sorted(body["user"]) == ["createdAt", "email", "id", "name", "role"]
        assert "password" not in response.text.lower()
        assert "khong-dung" not in response.text


async def test_luong_day_du_dang_ky_roi_dung_token_goi_me():
    async with api() as (client, app, repository):
        registered = await client.post(
            "/api/auth/register",
            json={
                "name": "Sang Phúc Văn",
                "email": "sang@ptit.edu.vn",
                "password": "MatKhau@123",
                "confirmPassword": "MatKhau@123",
                "consent": True,
            },
        )
        user_id = registered.json()["user"]["id"]
        response = await client.get(ME, headers=bearer(token_for(app, user_id)))
        assert response.status_code == 200
        assert response.json()["user"]["email"] == "sang@ptit.edu.vn"


async def test_khong_gui_token_401_not_authenticated_kem_www_authenticate():
    async with api() as (client, _, _):
        response = await client.get(ME)
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"
        assert response.headers["www-authenticate"] == "Bearer"
        assert response.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "header",
    ["Basic Zm9vOmJhcg==", "Bearer", "Bearer ", "Token abc", "abc.def.ghi", ""],
)
async def test_header_authorization_sai_dinh_dang_401_not_authenticated(header):
    async with api() as (client, _, _):
        response = await client.get(ME, headers={"Authorization": header})
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "NOT_AUTHENTICATED"


async def test_scheme_bearer_khong_phan_biet_hoa_thuong():
    async with api() as (client, app, repository):
        user = await make_user(repository)
        token = token_for(app, user.id)
        for scheme in ("bearer", "BEARER", "Bearer"):
            response = await client.get(ME, headers={"Authorization": f"{scheme} {token}"})
            assert response.status_code == 200


async def test_token_het_han_401_token_expired():
    async with api() as (client, app, repository):
        user = await make_user(repository)
        token = token_for(app, user.id, expires_delta=timedelta(seconds=-30))
        response = await client.get(ME, headers=bearer(token))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "TOKEN_EXPIRED"
        assert 'error="invalid_token"' in response.headers["www-authenticate"]


async def test_token_gia_hoac_hong_401_invalid_token():
    async with api() as (client, app, repository):
        user = await make_user(repository)
        good = token_for(app, user.id)
        forged = jwt.encode({"sub": user.id}, "khoa-khac-" + "y" * 40, algorithm="HS256")
        for bad in ("abc.def.ghi", good[:-4] + "AAAA", forged, "a" * 5000):
            response = await client.get(ME, headers=bearer(bad))
            assert response.status_code == 401, bad[:20]
            assert response.json()["error"]["code"] == "INVALID_TOKEN"


async def test_token_hop_le_nhung_tai_khoan_khong_con_ton_tai_401_invalid_token():
    async with api() as (client, app, _):
        token = token_for(app, 2147483647)
        response = await client.get(ME, headers=bearer(token))
        assert response.status_code == 401
        assert response.json()["error"]["code"] == "INVALID_TOKEN"


async def test_tai_khoan_bi_vo_hieu_hoa_khong_the_dung_token_da_cap():
    async with api() as (client, app, repository):
        user = await make_user(repository)
        token = token_for(app, user.id)
        repository._users[user.id] = replace(user, is_active=False)

        response = await client.get(ME, headers=bearer(token))
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "FORBIDDEN"
        assert "password" not in response.text.lower()


async def test_token_cua_nguoi_nay_khong_the_dung_de_xem_nguoi_khac():
    async with api() as (client, app, repository):
        an = await make_user(repository, email="an@example.com")
        binh = await make_user(repository, email="binh@example.com")
        response = await client.get(ME, headers=bearer(token_for(app, binh.id)))
        assert response.json()["user"]["email"] == "binh@example.com"
        assert response.json()["user"]["id"] != an.id


# ---------- Dependency dùng lại cho route khác ----------


async def test_dependency_get_current_user_bao_ve_route_tuy_y():
    async with api() as (client, app, repository):
        user = await make_user(repository)
        assert (await client.get("/api/test/private")).status_code == 401
        ok = await client.get("/api/test/private", headers=bearer(token_for(app, user.id)))
        assert ok.status_code == 200
        assert ok.json() == {"email": "an@example.com"}


async def test_require_roles_learner_bi_403_admin_duoc_vao():
    async with api() as (client, app, repository):
        learner = await make_user(repository, email="hocvien@example.com", role="LEARNER")
        admin = await make_user(repository, email="admin@example.com", role="ADMIN")

        anonymous = await client.get("/api/test/admin")
        assert anonymous.status_code == 401

        denied = await client.get("/api/test/admin", headers=bearer(token_for(app, learner.id)))
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "FORBIDDEN"

        allowed = await client.get("/api/test/admin", headers=bearer(token_for(app, admin.id)))
        assert allowed.status_code == 200
        assert allowed.json() == {"ok": True}


async def test_doi_vai_tro_co_hieu_luc_ngay_vi_vai_tro_khong_nam_trong_token():
    async with api() as (client, app, repository):
        user = await make_user(repository, role="LEARNER")
        token = token_for(app, user.id)
        assert (await client.get("/api/test/admin", headers=bearer(token))).status_code == 403

        # Nâng quyền trong kho dữ liệu: cùng một token, không cần đăng nhập lại.
        promoted = User(**{**user.__dict__, "role": "ADMIN"})
        repository._users[user.id] = promoted
        assert (await client.get("/api/test/admin", headers=bearer(token))).status_code == 200


# ---------- CORS và tài liệu ----------


async def test_cors_preflight_cho_phep_header_authorization():
    async with api() as (client, _, _):
        response = await client.options(
            ME,
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert "authorization" in response.headers["access-control-allow-headers"].lower()


async def test_loi_401_cung_co_header_cors_de_front_end_doc_duoc_ma_loi():
    async with api() as (client, _, _):
        response = await client.get(ME, headers={"Origin": ALLOWED_ORIGIN})
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


async def test_openapi_khai_bao_bearer_de_docs_co_nut_authorize():
    async with api() as (client, _, _):
        spec = (await client.get("/openapi.json")).json()
        schemes = spec["components"]["securitySchemes"]
        assert any(s.get("type") == "http" and s.get("scheme") == "bearer" for s in schemes.values())
        assert "401" in spec["paths"][ME]["get"]["responses"]
