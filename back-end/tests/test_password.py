import base64

import pytest

from app.utils.password import (
    DEFAULT_PARAMS,
    MAX_PASSWORD_LENGTH,
    hash_password,
    needs_rehash,
    verify_password,
)

# Tham số nhẹ để test chạy nhanh; mặc định production vẫn dùng DEFAULT_PARAMS.
FAST = {"n": 1024, "r": 8, "p": 1}


def test_hash_co_dung_dinh_dang_va_khong_chua_mat_khau_goc():
    hashed = hash_password("MatKhau@123", **FAST)
    parts = hashed.split("$")
    assert len(parts) == 6
    assert parts[:4] == ["scrypt", "1024", "8", "1"]
    assert "MatKhau@123" not in hashed


def test_cung_mat_khau_bam_hai_lan_cho_hai_hash_khac_nhau():
    assert hash_password("MatKhau@123", **FAST) != hash_password("MatKhau@123", **FAST)


def test_mat_khau_dung_duoc_xac_nhan_mat_khau_sai_bi_tu_choi():
    hashed = hash_password("MatKhau@123", **FAST)
    assert verify_password("MatKhau@123", hashed) is True
    assert verify_password("matkhau@123", hashed) is False
    assert verify_password("MatKhau@1234", hashed) is False
    assert verify_password("", hashed) is False


def test_ho_tro_tieng_viet_co_dau_va_khop_giua_cac_dang_unicode_tuong_duong():
    import unicodedata

    composed = "Mật khẩu của tôi 123"
    decomposed = unicodedata.normalize("NFD", composed)
    assert composed != decomposed
    hashed = hash_password(composed, **FAST)
    assert verify_password(decomposed, hashed) is True


def test_verify_dung_tham_so_luu_trong_hash_khong_phu_thuoc_cau_hinh_hien_tai():
    hashed = hash_password("abcd1234", n=2048, r=8, p=1)
    assert verify_password("abcd1234", hashed) is True


@pytest.mark.parametrize(
    "bad",
    [
        None,
        123,
        b"scrypt$1024$8$1$c2FsdA==$aGFzaA==",
        "",
        "not-a-hash",
        "bcrypt$1024$8$1$c2FsdA==$aGFzaA==",
        "scrypt$1024$8$1$c2FsdA==",
        "scrypt$abc$8$1$c2FsdA==$aGFzaA==",
        "scrypt$1000$8$1$c2FsdA==$aGFzaA==",  # N không phải lũy thừa của 2
        "scrypt$1024$8$1$$",
        "scrypt$1024$8$1$@@@$aGFzaA==",  # base64 sai
    ],
)
def test_hash_hong_hoac_sai_kieu_tra_ve_false_thay_vi_nem_loi(bad):
    assert verify_password("abcd1234", bad) is False


def test_tu_choi_hash_co_tham_so_vuot_gioi_han():
    hashed = hash_password("abcd1234", **FAST)
    alg, _n, r, p, salt, digest = hashed.split("$")
    for n in (2**30, 2**20):  # 2^20 * r=8 vượt giới hạn bộ nhớ 256 MiB
        tampered = "$".join([alg, str(n), r, p, salt, digest])
        assert verify_password("abcd1234", tampered) is False
    too_big_r = "$".join([alg, "1024", "1000", p, salt, digest])
    assert verify_password("abcd1234", too_big_r) is False
    too_big_p = "$".join([alg, "1024", r, "1000", salt, digest])
    assert verify_password("abcd1234", too_big_p) is False


def test_hash_bi_sua_mot_ky_tu_thi_khong_con_khop():
    parts = hash_password("abcd1234", **FAST).split("$")
    raw = bytearray(base64.b64decode(parts[5]))
    raw[len(raw) // 2] ^= 0x01
    parts[5] = base64.b64encode(bytes(raw)).decode("ascii")
    assert verify_password("abcd1234", "$".join(parts)) is False


def test_hash_password_tu_choi_dau_vao_khong_hop_le():
    for bad in (None, 12345678, b"abc", "", ["a"]):
        with pytest.raises(TypeError):
            hash_password(bad)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        hash_password("a" * (MAX_PASSWORD_LENGTH + 1))


def test_verify_tra_ve_false_voi_mat_khau_qua_dai_hoac_sai_kieu():
    hashed = hash_password("abcd1234", **FAST)
    assert verify_password("a" * (MAX_PASSWORD_LENGTH + 1), hashed) is False
    assert verify_password(None, hashed) is False
    assert verify_password(12345678, hashed) is False


def test_chap_nhan_mat_khau_dai_dung_bang_gioi_han():
    long_password = "a" * MAX_PASSWORD_LENGTH
    assert verify_password(long_password, hash_password(long_password, **FAST)) is True


def test_needs_rehash_tham_so_yeu_hon_mac_dinh_thi_can_bam_lai():
    weak = hash_password("abcd1234", **FAST)
    assert needs_rehash(weak) is True
    assert needs_rehash("khong-phai-hash") is True
    assert needs_rehash(None) is True

    current = hash_password("abcd1234")
    assert needs_rehash(current) is False
    assert current.split("$")[1] == str(DEFAULT_PARAMS.n)
    assert verify_password("abcd1234", current) is True
