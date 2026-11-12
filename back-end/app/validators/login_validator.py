"""Kiểm tra dữ liệu đăng nhập; không thay đổi khoảng trắng trong mật khẩu."""

from dataclasses import dataclass, field
from typing import Any

from app.validators.register_validator import MESSAGES, PASSWORD_MAX, _validate_email


@dataclass(frozen=True)
class LoginData:
    email: str
    password: str


@dataclass(frozen=True)
class LoginValidation:
    valid: bool
    errors: dict[str, str] = field(default_factory=dict)
    value: LoginData | None = None


def validate_login_input(body: Any) -> LoginValidation:
    if not isinstance(body, dict):
        return LoginValidation(valid=False, errors={"body": MESSAGES["body"]})

    errors: dict[str, str] = {}
    email, email_error = _validate_email(body.get("email"))
    if email_error:
        errors["email"] = email_error

    password = body.get("password")
    if password is None or password == "":
        errors["password"] = MESSAGES["password_required"]
    elif not isinstance(password, str):
        errors["password"] = MESSAGES["password_type"]
    elif len(password) > PASSWORD_MAX:
        errors["password"] = MESSAGES["password_too_long"]

    if errors:
        return LoginValidation(valid=False, errors=errors)
    assert email is not None and isinstance(password, str)
    return LoginValidation(valid=True, value=LoginData(email=email, password=password))
