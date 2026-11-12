from collections.abc import Iterator

from fastapi import Request
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from app.config import load_database_url, normalize_database_url


def create_database_engine(database_url: str) -> Engine:
    url = make_url(normalize_database_url(database_url))
    if url.drivername != "mysql+pymysql":
        raise ValueError("DATABASE_URL phải dùng MySQL: mysql+pymysql://...")
    url = url.update_query_dict({"charset": "utf8mb4"})
    database_engine = create_engine(
        url,
        pool_pre_ping=True,
        pool_recycle=3600,
        connect_args={
            "init_command": "SET time_zone = '+00:00'",
            "connect_timeout": 5,
            "read_timeout": 10,
            "write_timeout": 10,
        },
    )
    if any(key in url.query for key in ("ssl_ca", "ssl_capath", "ssl_check_hostname")):
        @event.listens_for(database_engine, "connect")
        def require_encrypted_connection(connection, connection_record):
            if not connection._secure:
                raise SQLAlchemyError("MySQL chưa thiết lập kết nối TLS.")
    return database_engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


# Tạo engine/session factory chưa mở kết nối; schema được quản lý bằng Alembic.
engine = create_database_engine(load_database_url())
SessionLocal = create_session_factory(engine)


def get_db(request: Request) -> Iterator[Session]:
    session_factory = request.app.state.session_factory
    with session_factory() as db:
        with db.begin():
            yield db
