import base64
import json
import logging
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.config import JWT_SECRET_MIN_LENGTH, Settings, load_settings
from app.services.token_service import MAX_TOKEN_LENGTH, MESSAGES, TokenService
from app.utils.errors import AppError

SECRET = "khoa-bi-mat-dung-cho-test-" + "x" * 50
ISSUER = "gia-su-ai"


def make_service(**overrides):
    options = {"secret": SECRET, "issuer": ISSUER, "access_token_minutes": 30}
    options.update(overrides)
    return TokenService(**options)


def claims(**overrides):
    now = datetime.now(timezone.utc)
    base = {
        "sub": "user-1",
        "type": "access",
        "iss": ISSUER,
        "iat": now,
        "exp": now + timedelta(minutes=5),
    }
    base.update(overrides)
    return {k: v for k, v in base.items() if v is not None}


def verify_error(service, token) -> AppError:
    with pytest.raises(AppError) as info:
        service.verify_access_token(token)
    return info.value


def b64url(data: dict) -> str:
    raw = json.dumps(data, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


# ---------- Tạo và kiểm tra token hợp lệ ----------


def test_tao_roi_kiem_tra_token_hop_le():
    service = make_service()
    issued = service.create_access_token("user-1")
    assert issued.token_type == "Bearer"
    assert issued.expires_in == 30 * 60

    payload = service.verify_access_token(issued.access_token)
    assert payload.user_id == "user-1"
    assert payload.expires_at - payload.issued_at == timedelta(minutes=30)
    assert payload.expires_at > datetime.now(timezone.utc)


def test_token_chi_chua_dinh_danh_khong_chua_vai_tro_hay_email():
    token = make_service().create_access_token("user-1").access_token
    decoded = jwt.decode(token, options={"verify_signature": False})
    assert sorted(decoded) == ["exp", "iat", "iss", "sub", "type"]
    assert decoded["type"] == "access"
    assert decoded["iss"] == ISSUER


def test_khoa_qua_ngan_hoac_cau_hinh_sai_bi_tu_choi_ngay_khi_khoi_tao():
    with pytest.raises(ValueError):
        make_service(secret="ngan")
    with pytest.raises(ValueError):
        make_service(secret=None)
    with pytest.raises(ValueError):
        make_service(access_token_minutes=0)


@pytest.mark.parametrize("user_id", ["", None, 0, -1, True, 1.5])
def test_khong_the_phat_hanh_token_voi_user_id_khong_hop_le(user_id):
    with pytest.raises(ValueError):
        make_service().create_access_token(user_id)


# ---------- Token hết hạn ----------


def test_token_het_han_tra_ve_token_expired():
    service = make_service()
    token = service.create_access_token("user-1", expires_delta=timedelta(seconds=-5)).access_token
    error = verify_error(service, token)
    assert error.status_code == 401
    assert error.code == "TOKEN_EXPIRED"
    assert error.message == MESSAGES["token_expired"]
    assert "expired" in error.headers["WWW-Authenticate"]


# ---------- Token sai: mọi trường hợp đều INVALID_TOKEN ----------


def assert_invalid(service, token):
    error = verify_error(service, token)
    assert error.status_code == 401
    assert error.code == "INVALID_TOKEN"
    assert error.message == MESSAGES["invalid_token"]
    assert error.headers["WWW-Authenticate"].startswith("Bearer")


@pytest.mark.parametrize("garbage", ["", "abc", "a.b.c", "a.b", "....", "Bearer xyz", " ", "\x00", "ấ.ơ.ư"])
def test_chuoi_rac_bi_tu_choi(garbage):
    assert_invalid(make_service(), garbage)


@pytest.mark.parametrize("not_a_string", [None, 123, b"abc", ["a"], {"a": 1}])
def test_gia_tri_khong_phai_chuoi_bi_tu_choi(not_a_string):
    assert_invalid(make_service(), not_a_string)


def test_token_qua_dai_bi_tu_choi_truoc_khi_giai_ma():
    assert_invalid(make_service(), "a" * (MAX_TOKEN_LENGTH + 1))


def test_ky_bang_khoa_khac_bi_tu_choi():
    forged = jwt.encode(claims(), "mot-khoa-khac-" + "y" * 30, algorithm="HS256")
    assert_invalid(make_service(), forged)


def test_sua_noi_dung_token_giu_nguyen_chu_ky_bi_tu_choi():
    token = make_service().create_access_token("user-1").access_token
    header, body, signature = token.split(".")
    decoded = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    decoded["sub"] = "admin-1"  # thử đổi sang người dùng khác
    tampered = ".".join([header, b64url(decoded), signature])
    assert_invalid(make_service(), tampered)


def test_token_alg_none_bi_tu_choi():
    unsigned = ".".join([b64url({"alg": "none", "typ": "JWT"}), b64url({
        "sub": "user-1", "type": "access", "iss": ISSUER,
        "iat": int(datetime.now(timezone.utc).timestamp()),
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }), ""])
    assert_invalid(make_service(), unsigned)


@pytest.mark.parametrize("algorithm", ["HS384", "HS512"])
def test_doi_thuat_toan_ky_bi_tu_choi_du_cung_khoa(algorithm):
    token = jwt.encode(claims(), SECRET, algorithm=algorithm)
    assert_invalid(make_service(), token)


def test_sai_issuer_bi_tu_choi():
    token = jwt.encode(claims(iss="he-thong-khac"), SECRET, algorithm="HS256")
    assert_invalid(make_service(), token)


@pytest.mark.parametrize("missing", ["exp", "iat", "sub", "iss"])
def test_thieu_claim_bat_buoc_bi_tu_choi(missing):
    data = claims()
    del data[missing]
    assert_invalid(make_service(), jwt.encode(data, SECRET, algorithm="HS256"))


def test_token_khong_phai_loai_access_bi_tu_choi():
    for token_type in ("refresh", "", None):
        data = claims()
        if token_type is None:
            del data["type"]
        else:
            data["type"] = token_type
        assert_invalid(make_service(), jwt.encode(data, SECRET, algorithm="HS256"))


def test_sub_rong_bi_tu_choi():
    assert_invalid(make_service(), jwt.encode(claims(sub=""), SECRET, algorithm="HS256"))


def test_token_phat_hanh_o_tuong_lai_bi_tu_choi():
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    token = jwt.encode(claims(iat=future, exp=future + timedelta(minutes=5)), SECRET, algorithm="HS256")
    assert_invalid(make_service(), token)


def test_thong_bao_loi_khong_tiet_lo_nguyen_nhan_cu_the():
    service = make_service()
    forged = jwt.encode(claims(), "mot-khoa-khac-" + "y" * 30, algorithm="HS256")
    wrong_type = jwt.encode(claims(type="refresh"), SECRET, algorithm="HS256")
    assert verify_error(service, forged).message == verify_error(service, wrong_type).message


# ---------- Cấu hình ----------


def test_settings_doc_jwt_secret_tu_bien_moi_truong(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("ACCESS_TOKEN_MINUTES", "5")
    settings = load_settings()
    assert settings.jwt_secret == SECRET
    assert settings.access_token_minutes == 5


def test_settings_khong_dat_jwt_secret_thi_dung_khoa_ngau_nhien_va_canh_bao(monkeypatch, caplog):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.delenv("ACCESS_TOKEN_MINUTES", raising=False)
    with caplog.at_level(logging.WARNING, logger="app.config"):
        first, second = load_settings(), load_settings()
    assert len(first.jwt_secret) >= JWT_SECRET_MIN_LENGTH
    assert first.jwt_secret != second.jwt_secret
    assert "JWT_SECRET" in caplog.text
    assert first.access_token_minutes == 30


def test_settings_jwt_secret_qua_ngan_thi_bao_loi(monkeypatch):
    monkeypatch.setenv("JWT_SECRET", "ngan")
    with pytest.raises(ValueError, match="JWT_SECRET"):
        load_settings()


@pytest.mark.parametrize("value", ["abc", "0", "-5", "1.5"])
def test_settings_access_token_minutes_khong_hop_le(monkeypatch, value):
    monkeypatch.setenv("JWT_SECRET", SECRET)
    monkeypatch.setenv("ACCESS_TOKEN_MINUTES", value)
    with pytest.raises(ValueError, match="ACCESS_TOKEN_MINUTES"):
        load_settings()


def test_settings_khong_in_khoa_bi_mat_trong_repr():
    assert SECRET not in repr(Settings(jwt_secret=SECRET))
