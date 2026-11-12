import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Integer

import app.models
from app.db.base import Base
from app.repositories.user_repository import InMemoryUserRepository, parse_user_id
from app.services.token_service import TokenService


@pytest.mark.parametrize(
    "value",
    [None, True, False, 0, -1, 1.0, "", "-1", " 1", "1.0", "١", "a" * 32, 2**31, "2147483648"],
)
def test_invalid_user_ids_are_rejected(value):
    assert parse_user_id(value) is None


@pytest.mark.anyio
async def test_user_ids_increment_and_jwt_subject_stays_a_string():
    repository = InMemoryUserRepository()
    users = [
        await repository.create(
            name="Learner", email=f"user{number}@example.com",
            password_hash="hash", role="LEARNER",
        )
        for number in range(3)
    ]
    assert [user.id for user in users] == [1, 2, 3]
    assert await repository.find_by_id("2") == users[1]
    assert await repository.find_by_id(2) == users[1]
    service = TokenService(secret="integer-id-test-secret-" + "x" * 40)
    token = service.create_access_token(users[1].id)
    assert service.verify_access_token(token.access_token).user_id == "2"


def test_every_primary_and_foreign_key_uses_integer():
    assert len(Base.metadata.tables) == 11
    for table in Base.metadata.tables.values():
        assert isinstance(table.c.id.type, Integer)
        assert table.c.id.autoincrement is True and table.c.id.server_default is None
        for foreign_key in table.foreign_keys:
            assert isinstance(foreign_key.parent.type, Integer)
            assert isinstance(foreign_key.column.type, Integer)


def load_migration():
    path = Path(__file__).resolve().parents[1] / "alembic/versions/0002_integer_ids.py"
    spec = importlib.util.spec_from_file_location("integer_id_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    return migration


def test_source_reference_ids_are_remapped_without_losing_other_fields():
    migration = load_migration()
    old_document = "a" * 32
    old_chunk = "b" * 32
    original = [
        {"document_id": old_document, "chunk_id": old_chunk, "title": "Source", "page": 2},
        {"document_id": "removed-source", "title": "Archive"},
    ]
    result = migration.remap_source_refs(original, {old_document: 1}, {old_chunk: 2})
    assert result == [
        {"document_id": 1, "chunk_id": 2, "title": "Source", "page": 2}, original[1],
    ]
    assert original[0]["document_id"] == old_document


def test_integer_migration_requires_a_live_connection_and_has_no_destructive_downgrade(monkeypatch):
    migration = load_migration()
    monkeypatch.setattr(migration.context, "is_offline_mode", lambda: True)
    with pytest.raises(RuntimeError, match="không hỗ trợ --sql"):
        migration.upgrade()
    with pytest.raises(RuntimeError, match="backup"):
        migration.downgrade()
