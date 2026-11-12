"""Cấu hình đọc từ biến môi trường, có giá trị mặc định cho môi trường phát triển."""

from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import make_url

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

logger = logging.getLogger(__name__)

# Front-end dev server (front-end/serve.cjs) chạy ở cổng 4173.
DEFAULT_CORS_ORIGINS = ("http://127.0.0.1:4173", "http://localhost:4173")
DEFAULT_MAX_BODY_BYTES = 10 * 1024
DEFAULT_ACCESS_TOKEN_MINUTES = 30
DEFAULT_DATABASE_URL = (
    "mysql+pymysql://gia_su_ai:gia_su_ai_dev@localhost:3306/gia_su_ai?charset=utf8mb4"
)
JWT_SECRET_MIN_LENGTH = 32  # HS256 cần khóa tối thiểu 256 bit


def _random_secret() -> str:
    return secrets.token_urlsafe(48)


@dataclass(frozen=True)
class Settings:
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    max_body_bytes: int = DEFAULT_MAX_BODY_BYTES
    # Mặc định là khóa ngẫu nhiên mỗi lần tạo Settings: an toàn nhưng token mất hiệu lực
    # khi khởi động lại. Môi trường thật phải đặt biến JWT_SECRET.
    jwt_secret: str = field(default_factory=_random_secret, repr=False)
    jwt_issuer: str = "gia-su-ai"
    access_token_minutes: int = DEFAULT_ACCESS_TOKEN_MINUTES
    database_url: str = field(default=DEFAULT_DATABASE_URL, repr=False)


def _load_jwt_secret() -> str:
    secret = os.environ.get("JWT_SECRET", "").strip()
    if not secret:
        logger.warning(
            "Chưa đặt JWT_SECRET: dùng khóa ngẫu nhiên, token sẽ mất hiệu lực khi khởi động lại "
            "và không dùng được khi chạy nhiều worker. Hãy đặt JWT_SECRET (từ %d ký tự) "
            "khi chạy thật.",
            JWT_SECRET_MIN_LENGTH,
        )
        return _random_secret()
    if len(secret) < JWT_SECRET_MIN_LENGTH:
        raise ValueError(f"JWT_SECRET phải có ít nhất {JWT_SECRET_MIN_LENGTH} ký tự.")
    return secret


def _load_access_token_minutes() -> int:
    raw = os.environ.get("ACCESS_TOKEN_MINUTES", "").strip()
    if not raw:
        return DEFAULT_ACCESS_TOKEN_MINUTES
    try:
        minutes = int(raw)
    except ValueError:
        raise ValueError("ACCESS_TOKEN_MINUTES phải là số nguyên dương.") from None
    if minutes <= 0:
        raise ValueError("ACCESS_TOKEN_MINUTES phải là số nguyên dương.")
    return minutes


def normalize_database_url(database_url: str) -> str:
    url = make_url(database_url)
    if url.drivername == "mysql":
        url = url.set(drivername="mysql+pymysql")
    query = dict(url.query)
    ssl_mode = query.pop("ssl-mode", query.pop("ssl_mode", None))
    if ssl_mode is not None:
        if not isinstance(ssl_mode, str):
            raise ValueError("ssl-mode chỉ được cấu hình một lần.")
        mode = ssl_mode.upper()
        if mode in {"REQUIRED", "PREFERRED"}:
            query.setdefault("ssl_check_hostname", "false")
        elif mode in {"VERIFY_CA", "VERIFY_IDENTITY"}:
            if not (query.get("ssl_ca") or query.get("ssl_capath")):
                raise ValueError("Cần ssl_ca hoặc ssl_capath khi kiểm tra chứng chỉ MySQL.")
            query["ssl_check_hostname"] = "true" if mode == "VERIFY_IDENTITY" else "false"
        elif mode == "DISABLED":
            query["ssl_disabled"] = "true"
        else:
            raise ValueError("ssl-mode MySQL chưa được hỗ trợ.")
    return url.set(query=query).render_as_string(hide_password=False)


def load_database_url() -> str:
    database_url = os.environ.get("DATABASE_URL", "").strip() or DEFAULT_DATABASE_URL
    return normalize_database_url(database_url)


def load_settings() -> Settings:
    raw = os.environ.get("CORS_ORIGIN", "")
    origins = tuple(item.strip() for item in raw.split(",") if item.strip())
    return Settings(
        cors_origins=origins or DEFAULT_CORS_ORIGINS,
        jwt_secret=_load_jwt_secret(),
        access_token_minutes=_load_access_token_minutes(),
        database_url=load_database_url(),
    )
