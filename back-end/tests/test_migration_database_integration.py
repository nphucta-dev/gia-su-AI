"""TK-085: migrate populated UUID history only in a disposable MySQL database."""

from datetime import datetime
import os
from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import Integer, MetaData, func, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy_utils import create_database, drop_database

from app.db.database import create_database_engine

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture
def legacy_database():
    raw_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not raw_url:
        pytest.skip("Cần TEST_DATABASE_URL để kiểm thử migration MySQL thực.")
    test_name = "gia_su_ai_test_" + uuid4().hex
    test_url = make_url(raw_url).set(database=test_name)
    engine = create_database_engine(test_url.render_as_string(hide_password=False))
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    created = False
    try:
        create_database(test_url, encoding="utf8mb4")
        created = True
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "0001_create_learning_schema")
        yield engine, config
    finally:
        engine.dispose()
        # Never drop the configured application database, only this generated name.
        if created and test_url.database == test_name and test_name.startswith("gia_su_ai_test_"):
            drop_database(test_url)


def test_populated_uuid_migration_preserves_eleven_tables_links_and_source_references(legacy_database):
    engine, config = legacy_database
    legacy = MetaData()
    legacy.reflect(engine)
    names = set(legacy.tables) - {"alembic_version"}
    assert len(names) == 11
    ids = {name: uuid4().hex for name in names}
    completed_at = datetime(2026, 11, 20, 8, 0, 0)
    rows = {
        "users": {"id": ids["users"], "email": "legacy@example.com", "full_name": "Người học cũ", "password_hash": "preserve-existing-hash"},
        "subjects": {"id": ids["subjects"], "name": "Toán cũ", "grade_level": "THPT"},
        "topics": {"id": ids["topics"], "subject_id": ids["subjects"], "chapter_name": "Đại số", "name": "Phương trình"},
        "documents": {"id": ids["documents"], "topic_id": ids["topics"], "title": "Nguồn cũ", "file_path": "legacy/source.txt", "status": "ready", "is_active": True, "processed_at": completed_at},
        "document_chunks": {"id": ids["document_chunks"], "document_id": ids["documents"], "chunk_index": 0, "content": "Nội dung nguồn đã được trích dẫn."},
        "chat_sessions": {"id": ids["chat_sessions"], "user_id": ids["users"], "topic_id": ids["topics"], "title": "Hội thoại cũ"},
        "chat_messages": {"id": ids["chat_messages"], "session_id": ids["chat_sessions"], "role": "assistant", "content": "Phản hồi đã lưu", "hint_level": 1, "feedback": 1, "source_refs": [{"document_id": ids["documents"], "chunk_id": ids["document_chunks"], "title": "Nguồn cũ", "chunk_index": 0, "page": 2}]},
        "quizzes": {"id": ids["quizzes"], "user_id": ids["users"], "topic_id": ids["topics"], "difficulty": "easy", "status": "completed", "score": 60, "completed_at": completed_at},
        "learning_progress": {"id": ids["learning_progress"], "user_id": ids["users"], "topic_id": ids["topics"], "total_quizzes": 1, "correct_count": 3, "total_count": 5, "mastery_percent": 60, "last_studied_at": completed_at},
    }
    with engine.begin() as connection:
        # Topological order ensures all twelve real foreign-key links are valid.
        for table in legacy.sorted_tables:
            if table.name in rows:
                connection.execute(table.insert().values(**rows[table.name]))
        for position in range(1, 6):
            question_id = uuid4().hex
            connection.execute(legacy.tables["quiz_questions"].insert().values(
                id=question_id, quiz_id=ids["quizzes"], position=position,
                question_text=f"Câu hỏi cũ {position}", options={"A": "1", "B": "2", "C": "3", "D": "4"},
                correct_answer="B", explanation="Giải thích đã lưu.",
            ))
            connection.execute(legacy.tables["quiz_answers"].insert().values(
                id=uuid4().hex, question_id=question_id,
                user_answer="B" if position <= 3 else "A", is_correct=position <= 3,
            ))
        before = {name: [dict(row) for row in connection.execute(select(legacy.tables[name])).mappings()] for name in names}

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    migrated = MetaData()
    migrated.reflect(engine)
    mappings = {}
    with engine.begin() as connection:
        # JSON citation references also depend on documents/chunks, even though
        # these two edges are not physical foreign keys in metadata.sorted_tables.
        verification_order = (
            "users", "subjects", "topics", "documents", "document_chunks",
            "chat_sessions", "chat_messages", "quizzes", "quiz_questions",
            "quiz_answers", "learning_progress",
        )
        for table_name in verification_order:
            table = migrated.tables[table_name]
            actual = [dict(row) for row in connection.execute(select(table)).mappings()]
            assert len(actual) == len(before[table.name])
            mappings[table.name] = {}
            for original in before[table.name]:
                expected = {key: value for key, value in original.items() if key != "id"}
                for foreign_key in table.foreign_keys:
                    expected[foreign_key.parent.name] = mappings[foreign_key.column.table.name][original[foreign_key.parent.name]]
                if table.name == "chat_messages":
                    expected["source_refs"] = [{
                        **original["source_refs"][0],
                        "document_id": mappings["documents"][ids["documents"]],
                        "chunk_id": mappings["document_chunks"][ids["document_chunks"]],
                    }]
                matches = [row for row in actual if {key: value for key, value in row.items() if key != "id"} == expected]
                assert len(matches) == 1, table.name
                new_id = matches[0]["id"]
                assert isinstance(new_id, int) and new_id > 0
                mappings[table.name][original["id"]] = new_id

        for table_name in names:
            columns = inspect(connection).get_columns(table_name)
            assert all(not column["name"].startswith(("_ai_", "_old_")) for column in columns)
            primary_key = next(column for column in columns if column["name"] == "id")
            assert isinstance(primary_key["type"], Integer) and primary_key["autoincrement"] is True
        subject = migrated.tables["subjects"]
        previous_max = connection.scalar(select(func.max(subject.c.id)))
        inserted = connection.execute(subject.insert().values(name="Môn mới sau migration", grade_level="THPT"))
        assert inserted.inserted_primary_key[0] > previous_max
        config.attributes["connection"] = connection
        command.check(config)
