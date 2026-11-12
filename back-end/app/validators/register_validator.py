"""Kiểm tra dữ liệu đăng ký ở phía máy chủ.

Quy tắc và thông báo lỗi bám theo form đăng ký ở front-end
(``front-end/src/js/pages/account.js``) để người dùng thấy cùng một nội dung dù
lỗi được phát hiện ở trình duyệt hay ở API. Máy chủ vẫn phải kiểm tra lại vì dữ
liệu có thể được gửi trực tiếp, không qua form.

Body JSON::

    {"name", "email", "password", "confirmPassword", "consent"}

Kết quả của :func:`validate_register_input`:

- hợp lệ:   ``valid=True,  errors={},                value=RegisterData(name, email, password)``
- không hợp lệ: ``valid=False, errors={<trường>: <thông báo>}, value=None``

``value`` chỉ chứa các trường được phép (whitelist) và đã chuẩn hoá, nên các
trường lạ như ``role`` hay ``id`` trong body không bao giờ lọt xuống tầng dưới.

Lý do không dùng thông báo lỗi mặc định của Pydantic: chúng bằng tiếng Anh và
không khớp với nội dung front-end đang hiển thị.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

NAME_MAX = 120
EMAIL_MAX = 255
EMAIL_LOCAL_MAX = 64
PASSWORD_MIN = 8
PASSWORD_MAX = 128

MESSAGES = {
    "body": "Dữ liệu gửi lên không hợp lệ.",
    "name_required": "Vui lòng nhập họ tên.",
    "name_type": "Họ tên phải là chuỗi ký tự.",
    "name_too_long": f"Họ tên tối đa {NAME_MAX} ký tự.",
    "name_chars": "Họ tên không được chứa ký tự điều khiển.",
    "email_required": "Vui lòng nhập email.",
    "email_type": "Email phải là chuỗi ký tự.",
    "email_format": "Email chưa đúng định dạng. Vui lòng kiểm tra lại, ví dụ: ban@example.com.",
    "email_too_long": f"Email tối đa {EMAIL_MAX} ký tự.",
    "password_required": "Vui lòng nhập mật khẩu.",
    "password_type": "Mật khẩu phải là chuỗi ký tự.",
    "password_too_short": f"Mật khẩu cần có ít nhất {PASSWORD_MIN} ký tự. Vui lòng bổ sung để tiếp tục.",
    "password_too_long": f"Mật khẩu tối đa {PASSWORD_MAX} ký tự.",
    "confirm_required": "Vui lòng nhập lại mật khẩu để xác nhận.",
    "confirm_type": "Mật khẩu xác nhận phải là chuỗi ký tự.",
    "confirm_mismatch": "Mật khẩu xác nhận chưa khớp. Vui lòng nhập lại.",
    "consent_required": "Vui lòng xác nhận bạn đồng ý với quy định sử dụng trước khi tiếp tục.",
}

# Cùng biểu thức với front-end; các điều kiện rõ ràng sai được kiểm tra thêm ở dưới.
_EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_CONTROL_CHARS = re.compile("[\u0000-\u001f\u007f-\u009f]")


@dataclass(frozen=True)
class RegisterData:
    """Dữ liệu đăng ký đã được kiểm tra và chuẩn hoá."""

    name: str
    email: str
    password: str


@dataclass(frozen=True)
class RegisterValidation:
    valid: bool
    errors: dict[str, str] = field(default_factory=dict)
    value: RegisterData | None = None


def _validate_name(raw: Any) -> tuple[str | None, str | None]:
    """Trả về (giá trị đã chuẩn hoá, lỗi)."""
    if raw is None:
        return None, MESSAGES["name_required"]
    if not isinstance(raw, str):
        return None, MESSAGES["name_type"]
    # Gộp khoảng trắng liên tiếp: "Nguyễn   Văn  A" -> "Nguyễn Văn A".
    name = " ".join(raw.split())
    if not name:
        return None, MESSAGES["name_required"]
    if len(name) > NAME_MAX:
        return None, MESSAGES["name_too_long"]
    if _CONTROL_CHARS.search(name):
        return None, MESSAGES["name_chars"]
    return name, None


def _validate_email(raw: Any) -> tuple[str | None, str | None]:
    if raw is None:
        return None, MESSAGES["email_required"]
    if not isinstance(raw, str):
        return None, MESSAGES["email_type"]
    email = raw.strip().lower()
    if not email:
        return None, MESSAGES["email_required"]
    if len(email) > EMAIL_MAX:
        return None, MESSAGES["email_too_long"]
    if not _EMAIL_PATTERN.match(email) or ".." in email:
        return None, MESSAGES["email_format"]

    local, _, domain = email.rpartition("@")
    if (
        len(local) > EMAIL_LOCAL_MAX
        or local.startswith(".")
        or local.endswith(".")
        or domain.startswith((".", "-"))
        or domain.endswith((".", "-"))
    ):
        return None, MESSAGES["email_format"]
    return email, None


def _validate_password(raw: Any) -> tuple[str | None, str | None]:
    if raw is None or raw == "":
        return None, MESSAGES["password_required"]
    if not isinstance(raw, str):
        return None, MESSAGES["password_type"]
    # Không strip: khoảng trắng đầu/cuối là một phần hợp lệ của mật khẩu.
    if len(raw) < PASSWORD_MIN:
        return None, MESSAGES["password_too_short"]
    if len(raw) > PASSWORD_MAX:
        return None, MESSAGES["password_too_long"]
    return raw, None


def validate_register_input(body: Any) -> RegisterValidation:
    """Kiểm tra body đăng ký (đã parse từ JSON). Không bao giờ ném lỗi vì dữ liệu sai."""
    if not isinstance(body, dict):
        return RegisterValidation(valid=False, errors={"body": MESSAGES["body"]})

    errors: dict[str, str] = {}
    name, name_error = _validate_name(body.get("name"))
    email, email_error = _validate_email(body.get("email"))
    password, password_error = _validate_password(body.get("password"))

    if name_error:
        errors["name"] = name_error
    if email_error:
        errors["email"] = email_error
    if password_error:
        errors["password"] = password_error

    confirm = body.get("confirmPassword")
    if confirm is None or confirm == "":
        errors["confirmPassword"] = MESSAGES["confirm_required"]
    elif not isinstance(confirm, str):
        errors["confirmPassword"] = MESSAGES["confirm_type"]
    elif isinstance(body.get("password"), str) and confirm != body["password"]:
        errors["confirmPassword"] = MESSAGES["confirm_mismatch"]

    # Chỉ chấp nhận đúng boolean True, không coi "true", 1, "on" là đồng ý.
    if body.get("consent") is not True:
        errors["consent"] = MESSAGES["consent_required"]

    if errors:
        return RegisterValidation(valid=False, errors=errors)
    assert name is not None and email is not None and password is not None
    return RegisterValidation(
        valid=True,
        value=RegisterData(name=name, email=email, password=password),
    )
