"""Chạy với TEST_DATABASE_URL; mỗi lần chạy dùng một database tạm riêng."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import delete, func, inspect, select
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
