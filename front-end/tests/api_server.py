"""API riêng cho browser test, chỉ sử dụng dữ liệu trong bộ nhớ."""

import argparse
import json
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path

os.environ["PYTHON_DOTENV_DISABLED"] = "1"
os.environ["DATABASE_URL"] = "mysql+pymysql://browser:browser@127.0.0.1/browser_tests"
os.environ["JWT_SECRET"] = "browser-test-only-key-" + "x" * 48
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "back-end"))

import uvicorn

from app.config import Settings
from app.main import create_app
from app.repositories.catalog_repository import InMemoryCatalogRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.repositories.document_repository import InMemoryDocumentRepository, SubjectRecord, TopicRecord
from app.utils.password import hash_password
from app.services.llm_client import LLMReply
from app.utils.errors import AppError


class BrowserModel:
    """Deterministic provider used only by the isolated browser test server."""

    def __init__(self):
        self.failed_questions = set()

    async def generate(self, messages):
        if messages[0]["content"].startswith("Bạn là giáo viên tạo bài luyện tập"):
            return LLMReply(json.dumps({"questions": [{
                "question_text": f"Câu {index}: Một cộng một bằng bao nhiêu?",
                "options": {"A": "Một", "B": "Hai", "C": "Ba", "D": "Bốn"},
                "correct_answer": "B", "explanation": "Một cộng một bằng hai.",
            } for index in range(1, 6)]}, ensure_ascii=False))
        text = json.dumps(messages, ensure_ascii=False)
        if "RETRY_ONCE" in text and "RETRY_ONCE" not in self.failed_questions:
            self.failed_questions.add("RETRY_ONCE")
            raise AppError(503, "LLM_UNAVAILABLE", "Model kiểm thử tạm thời chưa phản hồi.")
        return LLMReply("Bạn thử xác định dữ kiện đã biết rồi chọn bước giải tiếp theo nhé.", token_count=12)


def fast_hasher(password: str) -> str:
    return hash_password(password, n=1024, r=8, p=1)


def create_browser_app():
    repository = InMemoryUserRepository()
    catalog = InMemoryCatalogRepository()
    toan = catalog.add_subject("Toán học", "THPT")
    quadratic = catalog.add_topic(toan, "Chương 1 · Đại số", "Phương trình bậc hai", "Biệt thức, nghiệm và hệ thức Viète.")
    functions = catalog.add_topic(toan, "Chương 1 · Đại số", "Hàm số và đồ thị", "Khảo sát hàm số và đọc đồ thị.")
    lower_math = catalog.add_subject("Toán học", "THCS")
    fractions = catalog.add_topic(lower_math, "Số học", "Phép cộng phân số", "Quy đồng mẫu số và cộng phân số.")
    catalog.add_topic(lower_math, "Số học", "Chủ đề đã tắt", is_active=False)
    hidden = catalog.add_subject("Môn học đã tắt", "THCS", is_active=False)
    catalog.add_topic(hidden, "Chương 1", "Chủ đề thuộc môn đã tắt")
    documents = InMemoryDocumentRepository(
        subjects=[
            SubjectRecord(id=toan, name="Toán học", grade_level="THPT"),
            SubjectRecord(id=lower_math, name="Toán học", grade_level="THCS"),
        ],
        topics=[
            TopicRecord(id=quadratic, subject_id=toan, name="Phương trình bậc hai", chapter_name="Chương 1 · Đại số"),
            TopicRecord(id=functions, subject_id=toan, name="Hàm số và đồ thị", chapter_name="Chương 1 · Đại số"),
            TopicRecord(id=fractions, subject_id=lower_math, name="Phép cộng phân số", chapter_name="Số học"),
        ],
    )
    app = create_app(
        user_repository=repository,
        catalog_repository=catalog,
        password_hasher=fast_hasher,
        settings=Settings(jwt_secret=os.environ["JWT_SECRET"]),
        document_repository=documents,
        llm_client=BrowserModel(),
        upload_dir=Path(os.environ["BROWSER_UPLOAD_DIR"]),
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
        # Mô phỏng tài liệu đã upload trước khi có tính năng trích văn bản.
        storage = Path(os.environ["BROWSER_UPLOAD_DIR"])
        storage.mkdir(parents=True, exist_ok=True)
        (storage / "pending-source.txt").write_text("Nội dung tài liệu chờ xử lý. Hàm số bậc hai.", encoding="utf-8")
        await documents.create(topic_id=quadratic, title="Tài liệu chờ xử lý", file_path="pending-source.txt")
        source = await documents.create(topic_id=quadratic, title="Nguồn Đại số kiểm thử", file_path="ai-source.txt")
        await documents.finish_processing(source.id, chunks=["Phương trình bậc hai có dạng ax² + bx + c = 0. Biệt thức delta giúp xét nghiệm."])
        documents._documents[source.id] = replace(documents._documents[source.id], is_active=True)
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
