"""TK-095 runs against a disposable migrated MySQL database, never the project DB."""

import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import delete, func, select

from app.config import Settings
from app.db.base import Base
from app.db.seed import SAMPLE_USERS, seed_data
from app.main import create_app
from app.models import ChatMessage, ChatSession, Document, DocumentChunk, LearningProgress, Quiz, Subject, Topic, User
from app.services.document_text import extract_document_text, split_document_text
from app.utils.password import verify_password
from test_database_integration import database


SOURCE_DIR = Path(__file__).resolve().parents[1] / "app" / "db" / "demo_documents"


@pytest.fixture
def clean_seed_database(database):
    engine, sessions = database
    # This fixture only clears the random database created by the imported fixture.
    assert engine.url.database.startswith("gia_su_ai_test_")
    with sessions.begin() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(delete(table))
    return sessions


def snapshot(db):
    return {
        model.__tablename__: [tuple(getattr(row, column.name) for column in model.__table__.columns)
                              for row in db.scalars(select(model).order_by(model.id))]
        for model in (Subject, Topic, User, Document, DocumentChunk)
    }


@pytest.mark.anyio
async def test_seeded_catalog_accounts_documents_and_real_retrieval_are_usable(clean_seed_database, tmp_path):
    sessions = clean_seed_database
    with sessions.begin() as db:
        seed_data(db, upload_dir=tmp_path)
    rows = json.loads((SOURCE_DIR / "manifest.json").read_text(encoding="utf-8"))
    with sessions() as db:
        subjects = list(db.scalars(select(Subject)))
        assert len(subjects) == 2
        assert {subject.name: db.scalar(select(func.count()).select_from(Topic).where(Topic.subject_id == subject.id))
                for subject in subjects} == {"Toán": 5, "Vật lí": 5}
        documents = list(db.scalars(select(Document).order_by(Document.id)))
        assert len(documents) == 10 and len({doc.topic_id for doc in documents}) == 10
        for doc in documents:
            assert doc.status == "ready" and doc.is_active and doc.processed_at is not None
            assert doc.source_url is None  # Original bundled source, no fabricated remote citation.
            assert doc.file_path.startswith("demo-") and Path(doc.file_path).name == doc.file_path
            expected = next(row for row in rows if "demo-" + row["file_name"] == doc.file_path)
            assert (tmp_path / doc.file_path).read_bytes() == (SOURCE_DIR / expected["file_name"]).read_bytes()
            chunks = list(db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == doc.id).order_by(DocumentChunk.chunk_index)))
            assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
            assert [chunk.content for chunk in chunks] == split_document_text(extract_document_text(tmp_path / doc.file_path))
            assert chunks and all(chunk.embedding is None for chunk in chunks)
        for model in (ChatMessage, ChatSession, Quiz, LearningProgress):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        for sample in SAMPLE_USERS:
            user = db.scalar(select(User).where(User.email == sample["email"]))
            assert user is not None and user.role == sample["role"] and user.is_active
            assert user.password_hash != sample["password"] and verify_password(sample["password"], user.password_hash)
        admin_id = db.scalar(select(User.id).where(User.role == "ADMIN"))
        learner_id = db.scalar(select(User.id).where(User.role == "LEARNER"))
        topic_id = documents[0].topic_id
        query = db.get(Topic, topic_id).name

    app = create_app(session_factory=sessions, settings=Settings(jwt_secret="seed-demo-api-" + "x" * 40), upload_dir=tmp_path)
    def headers(user_id):
        return {"Authorization": "Bearer " + app.state.token_service.create_access_token(user_id).access_token}

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test") as client:
        catalog = await client.get("/api/catalog/subjects", headers=headers(learner_id))
        assert catalog.status_code == 200
        assert len(catalog.json()["subjects"]) == 2
        listed = await client.get("/api/admin/documents", headers=headers(admin_id))
        assert listed.status_code == 200 and len(listed.json()["documents"]) == 10
        assert all(doc["status"] == "ready" and doc["chunkCount"] > 0 and doc["sizeBytes"] > 0 for doc in listed.json()["documents"])
        assert (await client.get("/api/admin/documents", headers=headers(learner_id))).status_code == 403
        found = await app.state.document_retrieval_service.search(topic_id, query)
        assert found.matches and all(match.chunk.topic_id == topic_id for match in found.matches)


def test_repeated_seed_preserves_accounts_admin_choices_chunks_and_existing_files(clean_seed_database, tmp_path):
    sessions = clean_seed_database
    with sessions.begin() as db:
        seed_data(db, upload_dir=tmp_path)
        before = snapshot(db)
        contents = {path.name: path.read_bytes() for path in tmp_path.glob("*.txt")}
        seed_data(db, upload_dir=tmp_path)
        assert snapshot(db) == before
        assert {path.name: path.read_bytes() for path in tmp_path.glob("*.txt")} == contents
        user = db.scalar(select(User).where(User.email == "learner@example.com"))
        user.full_name, user.is_active = "Tên người học đã sửa", False
        subject = db.scalar(select(Subject).where(Subject.name == "Toán"))
        subject.is_active = False
        topic = db.scalar(select(Topic).where(Topic.subject_id == subject.id))
        topic.is_active = False
        doc = db.scalar(select(Document).where(Document.topic_id == topic.id))
        doc.title, doc.is_active = "Tiêu đề quản trị viên đã sửa", False
        chunk = db.scalar(select(DocumentChunk).where(DocumentChunk.document_id == doc.id))
        chunk.content = "Nội dung đã được quản trị viên hiệu đính."
        db.flush()
        modified = snapshot(db)
        seed_data(db, upload_dir=tmp_path)
        assert snapshot(db) == modified
        assert {path.name: path.read_bytes() for path in tmp_path.glob("*.txt")} == contents


def test_seed_file_collision_never_overwrites_existing_file_or_commits_partial_rows(clean_seed_database, tmp_path):
    sessions = clean_seed_database
    row = json.loads((SOURCE_DIR / "manifest.json").read_text(encoding="utf-8"))[-1]
    collision = tmp_path / ("demo-" + row["file_name"])
    collision.write_text("Tài liệu riêng cần giữ nguyên.", encoding="utf-8")
    original = collision.read_bytes()
    with pytest.raises(ValueError):
        with sessions.begin() as db:
            seed_data(db, upload_dir=tmp_path)
    assert collision.read_bytes() == original
    assert {path.name for path in tmp_path.iterdir()} == {collision.name}
    with sessions() as db:
        for model in (Subject, Topic, User, Document, DocumentChunk):
            assert db.scalar(select(func.count()).select_from(model)) == 0
