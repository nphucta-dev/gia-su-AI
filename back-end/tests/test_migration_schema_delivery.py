"""TK-085: the distributable MySQL schema must match models and migration head."""

import importlib.util
from pathlib import Path
import re

from alembic.config import Config
from alembic.script import ScriptDirectory
import pytest
from sqlalchemy.dialects import mysql
from sqlalchemy.schema import CreateIndex, CreateTable

import app.models
from app.db.base import Base

BACKEND_DIR = Path(__file__).resolve().parents[1]
SCHEMA = (BACKEND_DIR.parent / "database/schema.sql").read_text(encoding="utf-8")


def normalized_lines(statement):
    # SQLAlchemy may emit table constraints in a different order; their content
    # and columns must still match the checked-in, directly importable artifact.
    return {
        " ".join(line.strip().rstrip(",;").split())
        for line in statement.splitlines() if line.strip()
    }


def test_schema_delivery_contains_exactly_eleven_business_tables_and_version_table():
    tables = re.findall(r"CREATE TABLE\s+(\w+)\s*\(", SCHEMA)
    assert len(tables) == len(set(tables)) == 12
    assert set(tables) == set(Base.metadata.tables) | {"alembic_version"}
    assert SCHEMA.count("AUTO_INCREMENT") == 11


@pytest.mark.parametrize("table_name", sorted(Base.metadata.tables))
def test_importable_mysql_schema_preserves_each_models_columns_and_constraints(table_name):
    match = re.search(r"CREATE TABLE " + table_name + r"\s*\([\s\S]*?;", SCHEMA)
    assert match is not None
    expected = str(CreateTable(Base.metadata.tables[table_name]).compile(dialect=mysql.dialect()))
    assert normalized_lines(match.group(0)) == normalized_lines(expected)


def test_importable_schema_preserves_all_history_indexes_and_current_revision():
    indexes = {" ".join(statement.split()) for statement in re.findall(r"CREATE INDEX[^;]+", SCHEMA)}
    expected = {
        " ".join(str(CreateIndex(index).compile(dialect=mysql.dialect())).split())
        for table in Base.metadata.tables.values() for index in table.indexes
    }
    assert indexes == expected
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    scripts = ScriptDirectory.from_config(config)
    heads = scripts.get_heads()
    assert heads == ["0002_integer_ids"]
    stamps = re.findall(r"INSERT INTO alembic_version \(version_num\) VALUES \('([^']+)'\)", SCHEMA)
    assert stamps == heads
    assert [item.revision for item in scripts.walk_revisions()] == [
        "0002_integer_ids", "0001_create_learning_schema",
    ]


def test_integer_migration_remaps_every_current_foreign_key_and_table():
    path = BACKEND_DIR / "alembic/versions/0002_integer_ids.py"
    spec = importlib.util.spec_from_file_location("migration_delivery_integer_ids", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert len(migration.TABLES) == 11 and set(migration.TABLES) == set(Base.metadata.tables)
    expected = {
        (table.name, foreign_key.parent.name): foreign_key.column.table.name
        for table in Base.metadata.tables.values() for foreign_key in table.foreign_keys
    }
    assert len(expected) == 12 and migration.REFERENCES == expected
