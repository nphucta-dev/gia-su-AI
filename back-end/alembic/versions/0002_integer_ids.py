"""Chuyển UUID sang INT AUTO_INCREMENT, giữ dữ liệu và liên kết hiện có.

Dừng ứng dụng và sao lưu database trước khi chạy: MySQL DDL có implicit commit.
Revision này cần kết nối thật để kiểm tra và ánh xạ các ID hiện có.
"""

import json

from alembic import context, op
import sqlalchemy as sa

revision = "0002_integer_ids"
down_revision = "0001_create_learning_schema"
branch_labels = None
depends_on = None

TABLES = (
    "users", "subjects", "topics", "documents", "document_chunks", "chat_sessions",
    "chat_messages", "quizzes", "quiz_questions", "quiz_answers", "learning_progress",
)
REFERENCES = {
    ("topics", "subject_id"): "subjects",
    ("documents", "topic_id"): "topics",
    ("document_chunks", "document_id"): "documents",
    ("chat_sessions", "user_id"): "users",
    ("chat_sessions", "topic_id"): "topics",
    ("chat_messages", "session_id"): "chat_sessions",
    ("quizzes", "user_id"): "users",
    ("quizzes", "topic_id"): "topics",
    ("quiz_questions", "quiz_id"): "quizzes",
    ("quiz_answers", "question_id"): "quiz_questions",
    ("learning_progress", "user_id"): "users",
    ("learning_progress", "topic_id"): "topics",
}


def remap_source_refs(refs, documents, chunks):
    """Đổi ID nguồn đã biết; giữ nguyên thông tin khác và nguồn đã bị xóa."""
    if not isinstance(refs, list):
        return refs
    result = []
    for reference in refs:
        if not isinstance(reference, dict):
            result.append(reference)
            continue
        reference = reference.copy()
        for key, mapping in (("document_id", documents), ("chunk_id", chunks)):
            value = reference.get(key)
            if isinstance(value, str):
                normalized = value.replace("-", "").lower()
                if normalized in mapping:
                    reference[key] = mapping[normalized]
        result.append(reference)
    return result


def upgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError("Migration 0002 cần kết nối MySQL thật; không hỗ trợ --sql.")
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    quote = bind.dialect.identifier_preparer.quote
    available = set(inspector.get_table_names())
    if not set(TABLES).issubset(available):
        raise RuntimeError("Database chưa có đủ 11 bảng của migration 0001.")

    columns = {table: {col["name"]: col for col in inspector.get_columns(table)} for table in TABLES}
    for table in TABLES:
        if any(name.startswith(("_ai_", "_old_")) for name in columns[table]):
            raise RuntimeError("Có cột migration dở dang. Hãy kiểm tra/khôi phục backup trước khi chạy lại.")
        if inspector.get_pk_constraint(table)["constrained_columns"] != ["id"]:
            raise RuntimeError(f"Khóa chính của {table} không đúng thiết kế.")

    foreign_keys = []
    for table in available:
        for foreign_key in inspector.get_foreign_keys(table):
            if table not in TABLES and foreign_key["referred_table"] in TABLES:
                raise RuntimeError("Có bảng ngoài dự án tham chiếu ID; cần bổ sung ánh xạ trước.")
            if table in TABLES:
                if foreign_key.get("referred_schema") not in (None, bind.engine.url.database):
                    raise RuntimeError("Có khóa ngoại liên database; cần kiểm tra thủ công trước.")
                foreign_keys.append((table, foreign_key))
    actual_refs = {
        (table, tuple(fk["constrained_columns"]), fk["referred_table"], tuple(fk["referred_columns"]))
        for table, fk in foreign_keys
    }
    expected_refs = {(table, (column,), parent, ("id",)) for (table, column), parent in REFERENCES.items()}
    if actual_refs != expected_refs or any(not fk["name"] for _, fk in foreign_keys):
        raise RuntimeError("Các khóa ngoại hiện có không khớp thiết kế 12 liên kết.")

    counts = {table: bind.scalar(sa.text(f"SELECT COUNT(*) FROM {quote(table)}")) for table in TABLES}
    if any(count >= 2**31 - 1 for count in counts.values()):
        raise RuntimeError("Dữ liệu vượt miền INT; cần thiết kế BIGINT trước khi chuyển đổi.")
    for table in TABLES:
        column = columns[table]["id"]
        if not isinstance(column["type"], sa.String) or column["type"].length != 32:
            raise RuntimeError(f"ID của {table} không còn là UUID CHAR(32) theo migration 0001.")

    indexes = []
    for table in TABLES:
        changed_columns = {"id"} | {column for (child, column) in REFERENCES if child == table}
        descending = {}
        # MySQL dialect reflection có thể bỏ mất DESC; SHOW INDEX giữ Collation=D.
        for entry in bind.exec_driver_sql(f"SHOW INDEX FROM {quote(table)}").mappings():
            if entry["Collation"] == "D":
                descending.setdefault(entry["Key_name"], {})[entry["Column_name"]] = ("desc",)
        for index in inspector.get_indexes(table):
            if index["name"].startswith("_ai_pk_"):
                raise RuntimeError("Có index migration dở dang; cần kiểm tra backup trước khi chạy lại.")
            if not all(index["column_names"]):
                raise RuntimeError("Có functional index ngoài thiết kế; cần kiểm tra thủ công.")
            if set(index["column_names"]) & changed_columns:
                index = dict(index)
                index["column_sorting"] = descending.get(index["name"], index.get("column_sorting", {}))
                indexes.append((table, index))

    # Thêm số tự tăng bên cạnh UUID; UUID vẫn giữ nguyên trong lúc ánh xạ.
    for table in TABLES:
        op.execute(sa.text(
            f"ALTER TABLE {quote(table)} ADD COLUMN _ai_id INT NOT NULL AUTO_INCREMENT, "
            f"ADD UNIQUE INDEX {quote('_ai_pk_' + table)} (_ai_id)"
        ))
    for (table, column), parent in REFERENCES.items():
        new_column = "_ai_" + column
        op.add_column(table, sa.Column(new_column, sa.Integer(), nullable=True))
        op.execute(sa.text(
            f"UPDATE {quote(table)} AS child JOIN {quote(parent)} AS parent "
            f"ON child.{quote(column)} = parent.id "
            f"SET child.{quote(new_column)} = parent._ai_id"
        ))
        missing = bind.scalar(sa.text(
            f"SELECT COUNT(*) FROM {quote(table)} "
            f"WHERE {quote(column)} IS NOT NULL AND {quote(new_column)} IS NULL"
        ))
        if missing:
            raise RuntimeError(f"Không ánh xạ được khóa ngoại {table}.{column}; dừng migration.")

    # source_refs chứa ID trong JSON nên không được MySQL tự cập nhật theo FK.
    mappings = {}
    for table in ("documents", "document_chunks"):
        mappings[table] = {
            str(row.id).replace("-", "").lower(): row._ai_id
            for row in bind.execute(sa.text(f"SELECT id, _ai_id FROM {quote(table)}"))
        }
    messages = bind.execute(sa.text("SELECT id, source_refs FROM chat_messages")).all()
    for message in messages:
        refs = json.loads(message.source_refs) if isinstance(message.source_refs, str) else message.source_refs
        converted = remap_source_refs(refs, mappings["documents"], mappings["document_chunks"])
        if converted != refs:
            bind.execute(
                sa.text("UPDATE chat_messages SET source_refs = :refs WHERE id = :id"),
                {"refs": json.dumps(converted, ensure_ascii=False), "id": message.id},
            )

    for table, foreign_key in foreign_keys:
        op.drop_constraint(foreign_key["name"], table, type_="foreignkey")
    for table, index in indexes:
        op.drop_index(index["name"], table_name=table)

    for table in TABLES:
        op.execute(sa.text(
            f"ALTER TABLE {quote(table)} DROP PRIMARY KEY, "
            "CHANGE COLUMN id _old_id CHAR(32) NOT NULL, "
            "CHANGE COLUMN _ai_id id INT NOT NULL AUTO_INCREMENT, ADD PRIMARY KEY (id)"
        ))
        op.drop_index("_ai_pk_" + table, table_name=table)
    for table, column in REFERENCES:
        nullable = "NULL" if columns[table][column]["nullable"] else "NOT NULL"
        op.execute(sa.text(
            f"ALTER TABLE {quote(table)} "
            f"CHANGE COLUMN {quote(column)} {quote('_old_' + column)} CHAR(32) {nullable}, "
            f"CHANGE COLUMN {quote('_ai_' + column)} {quote(column)} INT {nullable}"
        ))

    for table, index in indexes:
        sorting = index.get("column_sorting", {})
        expressions = [
            sa.column(column).desc() if "desc" in sorting.get(column, ()) else column
            for column in index["column_names"]
        ]
        op.create_index(index["name"], table, expressions, unique=bool(index["unique"]))
    for table, foreign_key in foreign_keys:
        op.create_foreign_key(
            foreign_key["name"], table, foreign_key["referred_table"],
            foreign_key["constrained_columns"], foreign_key["referred_columns"],
            **foreign_key.get("options", {}),
        )

    for table, original_count in counts.items():
        if bind.scalar(sa.text(f"SELECT COUNT(*) FROM {quote(table)}")) != original_count:
            raise RuntimeError(f"Số lượng bản ghi {table} đã thay đổi; cần kiểm tra backup.")
    for (table, column), parent in REFERENCES.items():
        invalid = bind.scalar(sa.text(
            f"SELECT COUNT(*) FROM {quote(table)} AS child "
            f"LEFT JOIN {quote(parent)} AS parent ON child.{quote(column)} = parent.id "
            f"WHERE child.{quote(column)} IS NOT NULL AND parent.id IS NULL"
        ))
        if invalid:
            raise RuntimeError(f"Liên kết {table}.{column} không hợp lệ sau chuyển đổi.")

    # Chỉ bỏ cột UUID dự phòng khi số hàng và toàn bộ liên kết đã được xác nhận.
    for table, column in REFERENCES:
        op.drop_column(table, "_old_" + column)
    for table in TABLES:
        op.drop_column(table, "_old_id")


def downgrade() -> None:
    raise RuntimeError("Không tự khôi phục UUID cũ. Cần dùng backup được tạo trước migration 0002.")
