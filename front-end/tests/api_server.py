"""API riêng cho browser test, chỉ sử dụng dữ liệu trong bộ nhớ."""

import argparse
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["DATABASE_URL"] = "mysql+pymysql://browser:browser@127.0.0.1/browser_tests"
os.environ["JWT_SECRET"] = "browser-test-only-key-" + "x" * 48
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "back-end"))

import uvicorn

from app.config import Settings
from app.main import create_app
from app.repositories.user_repository import InMemoryUserRepository
from app.utils.password import hash_password


def fast_hasher(password: str) -> str:
    return hash_password(password, n=1024, r=8, p=1)


def create_browser_app():
    repository = InMemoryUserRepository()
    app = create_app(
        user_repository=repository,
        password_hasher=fast_hasher,
        settings=Settings(jwt_secret=os.environ["JWT_SECRET"]),
    )
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(current_app):
        for email, name, role in (
            ("admin@example.com", "Browser Admin", "ADMIN"),
            ("learner@example.com", "Browser Learner", "LEARNER"),
        ):
            await repository.create(
                email=email,
                name=name,
                role=role,
                password_hash=fast_hasher("MatKhau@123"),
            )
        async with original_lifespan(current_app):
            yield

    app.router.lifespan_context = lifespan
    return app


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    arguments = parser.parse_args()
    uvicorn.run(
        create_browser_app(), host="127.0.0.1", port=arguments.port,
        log_level="warning", access_log=False,
    )
