"""Xuất schema hiện tại mà không cần kết nối database."""

import argparse
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import Column, MetaData, PrimaryKeyConstraint, String, Table
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[2]


def export_schema(output: Path) -> None:
    dialect = mysql.dialect()
    revision = ScriptDirectory.from_config(Config(str(BACKEND_DIR / "alembic.ini"))).get_current_head()
    version_table = Table(
        "alembic_version", MetaData(), Column("version_num", String(32), nullable=False),
        PrimaryKeyConstraint("version_num", name="alembic_version_pkc"),
    )
    statements = [
        "-- Current MySQL schema. Apply only to an empty database.",
        "SET time_zone = '+00:00';",
        str(CreateTable(version_table).compile(dialect=dialect)).strip() + ";",
    ]
    for table in Base.metadata.sorted_tables:
        statements.append(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in sorted(table.indexes, key=lambda item: item.name):
            statements.append(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
    statements.append(f"INSERT INTO alembic_version (version_num) VALUES ('{revision}');")
    rendered = "\n\n".join(statements)
    output.write_text("\n".join(line.rstrip() for line in rendered.splitlines()) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Xuất SQL MySQL hiện tại cho database trống.")
    parser.add_argument("--output", type=Path, default=BACKEND_DIR.parent / "database/schema.sql")
    export_schema(parser.parse_args().output)
