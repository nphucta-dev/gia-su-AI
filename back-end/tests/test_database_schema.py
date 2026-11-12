"""Kiểm tra thiết kế và SQL MySQL mà không cần mở kết nối database."""

import importlib.util
from io import StringIO
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    JSON,
    MetaData,
    Table,
    UniqueConstraint,
    Integer,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import configure_mappers
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
DIALECT = mysql.dialect()
TABLE_COLUMNS = {
    "users": "id email password_hash full_name birth_year role is_active created_at updated_at",
    "subjects": "id name grade_level is_active created_at",
    "topics": "id subject_id chapter_name name description is_active created_at",
    "documents": "id topic_id title file_path source_url status is_active created_at processed_at",
    "document_chunks": "id document_id chunk_index content embedding created_at",
    "chat_sessions": "id user_id topic_id title created_at updated_at",
    "chat_messages": "id session_id role content hint_level is_full_solution feedback source_refs token_count created_at",
    "quizzes": "id user_id topic_id difficulty status score created_at completed_at",
    "quiz_questions": "id quiz_id position question_text options correct_answer explanation",
    "quiz_answers": "id question_id user_answer is_correct created_at",
    "learning_progress": "id user_id topic_id total_quizzes correct_count total_count mastery_percent last_studied_at",
}
NULLABLE_COLUMNS = {
    ("users", "birth_year"),
    ("topics", "description"),
    ("documents", "source_url"),
    ("documents", "processed_at"),
    ("document_chunks", "embedding"),
    ("chat_sessions", "title"),
    ("chat_messages", "hint_level"),
    ("chat_messages", "feedback"),
    ("chat_messages", "token_count"),
    ("quizzes", "score"),
    ("quizzes", "completed_at"),
    ("learning_progress", "last_studied_at"),
}
EXPECTED_FKS = {
    ("topics", "subject_id", "subjects.id", "RESTRICT"),
    ("documents", "topic_id", "topics.id", "RESTRICT"),
    ("document_chunks", "document_id", "documents.id", "CASCADE"),
    ("chat_sessions", "user_id", "users.id", "CASCADE"),
    ("chat_sessions", "topic_id", "topics.id", "RESTRICT"),
    ("chat_messages", "session_id", "chat_sessions.id", "CASCADE"),
    ("quizzes", "user_id", "users.id", "CASCADE"),
    ("quizzes", "topic_id", "topics.id", "RESTRICT"),
    ("quiz_questions", "quiz_id", "quizzes.id", "CASCADE"),
    ("quiz_answers", "question_id", "quiz_questions.id", "CASCADE"),
    ("learning_progress", "user_id", "users.id", "CASCADE"),
    ("learning_progress", "topic_id", "topics.id", "RESTRICT"),
}


def test_models_register_exact_documented_tables_and_columns():
    configure_mappers()
    assert set(Base.metadata.tables) == set(TABLE_COLUMNS)
    nullable = set()
    for name, expected in TABLE_COLUMNS.items():
        table = Base.metadata.tables[name]
        assert list(table.c.keys()) == expected.split()
        assert list(table.primary_key.columns.keys()) == ["id"]
        assert isinstance(table.c.id.type, Integer)
        assert table.c.id.autoincrement is True
        assert table.c.id.server_default is None
        assert dict(table.kwargs) == {
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_0900_as_cs",
        }
        for column in table.c:
            if column.nullable:
                nullable.add((name, column.name))
            if isinstance(column.type, DateTime) or isinstance(
                getattr(column.type, "impl", None), mysql.DATETIME
            ):
                assert str(column.type.compile(dialect=DIALECT)) == "DATETIME(6)"
                if column.name in {"created_at", "updated_at"}:
                    assert str(column.server_default.arg) == "CURRENT_TIMESTAMP(6)"
        # Mọi bảng có thể sinh DDL MySQL, không vô tình dùng SQLite/type chung sai.
        assert f"CREATE TABLE {name}" in str(CreateTable(table).compile(dialect=DIALECT))
    assert nullable == NULLABLE_COLUMNS


@pytest.mark.parametrize(
    ("table", "column", "sql_type"),
    [
        ("users", "email", "VARCHAR(255)"),
        ("users", "full_name", "VARCHAR(120)"),
        ("users", "birth_year", "SMALLINT"),
        ("users", "role", "VARCHAR(10)"),
        ("subjects", "grade_level", "VARCHAR(50)"),
        ("topics", "chapter_name", "VARCHAR(150)"),
        ("topics", "name", "VARCHAR(180)"),
        ("documents", "title", "VARCHAR(200)"),
        ("documents", "status", "VARCHAR(10)"),
        ("chat_messages", "role", "VARCHAR(12)"),
        ("chat_messages", "source_refs", "JSON"),
        ("quiz_questions", "options", "JSON"),
        ("quizzes", "status", "VARCHAR(15)"),
        ("quizzes", "score", "NUMERIC(5, 2)"),
        ("learning_progress", "mastery_percent", "NUMERIC(5, 2)"),
        ("quiz_questions", "correct_answer", "CHAR(1)"),
        ("quiz_answers", "user_answer", "CHAR(1)"),
        ("document_chunks", "embedding", "JSON"),
    ],
)
def test_mysql_column_types(table, column, sql_type):
    assert str(Base.metadata.tables[table].c[column].type.compile(dialect=DIALECT)) == sql_type


def test_foreign_keys_uniqueness_and_delete_rules():
    foreign_keys = {
        (table.name, fk.parent.name, fk.target_fullname, fk.ondelete)
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
    }
    assert foreign_keys == EXPECTED_FKS
    unique_columns = {
        (table.name, tuple(constraint.columns.keys()))
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert unique_columns == {
        ("users", ("email",)),
        ("subjects", ("name", "grade_level")),
        ("topics", ("subject_id", "chapter_name", "name")),
        ("document_chunks", ("document_id", "chunk_index")),
        ("quiz_questions", ("quiz_id", "position")),
        ("quiz_answers", ("question_id",)),
        ("learning_progress", ("user_id", "topic_id")),
    }
    assert app.models.Subject.topics.property.passive_deletes == "all"
    assert "delete" not in app.models.Topic.documents.property.cascade
    assert app.models.QuizQuestion.answer.property.uselist is False


def test_checks_defaults_and_history_indexes():
    checks = {
        constraint.name: str(constraint.sqltext)
        for table in Base.metadata.tables.values()
        for constraint in table.constraints
        if isinstance(constraint, CheckConstraint)
    }
    assert checks == {
        "ck_users_role": "role IN ('LEARNER', 'ADMIN')",
        "ck_documents_status": "status IN ('pending', 'ready', 'error')",
        "ck_document_chunks_chunk_index": "chunk_index >= 0",
        "ck_document_chunks_embedding": "embedding IS NULL OR (JSON_TYPE(embedding) = 'ARRAY' AND JSON_LENGTH(embedding) = 768)",
        "ck_chat_messages_role": "role IN ('user', 'assistant')",
        "ck_chat_messages_hint_level": "hint_level BETWEEN 1 AND 3",
        "ck_chat_messages_feedback": "feedback IN (-1, 1)",
        "ck_chat_messages_token_count": "token_count >= 0",
        "ck_quizzes_difficulty": "difficulty IN ('easy', 'medium', 'hard')",
        "ck_quizzes_status": "status IN ('in_progress', 'completed')",
        "ck_quizzes_score": "score BETWEEN 0 AND 100",
        "ck_quiz_questions_position": "position BETWEEN 1 AND 5",
        "ck_quiz_questions_correct_answer": "correct_answer IN ('A', 'B', 'C', 'D')",
        "ck_quiz_answers_user_answer": "user_answer IN ('A', 'B', 'C', 'D')",
        "ck_learning_progress_total_quizzes": "total_quizzes >= 0",
        "ck_learning_progress_correct_count": "correct_count >= 0",
        "ck_learning_progress_total_count": "total_count >= 0",
        "ck_learning_progress_correct_count_total_count": "correct_count <= total_count",
        "ck_learning_progress_mastery_percent": "mastery_percent BETWEEN 0 AND 100",
    }
    message = Base.metadata.tables["chat_messages"]
    assert str(message.c.source_refs.server_default.arg) == "(JSON_ARRAY())"
    assert isinstance(Base.metadata.tables["document_chunks"].c.embedding.type, JSON)
    assert Base.metadata.tables["users"].c.updated_at.onupdate is not None
    assert Base.metadata.tables["chat_sessions"].c.updated_at.onupdate is not None
    indexes = {
        index.name: str(CreateIndex(index).compile(dialect=DIALECT))
        for table in Base.metadata.tables.values()
        for index in table.indexes
    }
    assert set(indexes) == {
        "ix_topics_subject_id",
        "ix_chat_sessions_user_updated_at",
        "ix_chat_messages_session_created_at",
        "ix_quizzes_user_completed_at",
    }
    assert "(user_id, updated_at DESC)" in indexes["ix_chat_sessions_user_updated_at"]
    assert "(session_id, created_at)" in indexes["ix_chat_messages_session_created_at"]
    assert "(user_id, completed_at DESC)" in indexes["ix_quizzes_user_completed_at"]


def table_signature(table):
    return {
        "options": dict(table.kwargs),
        "columns": [
            (
                column.name,
                str(column.type.compile(dialect=DIALECT)),
                column.nullable,
                column.primary_key,
                str(column.server_default.arg) if column.server_default else None,
            )
            for column in table.c
        ],
        "checks": {
            (item.name, str(item.sqltext))
            for item in table.constraints
            if isinstance(item, CheckConstraint)
        },
        "unique": {
            (item.name, tuple(item.columns.keys()))
            for item in table.constraints
            if isinstance(item, UniqueConstraint)
        },
        "foreign_keys": {
            (fk.parent.name, fk.target_fullname, fk.ondelete) for fk in table.foreign_keys
        },
        "indexes": {str(CreateIndex(index).compile(dialect=DIALECT)) for index in table.indexes},
    }


def test_legacy_schema_diff_is_limited_to_id_columns(monkeypatch):
    path = BACKEND_DIR / "alembic/versions/0001_create_learning_schema.py"
    spec = importlib.util.spec_from_file_location("initial_learning_schema", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    metadata = MetaData()

    def create_index(name, table_name, columns):
        table = metadata.tables[table_name]
        Index(name, *(table.c[item] if isinstance(item, str) else item for item in columns))

    monkeypatch.setattr(
        revision.op,
        "create_table",
        lambda name, *items, **options: Table(name, metadata, *items, **options),
    )
    monkeypatch.setattr(revision.op, "create_index", create_index)
    monkeypatch.setattr(revision.op, "execute", lambda _: None)
    revision.upgrade()
    assert set(metadata.tables) == set(TABLE_COLUMNS)
    for name, table in metadata.tables.items():
        for column in table.c:
            if column.name == "id" or column.foreign_keys:
                column.type = Integer()
                column.server_default = None
        assert table_signature(table) == table_signature(Base.metadata.tables[name]), name


def test_offline_upgrade_and_downgrade_generate_mysql_sql(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL", "mysql+pymysql://test:test@localhost/gia_su_ai_test?charset=utf8mb4"
    )
    upgrade = StringIO()
    config = Config(str(BACKEND_DIR / "alembic.ini"), output_buffer=upgrade)
    command.upgrade(config, "0001_create_learning_schema", sql=True)
    sql = upgrade.getvalue()
    assert "CREATE EXTENSION" not in sql
    assert "CHAR(32)" in sql
    assert "DEFAULT (REPLACE(UUID(), '-', ''))" in sql
    assert "DEFAULT (JSON_ARRAY())" in sql
    assert "ENGINE=InnoDB" in sql
    assert "CHARSET=utf8mb4" in sql
    assert "COLLATE utf8mb4_0900_as_cs" in sql
    for table_name in TABLE_COLUMNS:
        assert f"CREATE TABLE {table_name} (" in sql
    assert "JSON" in sql and "DATETIME(6)" in sql
    assert "JSONB" not in sql and "VECTOR(" not in sql and "TIMESTAMP WITH TIME ZONE" not in sql
    assert "updated_at DESC" in sql and "completed_at DESC" in sql
    assert "INSERT INTO alembic_version" in sql

    downgrade = StringIO()
    config.output_buffer = downgrade
    command.downgrade(config, "0001_create_learning_schema:base", sql=True)
    sql = downgrade.getvalue()
    for table_name in TABLE_COLUMNS:
        assert f"DROP TABLE {table_name};" in sql
    assert (
        sql.index("DROP TABLE quiz_answers")
        < sql.index("DROP TABLE quiz_questions")
        < sql.index("DROP TABLE quizzes")
    )
    assert "DROP EXTENSION" not in sql
