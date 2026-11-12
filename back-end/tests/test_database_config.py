from sqlalchemy.engine import make_url

from app.config import load_database_url, normalize_database_url
from app.db.database import create_database_engine


def test_provider_mysql_url_uses_pymysql_without_changing_credentials(monkeypatch):
    raw = "mysql://app:p%40ssword@localhost:3306/gia_su_ai?ssl-mode=REQUIRED"
    monkeypatch.setenv("DATABASE_URL", raw)
    normalized = make_url(load_database_url())
    assert normalized.drivername == "mysql+pymysql"
    assert normalized.username == "app" and normalized.password == "p@ssword"
    assert normalized.host == "localhost" and normalized.database == "gia_su_ai"
    assert "ssl-mode" not in normalized.query
    engine = create_database_engine(load_database_url())
    try:
        _, arguments = engine.dialect.create_connect_args(engine.url)
        assert arguments["ssl"]["check_hostname"] is False
        assert arguments["charset"] == "utf8mb4"
    finally:
        engine.dispose()


def test_normalizing_a_configured_url_twice_is_idempotent():
    first = normalize_database_url("mysql://app:password@localhost/test?ssl-mode=REQUIRED")
    assert normalize_database_url(first) == first


def test_local_mysql_does_not_enable_tls_when_not_requested():
    engine = create_database_engine("mysql://app:password@localhost/test")
    try:
        _, arguments = engine.dialect.create_connect_args(engine.url)
        assert "ssl" not in arguments
    finally:
        engine.dispose()
