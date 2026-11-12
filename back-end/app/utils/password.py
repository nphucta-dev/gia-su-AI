"""Băm và kiểm tra mật khẩu bằng scrypt (``hashlib.scrypt`` có sẵn trong Python,
không cần cài thêm thư viện).

Định dạng chuỗi lưu trong CSDL (một cột duy nhất)::

    scrypt$<N>$<r>$<p>$<salt base64>$<hash base64>

Tham số được lưu cùng hash nên sau này có thể tăng độ khó mà vẫn kiểm tra được
mật khẩu cũ (xem :func:`needs_rehash`).
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import unicodedata
from dataclasses import dataclass

ALGORITHM = "scrypt"
KEY_LENGTH = 64
SALT_LENGTH = 16
MAX_PASSWORD_LENGTH = 128


@dataclass(frozen=True)
class ScryptParams:
    n: int
    r: int
    p: int


# Cấu hình theo khuyến nghị OWASP: N=2^15, r=8, p=3 (~32 MiB bộ nhớ mỗi lần băm).
DEFAULT_PARAMS = ScryptParams(n=2**15, r=8, p=3)

# Giới hạn khi ĐỌC tham số từ chuỗi đã lưu, tránh hash bị sửa làm cạn bộ nhớ/CPU.
_MAX_N = 2**20
_MAX_R = 32
_MAX_P = 16
_MAX_MEMORY = 256 * 1024 * 1024  # 128 * N * r không được vượt 256 MiB


def _memory_for(n: int, r: int) -> int:
    # scrypt cần khoảng 128 * N * r byte; chừa thêm dư địa để không vượt maxmem của OpenSSL.
    return 128 * n * r * 2 + 1024 * 1024


def _normalize(password: str) -> bytes:
    # NFKC để cùng một mật khẩu gõ bằng các dạng Unicode khác nhau vẫn khớp nhau.
    return unicodedata.normalize("NFKC", password).encode("utf-8")


def _derive(password: str, salt: bytes, n: int, r: int, p: int, length: int) -> bytes:
    return hashlib.scrypt(
        _normalize(password),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=_memory_for(n, r),
        dklen=length,
    )


def _check_password_input(password: object) -> None:
    if not isinstance(password, str) or password == "":
        raise TypeError("Mật khẩu phải là chuỗi không rỗng.")
    if len(password) > MAX_PASSWORD_LENGTH:
        raise ValueError(f"Mật khẩu tối đa {MAX_PASSWORD_LENGTH} ký tự.")


def hash_password(
    password: str,
    *,
    n: int = DEFAULT_PARAMS.n,
    r: int = DEFAULT_PARAMS.r,
    p: int = DEFAULT_PARAMS.p,
) -> str:
    """Băm mật khẩu với salt ngẫu nhiên.

    ``n``, ``r``, ``p`` chủ yếu để test chạy nhanh; production dùng giá trị mặc định.
    Hàm này tốn CPU và chạy đồng bộ; trong code async hãy gọi qua thread pool.

    Raises:
        TypeError: mật khẩu không phải chuỗi hoặc rỗng.
        ValueError: mật khẩu dài quá giới hạn.
    """
    _check_password_input(password)
    salt = secrets.token_bytes(SALT_LENGTH)
    derived = _derive(password, salt, n, r, p, KEY_LENGTH)
    return "$".join(
        [
            ALGORITHM,
            str(n),
            str(r),
            str(p),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(derived).decode("ascii"),
        ]
    )


@dataclass(frozen=True)
class _ParsedHash:
    n: int
    r: int
    p: int
    salt: bytes
    digest: bytes


def _is_power_of_two(value: int) -> bool:
    return value > 1 and (value & (value - 1)) == 0


def _parse_hash(stored: object) -> _ParsedHash | None:
    if not isinstance(stored, str):
        return None
    parts = stored.split("$")
    if len(parts) != 6 or parts[0] != ALGORITHM:
        return None
    try:
        n, r, p = int(parts[1]), int(parts[2]), int(parts[3])
        salt = base64.b64decode(parts[4], validate=True)
        digest = base64.b64decode(parts[5], validate=True)
    except (ValueError, binascii.Error):
        return None

    if not _is_power_of_two(n) or n > _MAX_N:
        return None
    if not 1 <= r <= _MAX_R or not 1 <= p <= _MAX_P:
        return None
    if 128 * n * r > _MAX_MEMORY:
        return None
    if not salt or not digest:
        return None
    return _ParsedHash(n=n, r=r, p=p, salt=salt, digest=digest)


def verify_password(password: object, stored: object) -> bool:
    """Kiểm tra mật khẩu với chuỗi hash đã lưu.

    Không bao giờ ném lỗi vì dữ liệu sai: mật khẩu sai, hash hỏng hoặc kiểu dữ
    liệu lạ đều trả về ``False``.
    """
    if not isinstance(password, str) or password == "" or len(password) > MAX_PASSWORD_LENGTH:
        return False
    parsed = _parse_hash(stored)
    if parsed is None:
        return False
    try:
        derived = _derive(password, parsed.salt, parsed.n, parsed.r, parsed.p, len(parsed.digest))
    except (ValueError, MemoryError):
        return False
    # So sánh thời gian cố định, tránh lộ thông tin qua timing.
    return hmac.compare_digest(derived, parsed.digest)


def needs_rehash(stored: object) -> bool:
    """Hash cũ có dùng tham số yếu hơn cấu hình hiện tại không?

    Dùng sau khi đăng nhập thành công: nếu ``True`` thì băm lại và cập nhật CSDL.
    """
    parsed = _parse_hash(stored)
    if parsed is None:
        return True
    return (
        parsed.n < DEFAULT_PARAMS.n
        or parsed.r < DEFAULT_PARAMS.r
        or parsed.p < DEFAULT_PARAMS.p
        or len(parsed.digest) < KEY_LENGTH
    )
