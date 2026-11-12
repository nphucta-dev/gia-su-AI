import pytest

from app.validators.register_validator import (
    EMAIL_LOCAL_MAX,
    EMAIL_MAX,
    MESSAGES,
    NAME_MAX,
    PASSWORD_MAX,
    RegisterData,
    validate_register_input,
)


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


def errors_of(**overrides):
    return validate_register_input(valid_body(**overrides)).errors


def test_du_lieu_hop_le_va_value_da_chuan_hoa():
    result = validate_register_input(valid_body())
    assert result.valid is True
    assert result.errors == {}
    assert result.value == RegisterData(
        name="Nguyễn Văn An", email="an@example.com", password="MatKhau@123"
    )


def test_chuan_hoa_trim_gop_khoang_trang_trong_ten_email_chu_thuong():
    result = validate_register_input(
        valid_body(name="  Nguyễn   Văn  An ", email="  An.Nguyen@Example.COM ")
    )
    assert result.valid is True
    assert result.value.name == "Nguyễn Văn An"
    assert result.value.email == "an.nguyen@example.com"


def test_khong_trim_mat_khau():
    result = validate_register_input(
        valid_body(password="  abc12345  ", confirmPassword="  abc12345  ")
    )
    assert result.valid is True
    assert result.value.password == "  abc12345  "


def test_whitelist_truong_la_khong_xuat_hien_trong_value():
    result = validate_register_input(valid_body(role="ADMIN", id="x", is_admin=True))
    assert result.valid is True
    assert set(vars(result.value)) == {"name", "email", "password"}


@pytest.mark.parametrize("body", [None, "chuỗi", 42, True, [], [valid_body()]])
def test_body_khong_phai_object_thi_bao_loi_body(body):
    result = validate_register_input(body)
    assert result.valid is False
    assert result.errors == {"body": MESSAGES["body"]}
    assert result.value is None


def test_body_rong_bao_thieu_tat_ca_truong_dung_thong_bao_cua_front_end():
    result = validate_register_input({})
    assert result.valid is False
    assert result.errors == {
        "name": "Vui lòng nhập họ tên.",
        "email": "Vui lòng nhập email.",
        "password": "Vui lòng nhập mật khẩu.",
        "confirmPassword": "Vui lòng nhập lại mật khẩu để xác nhận.",
        "consent": "Vui lòng xác nhận bạn đồng ý với quy định sử dụng trước khi tiếp tục.",
    }


def test_ho_ten_rong_chi_khoang_trang_qua_dai_sai_kieu_ky_tu_dieu_khien():
    assert errors_of(name="")["name"] == MESSAGES["name_required"]
    assert errors_of(name="   ")["name"] == MESSAGES["name_required"]
    assert errors_of(name="a" * (NAME_MAX + 1))["name"] == MESSAGES["name_too_long"]
    assert errors_of(name=123)["name"] == MESSAGES["name_type"]
    assert errors_of(name={"a": 1})["name"] == MESSAGES["name_type"]
    assert errors_of(name="An\u0000")["name"] == MESSAGES["name_chars"]
    assert validate_register_input(valid_body(name="a" * NAME_MAX)).valid is True


def test_email_thieu_sai_kieu():
    assert errors_of(email="")["email"] == MESSAGES["email_required"]
    assert errors_of(email=123)["email"] == MESSAGES["email_type"]


@pytest.mark.parametrize(
    "email",
    [
        "invalid",
        "a@b",
        "@example.com",
        "an@",
        "an @example.com",
        "an@@example.com",
        "an@example..com",
        "an..nguyen@example.com",
        ".an@example.com",
        "an.@example.com",
        "an@.example.com",
        "an@example.com.",
        "an@-example.com",
    ],
)
def test_email_sai_dinh_dang(email):
    assert errors_of(email=email)["email"] == MESSAGES["email_format"]


def test_email_qua_dai():
    too_long = "a" * EMAIL_MAX + "@example.com"
    assert errors_of(email=too_long)["email"] == MESSAGES["email_too_long"]
    long_local = "a" * (EMAIL_LOCAL_MAX + 1) + "@example.com"
    assert errors_of(email=long_local)["email"] == MESSAGES["email_format"]


@pytest.mark.parametrize(
    "email", ["an@example.com", "an.nguyen+gia-su@sub.example.vn", "a_b-c@ptit.edu.vn"]
)
def test_email_hop_le_thuong_gap(email):
    assert validate_register_input(valid_body(email=email)).valid is True


def test_mat_khau_thieu_ngan_dung_8_ky_tu_qua_dai_sai_kieu():
    short = errors_of(password="1234567", confirmPassword="1234567")
    assert short["password"] == MESSAGES["password_too_short"]
    assert "confirmPassword" not in short

    assert errors_of(password="", confirmPassword="")["password"] == MESSAGES["password_required"]
    assert errors_of(password=12345678, confirmPassword="12345678")["password"] == MESSAGES["password_type"]
    assert validate_register_input(valid_body(password="12345678", confirmPassword="12345678")).valid

    too_long = "a" * (PASSWORD_MAX + 1)
    assert errors_of(password=too_long, confirmPassword=too_long)["password"] == MESSAGES["password_too_long"]
    max_len = "a" * PASSWORD_MAX
    assert validate_register_input(valid_body(password=max_len, confirmPassword=max_len)).valid


def test_nhap_lai_mat_khau_thieu_khong_khop_phan_biet_hoa_thuong_sai_kieu():
    assert errors_of(confirmPassword="")["confirmPassword"] == MESSAGES["confirm_required"]
    assert errors_of(confirmPassword=None)["confirmPassword"] == MESSAGES["confirm_required"]
    assert errors_of(confirmPassword="MatKhau@124")["confirmPassword"] == MESSAGES["confirm_mismatch"]
    assert errors_of(confirmPassword="matkhau@123")["confirmPassword"] == MESSAGES["confirm_mismatch"]
    assert errors_of(confirmPassword=12345678)["confirmPassword"] == MESSAGES["confirm_type"]


@pytest.mark.parametrize("consent", [False, None, "true", "on", 1, 0, [], {}])
def test_dong_y_quy_dinh_chi_nhan_boolean_true(consent):
    assert errors_of(consent=consent)["consent"] == MESSAGES["consent_required"]


def test_consent_true_hop_le():
    assert validate_register_input(valid_body(consent=True)).valid is True


def test_nhieu_loi_cung_luc_duoc_tra_ve_theo_tung_truong():
    result = validate_register_input(
        {"name": "", "email": "sai", "password": "123", "confirmPassword": "456", "consent": False}
    )
    assert result.valid is False
    assert sorted(result.errors) == ["confirmPassword", "consent", "email", "name", "password"]
    assert result.value is None
