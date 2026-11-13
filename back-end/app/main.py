"""Điểm vào của ứng dụng FastAPI.

Chạy phát triển (từ thư mục back-end/)::

    uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Callable, Sequence

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.config import DEFAULT_UPLOAD_BODY_BYTES, Settings, load_settings
from app.db.database import create_database_engine, create_session_factory
from app.dependencies.auth import require_roles
from app.error_handlers import register_error_handlers
from app.middlewares.body_limit import BodySizeLimitMiddleware
from app.middlewares.security_headers import SecurityHeadersMiddleware
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.chat_repository import ChatRepository, InMemoryChatRepository
from app.repositories.sqlalchemy_chat_repository import SqlAlchemyChatRepository
from app.repositories.sqlalchemy_catalog_repository import SqlAlchemyCatalogRepository
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.repositories.document_repository import DocumentRepository, SqlAlchemyDocumentRepository
from app.repositories.user_repository import User
from app.routes.auth import router as auth_router
from app.routes.admin_catalog import router as admin_catalog_router
from app.routes.catalog import router as catalog_router
from app.routes.chat import router as chat_router
from app.routes.me import router as me_router
from app.routes.profile import router as profile_router
from app.routes.documents import router as documents_router
from app.services.auth_service import AuthService, UserRepository
from app.services.admin_catalog_service import AdminCatalogService
from app.services.catalog_service import CatalogRepository, CatalogService
from app.services.chat_service import ChatService
from app.services.llm_client import ChatCompletionsClient, LLMClient
from app.services.token_service import TokenService
from app.utils.password import hash_password
from app.utils.errors import AppError


def create_app(
    *,
    user_repository: UserRepository | None = None,
    catalog_repository: CatalogRepository | None = None,
    password_hasher: Callable[[str], str] | None = None,
    token_service: TokenService | None = None,
    cors_origins: Sequence[str] | None = None,
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    document_repository: DocumentRepository | None = None,
    upload_dir: Path | str | None = None,
    chat_repository: ChatRepository | None = None,
    llm_client: LLMClient | None = None,
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

    catalog = catalog_repository
    if catalog is None:
        catalog = (
            SqlAlchemyCatalogRepository(session_factory)
            if session_factory is not None
            else InMemoryCatalogRepository()
        )

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
    app.state.document_repository = document_repository
    if document_repository is None and session_factory is not None:
        app.state.document_repository = SqlAlchemyDocumentRepository(session_factory)
    app.state.upload_dir = Path(upload_dir) if upload_dir is not None else settings.upload_dir
    app.state.auth_service = AuthService(repository, password_hasher or hash_password)
    app.state.catalog_service = CatalogService(catalog)
    app.state.admin_catalog_service = AdminCatalogService(catalog)
    chat = chat_repository
    if chat is None:
        chat = (
            SqlAlchemyChatRepository(session_factory) if session_factory is not None
            else InMemoryChatRepository(catalog if isinstance(catalog, InMemoryCatalogRepository) else None)
        )
    app.state.chat_service = ChatService(chat, llm_client or ChatCompletionsClient(settings), settings)
    app.state.token_service = token_service or TokenService(
        secret=settings.jwt_secret,
        issuer=settings.jwt_issuer,
        access_token_minutes=settings.access_token_minutes,
    )

    register_error_handlers(app)
    app.include_router(auth_router)
    app.include_router(me_router)
    app.include_router(catalog_router)
    app.include_router(chat_router)
    app.include_router(admin_catalog_router)
    app.include_router(profile_router)
    app.include_router(documents_router)

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
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.max_body_bytes,
        upload_max_bytes=DEFAULT_UPLOAD_BODY_BYTES,
    )
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
        max_age=600,
    )
    return app


app = create_app()
