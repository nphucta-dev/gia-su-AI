"""Điểm vào của ứng dụng FastAPI.

Chạy phát triển (từ thư mục back-end/)::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Annotated, Callable, Sequence

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings, load_settings
from app.db.database import create_database_engine, create_session_factory
from app.dependencies.auth import require_roles
from app.error_handlers import register_error_handlers
from app.middlewares.body_limit import BodySizeLimitMiddleware
from app.middlewares.security_headers import SecurityHeadersMiddleware
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.repositories.user_repository import User
from app.routes.auth import router as auth_router
from app.routes.me import router as me_router
from app.services.auth_service import AuthService, UserRepository
from app.services.token_service import TokenService
from app.utils.password import hash_password
from app.utils.errors import AppError


def create_app(
    *,
    user_repository: UserRepository | None = None,
    password_hasher: Callable[[str], str] | None = None,
    token_service: TokenService | None = None,
    cors_origins: Sequence[str] | None = None,
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> FastAPI:
    """Tạo ứng dụng. Các phụ thuộc được truyền vào để dễ thay kho dữ liệu (ví dụ CSDL
    thật) và để test độc lập, không cần mở cổng thật."""
    settings = settings or load_settings()
    origins = list(cors_origins) if cors_origins is not None else list(settings.cors_origins)

    database_engine = None
    repository = user_repository
    if repository is None:
        if session_factory is None:
            database_engine = create_database_engine(settings.database_url)
            session_factory = create_session_factory(database_engine)
        repository = SqlAlchemyUserRepository(session_factory)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            yield
        finally:
            if database_engine is not None:
                database_engine.dispose()

    app = FastAPI(title="Gia Sư AI API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.user_repository = repository
    app.state.auth_service = AuthService(repository, password_hasher or hash_password)
    app.state.token_service = token_service or TokenService(
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        access_token_minutes=settings.access_token_minutes,
    )

    register_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(me_router)

    @app.get("/api/health", tags=["system"])
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/database", tags=["system"], summary="Kiểm tra kết nối MySQL")
    def check_database(request: Request) -> dict[str, str]:
        factory = request.app.state.session_factory
        if factory is None:
            raise AppError(503, "DATABASE_UNAVAILABLE", "Chưa có kết nối database.")
        try:
            with factory() as db:
                db.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise AppError(
                503,
                "DATABASE_UNAVAILABLE",
                "Không thể kết nối database. Vui lòng kiểm tra cấu hình và dịch vụ MySQL.",
            ) from None
        return {"status": "ok", "database": "connected", "message": "Kết nối database thành công."}

    @app.get("/api/admin/access", tags=["admin"], summary="Kiểm tra quyền quản trị")
    async def admin_access(user: Annotated[User, Depends(require_roles("ADMIN"))]) -> dict[str, str]:
        return {"role": user.role, "message": "Bạn có quyền quản trị."}

    # Middleware thêm sau nằm ở ngoài: CORS ngoài cùng nên mọi phản hồi (kể cả 413) đều có header CORS.
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_body_bytes)
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=600,
    )
    return app


app = create_app()
