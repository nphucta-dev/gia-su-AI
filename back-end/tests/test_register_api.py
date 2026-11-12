import asyncio
import json
from contextlib import asynccontextmanager

import httpx
import pytest

from app.main import create_app
from app.repositories.user_repository import InMemoryUserRepository
from app.utils.password import hash_password, verify_password

ALLOWED_ORIGIN = "http://127.0.0.1:4173"
REGISTER = "/api/auth/register"

pytestmark = pytest.mark.anyio


def fast_hasher(password: str) -> str:
    # Tham số nhẹ để test chạy nhanh; vài test dùng hasher mặc định để kiểm tra cấu hình thật.
    return hash_password(password, n=1024, r=8, p=1)


def valid_body(**overrides):
    body = {
        "name": "Nguyễn Văn An",
        "email": "an@example.com",
        "password": "MatKhau@123",
        "confirmPassword": "MatKhau@123",
        "consent": True,
    }
    body.update(overrides)
    return body


@asynccontextmanager
async def api(**options):
    """Tạo app, trả về (client, repository). Lỗi 500 được trả về như phản hồi thật."""
    repository = options.pop("user_repository", None) or InMemoryUserRepository()
    options.setdefault("password_hasher", fast_hasher)
    app = create_app(user_repository=repository, cors_origins=[ALLOWED_ORIGIN], **options)
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, repository


async def test_dang_ky_thanh_cong_201_khong_lo_mat_khau():
    # Dùng hasher mặc định (scrypt cấu hình thật) cho test này.
    async with api(password_hasher=hash_password) as (client, _):
        response = await client.post(REGISTER, json=valid_body())
        assert response.status_code == 201
        assert response.headers["cache-control"] == "no-store"
        assert response.headers["x-content-type-options"] == "nosniff"

        data = response.json()
        assert data["message"] == "Đăng ký tài khoản thành công."
        user = data["user"]
        assert user["name"] == "Nguyễn Văn An"
        assert user["email"] == "an@example.com"
        assert user["role"] == "LEARNER"
        assert type(user["id"]) is int and user["id"] > 0
        assert user["createdAt"].endswith("Z")
        assert sorted(user) == ["createdAt", "email", "id", "name", "role"]

        raw = response.text
        assert "MatKhau@123" not in raw
        assert "password" not in raw.lower()  # không có trường password hay passwordHash nào
        assert "scrypt$" not in raw


async def test_mat_khau_duoc_luu_dang_hash_va_kiem_tra_lai_duoc():
    async with api(password_hasher=hash_password) as (client, repository):
        await client.post(REGISTER, json=valid_body())
        stored = await repository.find_by_email("an@example.com")
        assert stored.password_hash.startswith("scrypt$")
        assert "MatKhau@123" not in stored.password_hash
        assert verify_password("MatKhau@123", stored.password_hash) is True
        assert verify_password("SaiMatKhau", stored.password_hash) is False


async def test_email_duoc_chuan_hoa_chu_thuong_va_dang_ky_lai_khac_hoa_thuong_bi_trung():
    async with api() as (client, _):
        first = await client.post(REGISTER, json=valid_body(email="  An@Example.COM "))
        assert first.status_code == 201
        assert first.json()["user"]["email"] == "an@example.com"

        second = await client.post(REGISTER, json=valid_body(email="AN@example.com"))
        assert second.status_code == 409
        assert second.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"
        assert second.json()["error"]["fields"]["email"]


async def test_email_da_dang_ky_409_va_khong_tao_them_nguoi_dung():
    async with api() as (client, repository):
        assert (await client.post(REGISTER, json=valid_body())).status_code == 201
        response = await client.post(REGISTER, json=valid_body(name="Người khác"))
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"
        stored = await repository.find_by_email("an@example.com")
        assert stored.name == "Nguyễn Văn An"


async def test_hai_request_cung_email_dong_thoi_dung_mot_cai_thanh_cong():
    async with api() as (client, _):
        results = await asyncio.gather(
            client.post(REGISTER, json=valid_body(email="race@example.com")),
            client.post(REGISTER, json=valid_body(email="race@example.com")),
        )
        assert sorted(r.status_code for r in results) == [201, 409]


async def test_du_lieu_sai_422_kem_loi_theo_tung_truong_va_khong_tao_nguoi_dung():
    async with api() as (client, repository):
        response = await client.post(
            REGISTER,
            json={"name": "", "email": "sai-dinh-dang", "password": "123", "confirmPassword": "456", "consent": False},
        )
        assert response.status_code == 422
        error = response.json()["error"]
        assert error["code"] == "VALIDATION_ERROR"
        assert sorted(error["fields"]) == ["confirmPassword", "consent", "email", "name", "password"]
        assert await repository.find_by_email("sai-dinh-dang") is None


async def test_mat_khau_nhap_lai_khong_khop_422_o_truong_confirm_password():
    async with api() as (client, _):
        response = await client.post(REGISTER, json=valid_body(confirmPassword="KhacHoanToan1"))
        assert response.status_code == 422
        assert list(response.json()["error"]["fields"]) == ["confirmPassword"]


async def test_khong_the_tu_dat_role_body_gui_role_admin_van_tao_learner():
    async with api() as (client, _):
        response = await client.post(REGISTER, json=valid_body(role="ADMIN", id="tu-dat-id"))
        assert response.status_code == 201
        assert response.json()["user"]["role"] == "LEARNER"
        assert response.json()["user"]["id"] != "tu-dat-id"


async def test_json_sai_cu_phap_400_invalid_json():
    async with api() as (client, _):
        response = await client.post(
            REGISTER, content='{"name": "An",', headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "INVALID_JSON"


@pytest.mark.parametrize("body", [[valid_body()], "42", 42, "chuỗi", None])
async def test_body_khong_phai_object_422(body):
    async with api() as (client, _):
        response = await client.post(
            REGISTER, content=json.dumps(body), headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 422
        assert response.json()["error"]["fields"] == {"body": "Dữ liệu gửi lên không hợp lệ."}


async def test_thieu_body_json_422_thay_vi_loi_500():
    async with api() as (client, _):
        response = await client.post(REGISTER, headers={"Content-Type": "application/json"})
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


async def test_content_type_khong_phai_json_415():
    async with api() as (client, _):
        wrong = await client.post(
            REGISTER, content=json.dumps(valid_body()), headers={"Content-Type": "text/plain"}
        )
        assert wrong.status_code == 415
        assert wrong.json()["error"]["code"] == "UNSUPPORTED_MEDIA_TYPE"

        # Content-Type JSON kèm charset vẫn được chấp nhận.
        ok = await client.post(
            REGISTER,
            content=json.dumps(valid_body()),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        assert ok.status_code == 201


async def test_body_qua_lon_413_theo_content_length():
    async with api() as (client, _):
        response = await client.post(REGISTER, json=valid_body(name="a" * (20 * 1024)))
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"
        assert response.headers["cache-control"] == "no-store"


async def test_body_qua_lon_413_khi_gui_dang_chunked_khong_co_content_length():
    async def chunks():
        for _ in range(30):
            yield b"a" * 1024

    async with api() as (client, _):
        response = await client.post(
            REGISTER, content=chunks(), headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 413
        assert response.json()["error"]["code"] == "PAYLOAD_TOO_LARGE"


async def test_duong_dan_khong_ton_tai_404_va_sai_method_405_dang_json():
    async with api() as (client, _):
        missing = await client.get("/api/khong-co")
        assert missing.status_code == 404
        assert missing.json()["error"]["code"] == "NOT_FOUND"

        wrong_method = await client.get(REGISTER)
        assert wrong_method.status_code == 405
        assert wrong_method.json()["error"]["code"] == "METHOD_NOT_ALLOWED"
        assert wrong_method.headers["allow"] == "POST"


async def test_health_check_hoat_dong():
    async with api() as (client, _):
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        assert response.headers["x-content-type-options"] == "nosniff"
        assert "cache-control" not in response.headers


async def test_cors_preflight_origin_front_end_duoc_phep_origin_la_thi_khong():
    async with api() as (client, _):
        allowed = await client.options(
            REGISTER,
            headers={
                "Origin": ALLOWED_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == ALLOWED_ORIGIN
        assert "POST" in allowed.headers["access-control-allow-methods"]

        denied = await client.options(
            REGISTER,
            headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
        )
        assert denied.status_code == 400
        assert "access-control-allow-origin" not in denied.headers

        actual = await client.post(
            REGISTER, json=valid_body(email="cors@example.com"), headers={"Origin": ALLOWED_ORIGIN}
        )
        assert actual.headers["access-control-allow-origin"] == ALLOWED_ORIGIN

        too_big = await client.post(
            REGISTER, json=valid_body(name="a" * 20000), headers={"Origin": ALLOWED_ORIGIN}
        )
        assert too_big.status_code == 413
        assert too_big.headers["access-control-allow-origin"] == ALLOWED_ORIGIN


async def test_loi_bat_ngo_o_tang_luu_tru_500_chung_chung_khong_lo_chi_tiet():
    class BrokenRepository:
        async def find_by_email(self, email):
            raise RuntimeError("kết nối CSDL thất bại: mật khẩu root=bí-mật")

        async def create(self, **kwargs):
            raise AssertionError("không dùng tới")

    async with api(user_repository=BrokenRepository()) as (client, _):
        response = await client.post(REGISTER, json=valid_body())
        assert response.status_code == 500
        assert response.json()["error"]["code"] == "INTERNAL_ERROR"
        assert "bí-mật" not in response.text


async def test_co_the_thay_bo_bam_mat_khau_qua_password_hasher():
    calls = []

    def fake_hasher(password):
        calls.append(password)
        return "hash-gia"

    async with api(password_hasher=fake_hasher) as (client, repository):
        response = await client.post(REGISTER, json=valid_body())
        assert response.status_code == 201
        assert calls == ["MatKhau@123"]
        stored = await repository.find_by_email("an@example.com")
        assert stored.password_hash == "hash-gia"


async def test_tai_lieu_openapi_mo_ta_dung_body_va_ma_loi():
    async with api() as (client, _):
        response = await client.get("/openapi.json")
        assert response.status_code == 200
        operation = response.json()["paths"][REGISTER]["post"]
        schema = operation["requestBody"]["content"]["application/json"]["schema"]
        assert sorted(schema["properties"]) == ["confirmPassword", "consent", "email", "name", "password"]
        assert {"201", "400", "409", "413", "415", "422"} <= set(operation["responses"])
