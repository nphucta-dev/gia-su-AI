from alembic import context
from sqlalchemy import create_engine, pool

import app.models  # Đăng ký đủ model trước khi dùng metadata.
from app.config import load_database_url
from app.db.base import Base
from app.db.types import UTCDateTime

config = context.config
target_metadata = Base.metadata


def render_item(type_, obj, autogen_context):
    if type_ == "type" and isinstance(obj, UTCDateTime):
        autogen_context.imports.add("from sqlalchemy.dialects import mysql")
        return "mysql.DATETIME(fsp=6)"
    return False


def configure(connection=None):
    options = {
        "target_metadata": target_metadata,
        "compare_type": True,
        "compare_server_default": True,
        "render_item": render_item,
    }
    if connection is None:
        context.configure(
            url=load_database_url(),
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            **options,
        )
    else:
        context.configure(connection=connection, **options)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    configure()
else:
    connection = config.attributes.get("connection")
    if connection is not None:
        configure(connection)
    else:
        engine = create_engine(
            load_database_url(),
            poolclass=pool.NullPool,
            connect_args={"init_command": "SET time_zone = '+00:00'"},
        )
        try:
            with engine.connect() as connection:
                configure(connection)
        finally:
            engine.dispose()
