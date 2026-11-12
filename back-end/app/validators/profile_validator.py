"""Kiểm tra các trường được phép chỉnh sửa trong hồ sơ cá nhân."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.validators.register_validator import _validate_name


@dataclass(frozen=True)
class ProfileData:
    name: str | None = None
    birth_year: int | None = None
    update_birth_year: bool = False


@dataclass(frozen=True)
class ProfileValidation:
    valid: bool
    errors: dict[str, str] = field(default_factory=dict)
    value: ProfileData | None = None


def validate_profile_input(body: Any) -> ProfileValidation:
    if not isinstance(body, dict) or not body:
        return ProfileValidation(False, {"body": "Vui lòng gửi họ tên hoặc năm sinh cần cập nhật."})

    errors: dict[str, str] = {}
    if set(body) - {"name", "birthYear"}:
        errors["body"] = "Chỉ được cập nhật họ tên và năm sinh."
    name = None
    if "name" in body:
        name, name_error = _validate_name(body["name"])
        if name_error:
            errors["name"] = name_error
        elif name is not None:
            # JSON có thể chứa surrogate đơn lẻ, không thể lưu/hiển thị bằng UTF-8.
            try:
                name.encode("utf-8")
            except UnicodeEncodeError:
                errors["name"] = "Họ tên chứa ký tự không hợp lệ."

    birth_year = body.get("birthYear")
    if birth_year is not None:
        current_year = datetime.now(timezone.utc).year
        if type(birth_year) is not int or not 1900 <= birth_year <= current_year:
            errors["birthYear"] = f"Năm sinh phải là số nguyên từ 1900 đến {current_year}."

    if errors:
        return ProfileValidation(False, errors)
    return ProfileValidation(
        True,
        value=ProfileData(name=name, birth_year=birth_year, update_birth_year="birthYear" in body),
    )
