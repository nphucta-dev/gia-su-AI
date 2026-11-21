"""Dữ liệu mẫu: python -m app.db.seed [--admin]."""

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from getpass import getpass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import BACKEND_DIR, DEFAULT_UPLOAD_DIR
from app.db.database import SessionLocal, engine
from app.models import Document, DocumentChunk, Subject, Topic, User, UserRole
from app.services.document_text import extract_document_text, split_document_text
from app.utils.password import hash_password
from app.validators.register_validator import validate_register_input

SAMPLE_SUBJECTS = (
    ("Toán", "THPT", (
        ("Hàm số", "Hàm số bậc hai"), ("Đại số", "Phương trình bậc hai"),
        ("Đại số", "Bất phương trình bậc nhất"), ("Hình học", "Định lý Pythagore"),
        ("Xác suất", "Xác suất cổ điển"),
    )),
    ("Vật lí", "THPT", (
        ("Cơ học", "Chuyển động thẳng đều"), ("Cơ học", "Chuyển động thẳng biến đổi đều"),
        ("Cơ học", "Định luật II Newton"), ("Cơ học", "Công và công suất"),
        ("Điện học", "Định luật Ohm"),
    )),
)
DEMO_DOCUMENT_DIR = Path(__file__).with_name("demo_documents")

SAMPLE_USERS = (
    {
        "full_name": "Người học mẫu",
        "email": "learner@example.com",
        "password": "Learner@123",
        "role": UserRole.LEARNER.value,
    },
    {
        "full_name": "Quản trị viên mẫu",
        "email": "admin@example.com",
        "password": "Admin@123",
        "role": UserRole.ADMIN.value,
    },
)


def _load_demo_documents() -> list[dict]:
    """Validate all bundled sources before adding any database records."""
    expected = {
        (subject, grade, chapter, topic)
        for subject, grade, topics in SAMPLE_SUBJECTS for chapter, topic in topics
    }
    seen_topics, seen_files = set(), set()
    documents = []
    manifest = json.loads((DEMO_DOCUMENT_DIR / "manifest.json").read_text(encoding="utf-8"))
    for item in manifest:
        key = (item["subject"], item["grade_level"], item["chapter_name"], item["topic_name"])
        name = item["file_name"]
        if key not in expected or key in seen_topics or name in seen_files:
            raise ValueError("Danh mục tài liệu demo bị trùng hoặc không khớp chủ đề.")
        if Path(name).name != name or Path(name).suffix != ".txt" or "\\" in name:
            raise ValueError("Đường dẫn tài liệu demo không hợp lệ.")
        source = DEMO_DOCUMENT_DIR / name
        if source.is_symlink() or source.resolve().parent != DEMO_DOCUMENT_DIR.resolve():
            raise ValueError("Tài liệu demo phải nằm trong thư mục nguồn.")
        title = item["title"]
        if not isinstance(title, str) or not title.strip() or len(title) > 200:
            raise ValueError("Tiêu đề tài liệu demo không hợp lệ.")
        chunks = split_document_text(extract_document_text(source))
        documents.append({**item, "key": key, "payload": source.read_bytes(), "chunks": chunks})
        seen_topics.add(key)
        seen_files.add(name)
    if seen_topics != expected:
        raise ValueError("Mỗi chủ đề demo phải có đúng một tài liệu nguồn.")
    return documents


def _seed_documents(db: Session, topics: dict, documents: list[dict], upload_dir: Path) -> None:
    created_files = []
    try:
        for source in documents:
            storage_name = "demo-" + source["file_name"]
            # Stable identity: changing a document's title/status in ADMIN does not
            # make a repeated seed add another document or re-enable that source.
            existing = db.scalar(select(Document).where(
                Document.topic_id == topics[source["key"]], Document.file_path == storage_name,
            ))
            if existing is not None:
                continue
            destination = upload_dir / storage_name
            upload_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            try:
                with destination.open("xb") as output:
                    created_files.append(destination)
                    output.write(source["payload"])
            except FileExistsError:
                if destination.is_symlink() or not destination.is_file() or destination.read_bytes() != source["payload"]:
                    raise ValueError("Tệp demo đã tồn tại với nội dung khác; seed không ghi đè.") from None
            document = Document(
                topic_id=topics[source["key"]], title=source["title"], file_path=storage_name,
                source_url=None, status="ready", is_active=True, processed_at=datetime.now(timezone.utc),
            )
            db.add(document)
            db.flush()
            db.add_all([
                DocumentChunk(document_id=document.id, chunk_index=index, content=content)
                for index, content in enumerate(source["chunks"])
            ])
            db.flush()
    except Exception:
        # Only remove files created in this call, never a pre-existing upload.
        for path in created_files:
            path.unlink(missing_ok=True)
        raise


def _seed_user(
    db: Session,
    *,
    full_name: str,
    email: str | None,
    password: str | None,
    role: str,
) -> None:
    result = validate_register_input(
        {
            "name": full_name,
            "email": email,
            "password": password,
            "confirmPassword": password,
            "consent": True,
        }
    )
    if not result.valid:
        raise ValueError(f"Thông tin {role} chưa hợp lệ: " + "; ".join(result.errors.values()))

    data = result.value
    assert data is not None
    user = db.scalar(select(User).where(User.email == data.email))
    if user is not None:
        if user.role != role:
            raise ValueError(
                f"Email {data.email} đã thuộc tài khoản có vai trò khác. Hãy dùng email khác."
            )
        return

    db.add(
        User(
            full_name=data.name,
            email=data.email,
            password_hash=hash_password(data.password),
            role=role,
        )
    )
    db.flush()


def seed_data(
    db: Session,
    *,
    admin_email: str | None = None,
    admin_password: str | None = None,
    upload_dir: Path | None = None,
) -> None:
    documents = _load_demo_documents()
    storage = Path(upload_dir) if upload_dir is not None else Path(os.environ.get("UPLOAD_DIR", "").strip() or DEFAULT_UPLOAD_DIR).expanduser()
    if not storage.is_absolute():
        storage = BACKEND_DIR / storage
    storage = storage.resolve()
    topic_ids = {}
    for subject_name, grade_level, topics in SAMPLE_SUBJECTS:
        subject = db.scalar(
            select(Subject).where(Subject.name == subject_name, Subject.grade_level == grade_level)
        )
        if subject is None:
            subject = Subject(name=subject_name, grade_level=grade_level)
            db.add(subject)
            db.flush()

        for chapter_name, topic_name in topics:
            topic = db.scalar(
                select(Topic).where(
                    Topic.subject_id == subject.id,
                    Topic.chapter_name == chapter_name,
                    Topic.name == topic_name,
                )
            )
            if topic is None:
                topic = Topic(subject_id=subject.id, chapter_name=chapter_name, name=topic_name)
                db.add(topic)
                db.flush()
            topic_ids[(subject_name, grade_level, chapter_name, topic_name)] = topic.id

    # Seed ADMIN tự nhập trước để ưu tiên mật khẩu này nếu trùng email ADMIN mẫu.
    if admin_email is not None or admin_password is not None:
        _seed_user(
            db,
            full_name="Quản trị viên",
            email=admin_email,
            password=admin_password,
            role=UserRole.ADMIN.value,
        )

    for user_data in SAMPLE_USERS:
        _seed_user(db, **user_data)
    _seed_documents(db, topic_ids, documents, storage)


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed 2 môn, 10 chủ đề, tài liệu nguồn và tài khoản LEARNER, ADMIN mẫu.")
    parser.add_argument("--admin", action="store_true", help="Thêm ADMIN bằng thông tin tự nhập.")
    args = parser.parse_args()

    admin_email = None
    admin_password = None
    if args.admin:
        admin_email = os.environ.get("SEED_ADMIN_EMAIL", "").strip() or input("Email ADMIN: ")
        admin_password = os.environ.get("SEED_ADMIN_PASSWORD", "") or getpass("Mật khẩu ADMIN: ")

    try:
        with SessionLocal.begin() as db:
            seed_data(db, admin_email=admin_email, admin_password=admin_password)
    finally:
        engine.dispose()
    print("Đã seed dữ liệu thành công. Các bản ghi đã tồn tại được giữ nguyên.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
