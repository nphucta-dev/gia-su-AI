"""Chạy với TEST_DATABASE_URL; mỗi lần chạy dùng một database tạm riêng."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, event, func, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy_utils import create_database, drop_database

from app.config import Settings
from app.db.database import create_database_engine, create_session_factory
from app.db.init_db import init_database
from app.db.seed import SAMPLE_USERS, seed_data
from app.main import create_app
from app.models import (
    ChatMessage,
    ChatSession,
    Document,
    DocumentChunk,
    LearningProgress,
    Quiz,
    QuizAnswer,
    QuizQuestion,
    Subject,
    Topic,
    User,
)
from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.utils.password import hash_password, verify_password

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def database():
    raw_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not raw_url:
        pytest.skip("Cần TEST_DATABASE_URL để kiểm thử MySQL thực.")
    test_name = "gia_su_ai_test_" + uuid4().hex
    test_url = make_url(raw_url).set(database=test_name)
    engine = create_database_engine(test_url.render_as_string(hide_password=False))
    created = False
    try:
        create_database(test_url, encoding="utf8mb4")
        created = True
        init_database(test_url.render_as_string(hide_password=False))
        yield engine, create_session_factory(engine)
    finally:
        engine.dispose()
        # Chỉ xóa đúng database ngẫu nhiên do fixture này vừa tạo.
        if created and test_url.database == test_name and test_name.startswith("gia_su_ai_test_"):
            drop_database(test_url)


def make_catalog(db):
    suffix = uuid4().hex
    user = User(email=f"{suffix}@example.com", full_name="Người học", password_hash="test-hash")
    subject = Subject(name=f"Toán {suffix}", grade_level="THPT")
    topic = Topic(subject=subject, chapter_name="Hàm số", name="Hàm số bậc hai")
    db.add_all([user, topic])
    db.flush()
    return user, subject, topic


@pytest.mark.anyio
async def test_profile_api_persists_in_mysql_and_preserves_credentials(database):
    _, sessions = database
    with sessions.begin() as db:
        user, _, _ = make_catalog(db)
        user_id, email, password_hash = user.id, user.email, user.password_hash
    app = create_app(
        session_factory=sessions,
        settings=Settings(jwt_secret="mysql-profile-integration-" + "x" * 40),
    )
    token = app.state.token_service.create_access_token(user_id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        response = await client.patch(
            "/api/profile",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Hồ sơ MySQL", "birthYear": 2000},
        )
        assert response.status_code == 200
        restored = await client.get("/api/profile", headers={"Authorization": f"Bearer {token}"})
        assert restored.json()["user"]["birthYear"] == 2000
    with sessions() as db:
        stored = db.get(User, user_id)
        assert stored.full_name == "Hồ sơ MySQL" and stored.birth_year == 2000
        assert stored.email == email and stored.password_hash == password_hash
        assert stored.role == "LEARNER"


@pytest.mark.anyio
async def test_admin_upload_persists_file_and_document_in_mysql(database, tmp_path):
    _, sessions = database
    with sessions.begin() as db:
        admin, _, topic = make_catalog(db)
        admin.role = "ADMIN"
        admin_id, topic_id = admin.id, topic.id
    upload_dir = tmp_path / "documents"
    app = create_app(
        session_factory=sessions,
        upload_dir=upload_dir,
        settings=Settings(jwt_secret="mysql-upload-integration-" + "x" * 40),
    )
    token = app.state.token_service.create_access_token(admin_id).access_token
    headers = {"Authorization": f"Bearer {token}"}
    content = "Nội dung tài liệu MySQL thực.".encode("utf-8")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test"
    ) as client:
        options = await client.get("/api/admin/documents/options", headers=headers)
        assert options.status_code == 200
        response = await client.post(
            "/api/admin/documents", headers=headers,
            data={"topic_id": str(topic_id), "title": "Tài liệu MySQL"},
            files={"file": ("source.txt", content, "text/plain")},
        )
        assert response.status_code == 201
        saved = response.json()["document"]
        assert isinstance(saved["id"], int) and saved["topicId"] == topic_id
        assert saved["status"] == "ready" and saved["isActive"] is False
        assert saved["chunkCount"] == 1 and saved["processedAt"].endswith("Z")
        listing = await client.get("/api/admin/documents", headers=headers)
        assert any(row["id"] == saved["id"] for row in listing.json()["documents"])
    with sessions() as db:
        stored = db.get(Document, saved["id"])
        assert stored.title == "Tài liệu MySQL" and stored.topic_id == topic_id
        assert stored.status == "ready" and not stored.is_active and stored.processed_at is not None
        chunks = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == stored.id)).all()
        assert len(chunks) == 1 and chunks[0].chunk_index == 0
        assert chunks[0].content == content.decode("utf-8") and chunks[0].embedding is None
        assert Path(stored.file_path).name == stored.file_path
        stored_file = upload_dir / stored.file_path
        assert stored_file.resolve().parent == upload_dir.resolve()
        assert stored_file.read_bytes() == content


@pytest.mark.anyio
async def test_document_processing_retry_concurrency_and_persistence_in_mysql(database, tmp_path):
    _, sessions = database
    with sessions.begin() as db:
        admin, _, topic = make_catalog(db)
        admin.role = "ADMIN"
        pending = Document(topic_id=topic.id, title="Tài liệu cũ", file_path="legacy.txt")
        retry = Document(topic_id=topic.id, title="Tài liệu cần thử lại", file_path="retry.txt", status="error")
        db.add_all([pending, retry])
        db.flush()
        db.add(DocumentChunk(document_id=retry.id, chunk_index=0, content="Đoạn cũ chưa hợp lệ"))
        admin_id, pending_id, retry_id = admin.id, pending.id, retry.id
    content = "\n\n".join(f"Bài học {index}: Hàm số bậc hai có đồ thị là parabol." for index in range(160))
    (tmp_path / "legacy.txt").write_text(content, encoding="utf-8")
    (tmp_path / "retry.txt").write_bytes(b"\xff\xfe")
    settings = Settings(jwt_secret="mysql-processing-integration-" + "x" * 40)
    app = create_app(session_factory=sessions, upload_dir=tmp_path, settings=settings)
    token = app.state.token_service.create_access_token(admin_id).access_token
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test", headers=headers,
    ) as client:
        path = f"/api/admin/documents/{pending_id}/process"
        first, second = await asyncio.gather(client.post(path), client.post(path))
        assert first.status_code == second.status_code == 200
        saved = first.json()["document"]
        assert saved["status"] == "ready" and saved["chunkCount"] > 1
        assert second.json()["document"]["chunkCount"] == saved["chunkCount"]
        failed = await client.post(f"/api/admin/documents/{retry_id}/process")
        assert failed.status_code == 200
        error = failed.json()["document"]
        assert error["status"] == "error" and error["chunkCount"] == 0
        assert error["processedAt"] and not error["isActive"]
        with sessions() as db:
            rows = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == pending_id).order_by(DocumentChunk.chunk_index)).all()
            chunk_ids = [row.id for row in rows]
            assert [row.chunk_index for row in rows] == list(range(saved["chunkCount"]))
            assert all(row.content.strip() and len(row.content) <= 1000 and row.embedding is None for row in rows)
            assert "Bài học 0:" in rows[0].content and "Bài học 159:" in rows[-1].content
            assert db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == retry_id)) == 0
        repeated = await client.post(path)
        assert repeated.status_code == 200 and repeated.json()["document"] == saved
        (tmp_path / "retry.txt").write_text("Nội dung đã khôi phục.", encoding="utf-8")
        restored = await client.post(f"/api/admin/documents/{retry_id}/process")
        assert restored.json()["document"]["status"] == "ready"
        assert restored.json()["document"]["chunkCount"] == 1
    # Một app mới đọc đúng kết quả đã commit, không dựa vào bộ nhớ của tiến trình cũ.
    app = create_app(session_factory=sessions, upload_dir=tmp_path, settings=settings)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers) as client:
        listing = (await client.get("/api/admin/documents")).json()["documents"]
        assert next(item for item in listing if item["id"] == pending_id) == saved
    with sessions() as db:
        rows = db.scalars(select(DocumentChunk).where(DocumentChunk.document_id == pending_id).order_by(DocumentChunk.chunk_index)).all()
        assert [row.id for row in rows] == chunk_ids


@pytest.mark.anyio
async def test_processing_chunk_write_failure_rolls_back_status_in_mysql(database, tmp_path):
    _, sessions = database
    with sessions.begin() as db:
        admin, _, topic = make_catalog(db)
        admin.role = "ADMIN"
        document = Document(topic_id=topic.id, title="Giao dịch cần nguyên vẹn", file_path="atomic.txt")
        db.add(document)
        db.flush()
        admin_id, document_id = admin.id, document.id
    (tmp_path / "atomic.txt").write_text("Văn bản phải lưu đủ cùng trạng thái ready.", encoding="utf-8")
    app = create_app(session_factory=sessions, upload_dir=tmp_path, settings=Settings(jwt_secret="mysql-atomic-processing-" + "x" * 40))
    token = app.state.token_service.create_access_token(admin_id).access_token

    def fail_chunk_write(db, *_):
        if any(isinstance(item, DocumentChunk) and item.document_id == document_id for item in db.new):
            raise RuntimeError("test-only chunk write failure")

    event.listen(sessions.class_, "before_flush", fail_chunk_write)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            failed = await client.post(f"/api/admin/documents/{document_id}/process")
            assert failed.status_code == 500 and "test-only" not in failed.text
    finally:
        event.remove(sessions.class_, "before_flush", fail_chunk_write)
    with sessions() as db:
        stored = db.get(Document, document_id)
        assert stored.status == "pending" and stored.processed_at is None
        assert db.scalar(select(func.count(DocumentChunk.id)).where(DocumentChunk.document_id == document_id)) == 0
    assert (tmp_path / "atomic.txt").is_file()


@pytest.mark.anyio
async def test_catalog_grade_filter_in_mysql(database):
    _, sessions = database
    suffix = uuid4().hex
    with sessions.begin() as db:
        learner = User(email=f"catalog-{suffix}@example.com", full_name="Người học", password_hash="test-hash")
        lower = Subject(name=f"Toán {suffix}", grade_level="THCS")
        higher = Subject(name=f"Toán {suffix}", grade_level="THPT")
        hidden = Subject(name=f"Môn đã tắt {suffix}", grade_level="THCS", is_active=False)
        empty = Subject(name=f"Môn trống {suffix}", grade_level="THCS")
        db.add_all([
            learner, empty,
            Topic(subject=lower, chapter_name="Số học", name="Phân số"),
            Topic(subject=lower, chapter_name="Số học", name="Chủ đề đã tắt", is_active=False),
            Topic(subject=higher, chapter_name="Đại số", name="Phương trình"),
            Topic(subject=hidden, chapter_name="Chương 1", name="Chủ đề của môn đã tắt"),
        ])
        db.flush()
        learner_id, lower_id, higher_id, hidden_id, empty_id = learner.id, lower.id, higher.id, hidden.id, empty.id
    app = create_app(
        session_factory=sessions,
        settings=Settings(jwt_secret="mysql-catalog-integration-" + "x" * 40),
    )
    token = app.state.token_service.create_access_token(learner_id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test", headers={"Authorization": f"Bearer {token}"},
    ) as client:
        unfiltered = await client.get("/api/catalog/subjects")
        assert unfiltered.status_code == 200
        ids = {subject["id"] for subject in unfiltered.json()["subjects"]}
        assert {lower_id, higher_id} <= ids and not {hidden_id, empty_id} & ids
        for grade, expected_id, excluded_id in (("THCS", lower_id, higher_id), ("THPT", higher_id, lower_id)):
            response = await client.get("/api/catalog/subjects", params={"gradeLevel": f"  {grade}  "})
            assert response.status_code == 200
            subjects = response.json()["subjects"]
            assert all(subject["gradeLevel"] == grade for subject in subjects)
            assert expected_id in {subject["id"] for subject in subjects}
            assert excluded_id not in {subject["id"] for subject in subjects}
            own_subject = next(subject for subject in subjects if subject["id"] == expected_id)
            assert sum(len(chapter["topics"]) for chapter in own_subject["chapters"]) == 1
        empty_result = await client.get("/api/catalog/subjects", params={"gradeLevel": "not-a-real-grade"})
        assert empty_result.json() == {"subjects": []}


@pytest.mark.anyio
async def test_admin_catalog_persists_edits_and_toggles_without_deleting_history(database):
    _, sessions = database
    suffix = uuid4().hex
    with sessions.begin() as db:
        admin, _, _ = make_catalog(db)
        admin.role = "ADMIN"
        admin_id = admin.id
    settings = Settings(jwt_secret="mysql-admin-catalog-" + "x" * 40)
    app = create_app(session_factory=sessions, settings=settings)
    token = app.state.token_service.create_access_token(admin_id).access_token
    headers = {"Authorization": f"Bearer {token}"}
    subject_name = f"Môn quản trị {suffix}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test", headers=headers,
    ) as client:
        response = await client.post("/api/admin/subjects", json={"name": subject_name, "gradeLevel": "THCS"})
        assert response.status_code == 201, response.text
        subject_id = response.json()["subject"]["id"]
        assert type(subject_id) is int
        # Cùng tên nhưng khác cấp học là hai môn hợp lệ.
        higher = await client.post("/api/admin/subjects", json={"name": subject_name, "gradeLevel": "THPT"})
        assert higher.status_code == 201
        duplicate = await client.post("/api/admin/subjects", json={"name": subject_name, "gradeLevel": "THCS"})
        assert duplicate.status_code == 409
        topic_body = {"subjectId": subject_id, "chapterName": "Chương 1", "name": "Chủ đề mới", "description": "Mô tả cũ"}
        created = await client.post("/api/admin/topics", json=topic_body)
        assert created.status_code == 201, created.text
        topic_id = created.json()["topic"]["id"]
        assert (await client.post("/api/admin/topics", json=topic_body)).status_code == 409
        revised = await client.patch(f"/api/admin/topics/{topic_id}", json={"name": "Chủ đề đã sửa", "description": None})
        assert revised.status_code == 200
        assert revised.json()["topic"]["description"] is None
        assert revised.json()["topic"]["chapterName"] == "Chương 1"
        # Lỗi trùng UNIQUE phải rollback, không để lại cập nhật từng phần.
        failed = await client.patch(f"/api/admin/subjects/{subject_id}", json={"gradeLevel": "THPT", "isActive": False})
        assert failed.status_code == 409

        with sessions.begin() as db:
            history = ChatSession(user_id=admin_id, topic_id=topic_id, title="Lịch sử cần giữ")
            source = Document(topic_id=topic_id, title="Nguồn cần giữ", file_path=f"{suffix}.txt")
            db.add_all([history, source])
            db.flush()
            message = ChatMessage(session_id=history.id, role="user", content="Câu hỏi đã lưu")
            db.add(message)
            db.flush()
            history_id, source_id, message_id = history.id, source.id, message.id

        assert (await client.get(f"/api/catalog/topics/{topic_id}")).status_code == 200
        disabled = await client.patch(f"/api/admin/subjects/{subject_id}", json={"isActive": False})
        assert disabled.status_code == 200
        assert (await client.get(f"/api/catalog/topics/{topic_id}")).status_code == 404
        assert subject_id not in {row["id"] for row in (await client.get("/api/catalog/subjects")).json()["subjects"]}
        assert subject_id not in {row["id"] for row in (await client.get("/api/admin/documents/options")).json()["subjects"]}
        admin_topics = (await client.get("/api/admin/topics")).json()["topics"]
        assert next(row for row in admin_topics if row["id"] == topic_id)["isActive"] is True
        assert (await client.patch(f"/api/admin/topics/{topic_id}", json={"isActive": False})).status_code == 200
        assert (await client.patch(f"/api/admin/subjects/{subject_id}", json={"isActive": True})).status_code == 200
        assert (await client.get(f"/api/catalog/topics/{topic_id}")).status_code == 404
        assert (await client.patch(f"/api/admin/topics/{topic_id}", json={"isActive": True})).status_code == 200
        assert (await client.get(f"/api/catalog/topics/{topic_id}")).status_code == 200

    # Mở app mới chứng minh thay đổi nằm trong MySQL, không chỉ trong bộ nhớ.
    restored = create_app(session_factory=sessions, settings=settings)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=restored, raise_app_exceptions=False),
        base_url="http://test", headers=headers,
    ) as client:
        subject_rows = (await client.get("/api/admin/subjects")).json()["subjects"]
        saved_subject = next(row for row in subject_rows if row["id"] == subject_id)
        assert saved_subject["gradeLevel"] == "THCS" and saved_subject["isActive"] is True
        topic_rows = (await client.get("/api/admin/topics")).json()["topics"]
        saved_topic = next(row for row in topic_rows if row["id"] == topic_id)
        assert saved_topic["name"] == "Chủ đề đã sửa" and saved_topic["description"] is None
    with sessions() as db:
        assert db.get(ChatSession, history_id).topic_id == topic_id
        assert db.get(ChatMessage, message_id).content == "Câu hỏi đã lưu"
        assert db.get(Document, source_id).topic_id == topic_id


def test_migration_matches_models(database):
    engine, _ = database
    assert len(set(inspect(engine).get_table_names()) - {"alembic_version"}) == 11
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)


def test_mysql_defaults_json_and_embedding(database):
    _, sessions = database
    with sessions.begin() as db:
        user, _, topic = make_catalog(db)
        session = ChatSession(user_id=user.id, topic_id=topic.id)
        document = Document(topic_id=topic.id, title="Tài liệu", file_path="sample.txt")
        db.add_all([session, document])
        db.flush()
        first = ChatMessage(session_id=session.id, role="assistant", content="Gợi ý 1")
        second = ChatMessage(session_id=session.id, role="assistant", content="Gợi ý 2")
        chunk = DocumentChunk(document_id=document.id, chunk_index=0, content="Hàm số")
        db.add_all([first, second, chunk])
        db.flush()
        db.refresh(first)
        db.refresh(second)
        assert type(user.id) is int and user.id > 0
        assert user.created_at.utcoffset() is not None
        assert user.updated_at.utcoffset() is not None
        assert first.source_refs == second.source_refs == []
        first.source_refs.append({"title": "Nguồn thử"})
        assert second.source_refs == []
        assert document.status == "pending" and document.is_active is False
        assert chunk.embedding is None
        chunk.embedding = [0.25] * 768
        db.flush()
        db.refresh(chunk)
        assert len(chunk.embedding) == 768
        assert float(chunk.embedding[0]) == 0.25


@pytest.mark.parametrize(
    "case",
    [
        "role",
        "status",
        "chunk_index",
        "hint_level",
        "feedback",
        "token_count",
        "difficulty",
        "score",
        "position",
        "answer",
        "progress",
    ],
)
def test_invalid_values_rejected_by_database(database, case):
    _, sessions = database
    with sessions.begin() as db:
        user, _, topic = make_catalog(db)
        chat = ChatSession(user_id=user.id, topic_id=topic.id)
        document = Document(topic_id=topic.id, title="Nguồn", file_path="sample.txt")
        quiz = Quiz(user_id=user.id, topic_id=topic.id, difficulty="medium")
        db.add_all([chat, document, quiz])
        db.flush()
        bad_rows = {
            "role": User(
                email=f"{uuid4().hex}@example.com",
                full_name="Test",
                password_hash="hash",
                role="OWNER",
            ),
            "status": Document(
                topic_id=topic.id, title="Nguồn", file_path="a.txt", status="invalid"
            ),
            "chunk_index": DocumentChunk(document_id=document.id, chunk_index=-1, content="Sai"),
            "hint_level": ChatMessage(
                session_id=chat.id, role="assistant", content="Sai", hint_level=4
            ),
            "feedback": ChatMessage(
                session_id=chat.id, role="assistant", content="Sai", feedback=0
            ),
            "token_count": ChatMessage(
                session_id=chat.id, role="assistant", content="Sai", token_count=-1
            ),
            "difficulty": Quiz(user_id=user.id, topic_id=topic.id, difficulty="expert"),
            "score": Quiz(user_id=user.id, topic_id=topic.id, difficulty="easy", score=101),
            "position": QuizQuestion(
                quiz_id=quiz.id,
                position=6,
                question_text="Sai",
                options={},
                correct_answer="A",
                explanation="Sai",
            ),
            "answer": QuizQuestion(
                quiz_id=quiz.id,
                position=1,
                question_text="Sai",
                options={},
                correct_answer="E",
                explanation="Sai",
            ),
            "progress": LearningProgress(
                user_id=user.id, topic_id=topic.id, correct_count=2, total_count=1
            ),
        }
        # PyMySQL trả lỗi CHECK 3819 qua OperationalError, không phải IntegrityError.
        with pytest.raises(DBAPIError) as failure:
            with db.begin_nested():
                db.add(bad_rows[case])
                db.flush()
        assert failure.value.orig.args[0] == 3819


def test_single_answer_and_progress_unique(database):
    _, sessions = database
    with sessions.begin() as db:
        user, _, topic = make_catalog(db)
        quiz = Quiz(user_id=user.id, topic_id=topic.id, difficulty="easy")
        db.add(quiz)
        db.flush()
        question = QuizQuestion(
            quiz_id=quiz.id,
            position=1,
            question_text="1 + 1?",
            options={"A": "1", "B": "2", "C": "3", "D": "4"},
            correct_answer="B",
            explanation="1 + 1 = 2",
        )
        db.add(question)
        db.flush()
        db.add_all(
            [
                QuizAnswer(question_id=question.id, user_answer="B", is_correct=True),
                LearningProgress(user_id=user.id, topic_id=topic.id),
            ]
        )
        db.flush()
        for duplicate in (
            QuizAnswer(question_id=question.id, user_answer="A", is_correct=False),
            LearningProgress(user_id=user.id, topic_id=topic.id),
        ):
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.add(duplicate)
                    db.flush()


def test_restrict_catalog_and_cascade_user_history(database):
    _, sessions = database
    with sessions.begin() as db:
        user, subject, topic = make_catalog(db)
        chat = ChatSession(user_id=user.id, topic_id=topic.id)
        quiz = Quiz(user_id=user.id, topic_id=topic.id, difficulty="easy")
        db.add_all([chat, quiz, LearningProgress(user_id=user.id, topic_id=topic.id)])
        db.flush()
        question = QuizQuestion(
            quiz_id=quiz.id,
            position=1,
            question_text="Câu hỏi",
            options={},
            correct_answer="A",
            explanation="Giải thích",
        )
        db.add_all([question, ChatMessage(session_id=chat.id, role="user", content="Hỏi")])
        db.flush()
        answer = QuizAnswer(question_id=question.id, user_answer="A", is_correct=True)
        db.add(answer)
        db.flush()
        for statement in (
            delete(Subject).where(Subject.id == subject.id),
            delete(Topic).where(Topic.id == topic.id),
        ):
            with pytest.raises(IntegrityError):
                with db.begin_nested():
                    db.execute(statement)
        message_id = db.scalar(select(ChatMessage.id).where(ChatMessage.session_id == chat.id))
        answer_id, question_id, quiz_id, chat_id, user_id = (
            answer.id,
            question.id,
            quiz.id,
            chat.id,
            user.id,
        )
        db.execute(delete(User).where(User.id == user_id))
        topic_id = topic.id
        db.expunge_all()
        for model, row_id in (
            (ChatSession, chat_id),
            (ChatMessage, message_id),
            (Quiz, quiz_id),
            (QuizQuestion, question_id),
            (QuizAnswer, answer_id),
        ):
            assert db.get(model, row_id) is None
        assert (
            db.scalar(
                select(func.count())
                .select_from(LearningProgress)
                .where(LearningProgress.user_id == user_id)
            )
            == 0
        )
        assert db.get(Topic, topic_id) is not None


def test_seed_can_run_twice(database):
    _, sessions = database
    with sessions.begin() as db:
        seed_data(db)
        counts = (
            db.scalar(select(func.count()).select_from(Subject)),
            db.scalar(select(func.count()).select_from(Topic)),
            db.scalar(select(func.count()).select_from(User)),
        )
        accounts = {}
        for sample in SAMPLE_USERS:
            user = db.scalar(select(User).where(User.email == sample["email"]))
            assert user is not None and user.role == sample["role"]
            assert user.is_active is True
            assert user.password_hash != sample["password"]
            assert verify_password(sample["password"], user.password_hash)
            accounts[user.email] = (user.id, user.password_hash)
        seed_data(db)
        assert counts == (
            db.scalar(select(func.count()).select_from(Subject)),
            db.scalar(select(func.count()).select_from(Topic)),
            db.scalar(select(func.count()).select_from(User)),
        )
        for email, expected in accounts.items():
            user = db.scalar(select(User).where(User.email == email))
            assert (user.id, user.password_hash) == expected


def test_seed_preserves_existing_user_password_profile_and_status(database):
    _, sessions = database
    with sessions() as db:
        with db.begin():
            seed_data(db)
            learner = db.scalar(select(User).where(User.email == "learner@example.com"))
            learner.full_name = "Tên đã thay đổi"
            learner.password_hash = hash_password("ChangedPassword@123", n=1024, r=8, p=1)
            learner.is_active = False
            db.flush()
            expected = (learner.full_name, learner.password_hash, learner.role, learner.is_active)
            seed_data(db)
            db.refresh(learner)
            assert (learner.full_name, learner.password_hash, learner.role, learner.is_active) == expected
            # Không giữ thay đổi trạng thái này cho các test khác trong cùng database.
            db.rollback()


def test_seed_custom_admin_uses_requested_password_for_new_sample_email(database, monkeypatch):
    _, sessions = database
    samples = tuple(
        {**sample, "email": f"seed-{uuid4().hex}@example.com"} for sample in SAMPLE_USERS
    )
    monkeypatch.setattr("app.db.seed.SAMPLE_USERS", samples)
    admin_email = next(sample["email"] for sample in samples if sample["role"] == "ADMIN")
    with sessions.begin() as db:
        seed_data(db, admin_email=admin_email.upper(), admin_password="CustomAdmin@123")
        admin = db.scalar(select(User).where(User.email == admin_email))
        assert admin.role == "ADMIN"
        assert verify_password("CustomAdmin@123", admin.password_hash)
        assert not verify_password("Admin@123", admin.password_hash)


def test_seed_does_not_promote_an_existing_learner(database):
    _, sessions = database
    with sessions.begin() as db:
        email = f"seed-conflict-{uuid4().hex}@example.com"
        learner = User(email=email, full_name="Learner", password_hash="unchanged", role="LEARNER")
        db.add(learner)
        db.flush()
        with pytest.raises(ValueError, match="vai trò khác"):
            seed_data(db, admin_email=email, admin_password="Admin@123")
        db.refresh(learner)
        assert learner.role == "LEARNER" and learner.password_hash == "unchanged"


@pytest.mark.anyio
async def test_register_persists_across_apps_and_duplicate_race(database):
    engine, sessions = database
    settings = Settings(database_url=engine.url.render_as_string(hide_password=False))
    email = f"{uuid4().hex}@example.com"
    body = {
        "name": "Người học",
        "email": email,
        "password": "MatKhau@123",
        "confirmPassword": "MatKhau@123",
        "consent": True,
    }
    first_app = create_app(settings=settings, password_hasher=lambda _: "test-hash")
    async with first_app.router.lifespan_context(first_app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=first_app), base_url="http://test"
        ) as client:
            responses = await asyncio.gather(
                *(client.post("/api/auth/register", json=body) for _ in range(2))
            )
            assert sorted(response.status_code for response in responses) == [201, 409]
            user_id = next(
                response.json()["user"]["id"]
                for response in responses
                if response.status_code == 201
            )
    # Một repository và app khác vẫn đọc được tài khoản đã commit.
    repository = SqlAlchemyUserRepository(sessions)
    stored = await repository.find_by_id(user_id)
    assert stored.email == email and stored.name == "Người học"
    assert stored.created_at.endswith("Z")
    assert await repository.find_by_id("not-an-id") is None
    second_app = create_app(user_repository=repository, settings=settings)
    token = second_app.state.token_service.create_access_token(user_id).access_token
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=second_app), base_url="http://test"
    ) as client:
        response = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert response.status_code == 200
        assert set(response.json()["user"]) == {"id", "name", "email", "role", "createdAt"}
        with sessions.begin() as db:
            db.get(User, stored.id).is_active = False
        assert (
            await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        ).status_code == 403
