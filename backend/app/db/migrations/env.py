"""
Alembic environment configuration.
Supports both synchronous and async SQLAlchemy engines.
"""

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Import all models so Alembic can detect the full schema.
from app.core.database import Base
from app.db import models  # noqa: F401 — registers all ORM classes

# Alembic Config object
config = context.config

# Override sqlalchemy.url from environment variable.
# Convert postgresql:// → postgresql+asyncpg:// and strip sslmode (asyncpg
# does not accept it as a URL parameter).
database_url = os.environ.get("DATABASE_URL", "")
if database_url.startswith("postgresql://"):
    database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
if "?" in database_url:
    from urllib.parse import urlparse, urlencode, parse_qs, urlunparse
    _parsed = urlparse(database_url)
    _params = parse_qs(_parsed.query, keep_blank_values=True)
    for _k in ("sslmode", "sslcert", "sslkey", "sslrootcert"):
        _params.pop(_k, None)
    database_url = urlunparse(_parsed._replace(
        query=urlencode({k: v[0] for k, v in _params.items()})
    ))
config.set_main_option("sqlalchemy.url", database_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode (no live DB connection needed)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
