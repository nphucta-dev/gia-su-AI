"""Tạo database nếu chưa có rồi chạy migration: python -m app.db.init_db."""

from pathlib import Path
import sys

from alembic import command
from alembic.config import Config
from sqlalchemy_utils import create_database, database_exists

from app.config import load_database_url
from app.db.database import create_database_engine

BACKEND_DIR = Path(__file__).resolve().parents[2]


def init_database(database_url: str | None = None) -> None:
    database_engine = create_database_engine(database_url or load_database_url())
    try:
        if not database_exists(database_engine.url):
            create_database(database_engine.url, encoding="utf8mb4")

        config = Config(str(BACKEND_DIR / "alembic.ini"))
        with database_engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
    finally:
        database_engine.dispose()


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    init_database()
    print("Đã khởi tạo database và cập nhật migration thành công.")
