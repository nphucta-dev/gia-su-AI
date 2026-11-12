"""Tạo 11 bảng theo tài liệu thiết kế CSDL Gia sư AI."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = "0001_create_learning_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("birth_year", sa.SmallInteger(), nullable=True),
        sa.Column("role", sa.String(10), nullable=False, server_default=sa.text("'LEARNER'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("role IN ('LEARNER', 'ADMIN')", name="ck_users_role"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_table(
        "subjects",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("grade_level", sa.String(50), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint("name", "grade_level", name="uq_subjects_name_grade_level"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_table(
        "topics",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column(
            "subject_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("subjects.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("chapter_name", sa.String(150), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint(
            "subject_id", "chapter_name", "name", name="uq_topics_subject_id_chapter_name_name"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_index("ix_topics_subject_id", "topics", ["subject_id"])
    op.create_table(
        "documents",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column(
            "topic_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("topics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column("processed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint("status IN ('pending', 'ready', 'error')", name="ck_documents_status"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_table(
        "document_chunks",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column(
            "document_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("embedding", sa.JSON(none_as_null=True), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_document_chunks_document_id_chunk_index"
        ),
        sa.CheckConstraint("chunk_index >= 0", name="ck_document_chunks_chunk_index"),
        sa.CheckConstraint(
            "embedding IS NULL OR (JSON_TYPE(embedding) = 'ARRAY' AND JSON_LENGTH(embedding) = 768)",
            name="ck_document_chunks_embedding",
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_table(
        "chat_sessions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("topics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column(
            "updated_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_index(
        "ix_chat_sessions_user_updated_at", "chat_sessions", ["user_id", sa.text("updated_at DESC")]
    )
    op.create_table(
        "chat_messages",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column(
            "session_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(12), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("hint_level", sa.SmallInteger(), nullable=True),
        sa.Column("is_full_solution", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("feedback", sa.SmallInteger(), nullable=True),
        sa.Column(
            "source_refs", sa.JSON(), nullable=False, server_default=sa.text("(JSON_ARRAY())")
        ),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_chat_messages_role"),
        sa.CheckConstraint("hint_level BETWEEN 1 AND 3", name="ck_chat_messages_hint_level"),
        sa.CheckConstraint("feedback IN (-1, 1)", name="ck_chat_messages_feedback"),
        sa.CheckConstraint("token_count >= 0", name="ck_chat_messages_token_count"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_index(
        "ix_chat_messages_session_created_at", "chat_messages", ["session_id", "created_at"]
    )
    op.create_table(
        "quizzes",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("topics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("difficulty", sa.String(10), nullable=False),
        sa.Column("status", sa.String(15), nullable=False, server_default=sa.text("'in_progress'")),
        sa.Column("score", sa.Numeric(5, 2), nullable=True),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.Column("completed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint(
            "difficulty IN ('easy', 'medium', 'hard')", name="ck_quizzes_difficulty"
        ),
        sa.CheckConstraint("status IN ('in_progress', 'completed')", name="ck_quizzes_status"),
        sa.CheckConstraint("score BETWEEN 0 AND 100", name="ck_quizzes_score"),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_index(
        "ix_quizzes_user_completed_at", "quizzes", ["user_id", sa.text("completed_at DESC")]
    )
    op.create_table(
        "quiz_questions",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column(
            "quiz_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("quizzes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("options", sa.JSON(), nullable=False),
        sa.Column("correct_answer", sa.CHAR(1), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.UniqueConstraint("quiz_id", "position", name="uq_quiz_questions_quiz_id_position"),
        sa.CheckConstraint("position BETWEEN 1 AND 5", name="ck_quiz_questions_position"),
        sa.CheckConstraint(
            "correct_answer IN ('A', 'B', 'C', 'D')", name="ck_quiz_questions_correct_answer"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_table(
        "quiz_answers",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column(
            "question_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("quiz_questions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_answer", sa.CHAR(1), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            mysql.DATETIME(fsp=6),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP(6)"),
        ),
        sa.UniqueConstraint("question_id", name="uq_quiz_answers_question_id"),
        sa.CheckConstraint(
            "user_answer IN ('A', 'B', 'C', 'D')", name="ck_quiz_answers_user_answer"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )
    op.create_table(
        "learning_progress",
        sa.Column(
            "id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            primary_key=True,
            server_default=sa.text("(REPLACE(UUID(), '-', ''))"),
        ),
        sa.Column(
            "user_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "topic_id",
            sa.Uuid(as_uuid=True, native_uuid=False),
            sa.ForeignKey("topics.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("total_quizzes", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("correct_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "mastery_percent", sa.Numeric(5, 2), nullable=False, server_default=sa.text("0.00")
        ),
        sa.Column("last_studied_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.UniqueConstraint("user_id", "topic_id", name="uq_learning_progress_user_id_topic_id"),
        sa.CheckConstraint("total_quizzes >= 0", name="ck_learning_progress_total_quizzes"),
        sa.CheckConstraint("correct_count >= 0", name="ck_learning_progress_correct_count"),
        sa.CheckConstraint("total_count >= 0", name="ck_learning_progress_total_count"),
        sa.CheckConstraint(
            "correct_count <= total_count", name="ck_learning_progress_correct_count_total_count"
        ),
        sa.CheckConstraint(
            "mastery_percent BETWEEN 0 AND 100", name="ck_learning_progress_mastery_percent"
        ),
        mysql_engine="InnoDB",
        mysql_charset="utf8mb4",
        mysql_collate="utf8mb4_0900_as_cs",
    )


def downgrade() -> None:
    op.drop_table("learning_progress")
    op.drop_table("quiz_answers")
    op.drop_table("quiz_questions")
    op.drop_table("quizzes")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("document_chunks")
    op.drop_table("documents")
    op.drop_table("topics")
    op.drop_table("subjects")
    op.drop_table("users")
