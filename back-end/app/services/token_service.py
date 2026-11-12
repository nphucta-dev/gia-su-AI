"""Tạo và kiểm tra access token JWT (HS256).

Token chỉ chứa định danh người dùng (``sub`` = id), thời điểm phát hành/hết hạn và
loại token. Vai trò và trạng thái tài khoản KHÔNG nằm trong token mà được đọc lại
từ kho dữ liệu ở mỗi request, nên đổi vai trò hay xoá tài khoản có hiệu lực ngay.

Chống các lỗi hay gặp:
- Chỉ chấp nhận đúng thuật toán đã cấu hình, token ``alg: none`` hay đổi thuật toán đều bị từ chối.
- Bắt buộc có ``exp``, ``iat``, ``sub``, ``iss``; kiểm tra ``iss`` và loại token ``access``.
- Giới hạn độ dài token trước khi giải mã.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt

from app.utils.errors import AppError

TOKEN_TYPE_ACCESS = "access"
MAX_TOKEN_LENGTH = 2048
MIN_SECRET_LENGTH = 32

MESSAGES = {
    "not_authenticated": "Vui lòng đăng nhập để tiếp tục.",
    "token_expired": "Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
    "invalid_token": "Phiên đăng nhập không hợp lệ. Vui lòng đăng nhập lại.",
}


@dataclass(frozen=True)
class IssuedToken:
    access_token: str
    token_type: str
    expires_in: int  # số giây còn hiệu lực


@dataclass(frozen=True)
class TokenPayload:
    user_id: str
    issued_at: datetime
    expires_at: datetime


def not_authenticated_error() -> AppError:
    """Request không gửi token."""
    return AppError(
        401,
        "NOT_AUTHENTICATED",
        MESSAGES["not_authenticated"],
        headers={"WWW-Authenticate": "Bearer"},
    )


def invalid_token_error() -> AppError:
    return AppError(
        401,
        "INVALID_TOKEN",
        MESSAGES["invalid_token"],
        headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
    )


def expired_token_error() -> AppError:
    return AppError(
        401,
        "TOKEN_EXPIRED",
        MESSAGES["token_expired"],
        headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="token expired"'},
    )


class TokenService:
    def __init__(
        self,
        *,
        secret: str,
        algorithm: str = "HS256",
        issuer: str = "gia-su-ai",
        access_token_minutes: int = 30,
    ) -> None:
        if not isinstance(secret, str) or len(secret) < MIN_SECRET_LENGTH:
            raise ValueError(f"Khóa ký token phải có ít nhất {MIN_SECRET_LENGTH} ký tự.")
        if access_token_minutes <= 0:
            raise ValueError("Thời hạn token phải lớn hơn 0.")
        self._secret = secret
        self._algorithm = algorithm
        self._issuer = issuer
        self._access_token_lifetime = timedelta(minutes=access_token_minutes)

    def create_access_token(self, user_id: int | str, *, expires_delta: timedelta | None = None) -> IssuedToken:
        """Phát hành access token cho người dùng (API đăng nhập sẽ gọi hàm này).

        ``expires_delta`` chủ yếu để test token hết hạn; bình thường dùng thời hạn cấu hình.
        """
        if isinstance(user_id, bool):
            raise ValueError("user_id phải là số nguyên dương hoặc chuỗi không rỗng.")
        if isinstance(user_id, int):
            if user_id <= 0:
                raise ValueError("user_id phải là số nguyên dương.")
            user_id = str(user_id)
        if not isinstance(user_id, str) or not user_id:
            raise ValueError("user_id phải là số nguyên dương hoặc chuỗi không rỗng.")
        lifetime = expires_delta if expires_delta is not None else self._access_token_lifetime
        # jwt lưu thời điểm theo giây; bỏ phần micro giây để giá trị trong token và giá trị trả về khớp nhau.
        now = datetime.now(timezone.utc).replace(microsecond=0)
        claims = {
            "sub": user_id,
            "type": TOKEN_TYPE_ACCESS,
            "iss": self._issuer,
            "iat": now,
            "exp": now + lifetime,
        }
        token = jwt.encode(claims, self._secret, algorithm=self._algorithm)
        return IssuedToken(access_token=token, token_type="Bearer", expires_in=int(lifetime.total_seconds()))

    def verify_access_token(self, token: str) -> TokenPayload:
        """Kiểm tra token và trả về nội dung đã xác thực.

        Raises:
            AppError: 401 ``TOKEN_EXPIRED`` khi hết hạn, 401 ``INVALID_TOKEN`` với mọi lỗi khác
                (sai chữ ký, sai định dạng, sai loại, thiếu claim...). Thông báo không tiết lộ
                nguyên nhân cụ thể.
        """
        if not isinstance(token, str) or not token or len(token) > MAX_TOKEN_LENGTH:
            raise invalid_token_error()
        try:
            claims = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                issuer=self._issuer,
                options={"require": ["exp", "iat", "sub", "iss"]},
            )
        except jwt.ExpiredSignatureError:
            raise expired_token_error() from None
        except jwt.PyJWTError:
            raise invalid_token_error() from None

        user_id = claims.get("sub")
        if claims.get("type") != TOKEN_TYPE_ACCESS or not isinstance(user_id, str) or not user_id:
            raise invalid_token_error()
        return TokenPayload(
            user_id=user_id,
            issued_at=datetime.fromtimestamp(claims["iat"], tz=timezone.utc),
            expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        )
