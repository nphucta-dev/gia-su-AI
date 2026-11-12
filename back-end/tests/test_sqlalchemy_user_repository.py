from unittest.mock import Mock

import pymysql
import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.sqlalchemy_user_repository import SqlAlchemyUserRepository
from app.utils.errors import DuplicateEmailError

pytestmark = pytest.mark.anyio


@pytest.mark.parametrize("key", ["uq_users_email", "users.uq_users_email"])
async def test_mysql_duplicate_email_preserves_registration_error(key):
    sessions = Mock()
    driver_error = pymysql.err.IntegrityError(
        1062, f"Duplicate entry 'an@example.com' for key '{key}'"
    )
    sessions.begin.side_effect = IntegrityError("INSERT INTO users", {}, driver_error)
    repository = SqlAlchemyUserRepository(sessions)

    with pytest.raises(DuplicateEmailError):
        await repository.create(
            name="An", email="AN@example.com", password_hash="hash", role="LEARNER"
        )


@pytest.mark.parametrize(
    ("code", "message"),
    [
        (1062, "Duplicate entry 'id' for key 'users.PRIMARY'"),
        (1452, "Cannot add or update a child row: a foreign key constraint fails"),
    ],
)
async def test_other_mysql_integrity_errors_are_not_reported_as_duplicate_email(code, message):
    sessions = Mock()
    error = IntegrityError("INSERT INTO users", {}, pymysql.err.IntegrityError(code, message))
    sessions.begin.side_effect = error
    repository = SqlAlchemyUserRepository(sessions)

    with pytest.raises(IntegrityError) as failure:
        await repository.create(
            name="An", email="an@example.com", password_hash="hash", role="LEARNER"
        )
    assert failure.value is error
