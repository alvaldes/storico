"""Alembic environment configuration — async support via asyncpg."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from storico.config.settings import Settings
from storico.infrastructure.database.base import _normalize_db_url
from storico.infrastructure.database.models import Base

# Alembic Config object, which provides access to the values within the .ini file.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# An explicitly supplied URL wins; the application settings are the fallback.
#
# The supplied URL arrives through ``config.attributes``, Alembic's own channel for passing values
# from a caller into this file -- not through the ``sqlalchemy.url`` option. That is deliberate:
# ``alembic.ini`` declares ``sqlalchemy.url = driver://user:pass@localhost/dbname`` as a **truthy**
# placeholder (its own comment explains why it is kept), so ``config.get_main_option(
# "sqlalchemy.url")`` is never empty and an emptiness check would silently discard the override.
# The ini placeholder is left exactly as it is, for the Alembic commands that parse the config
# without ever reaching this file.
#
# A supplied URL is used verbatim. It is the caller's contract, and ``_normalize_db_url`` rewrites
# any scheme to ``postgresql+asyncpg``, which would mangle a URL whose caller never asked for that.
_supplied_url = config.attributes.get("sqlalchemy_url")
if _supplied_url:
    config.set_main_option("sqlalchemy.url", _supplied_url)
else:
    # Normalize for asyncpg (sslmode -> ssl, strip psycopg2-only params).
    config.set_main_option("sqlalchemy.url", _normalize_db_url(Settings.load().database_url))

# Target metadata for autogenerate support.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    Configures the context with just a URL and not an Engine,
    though an Engine is acceptable here as well.  By skipping the Engine
    creation we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.
    """
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
    """Run migrations against the given synchronous-style connection."""
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations online."""
    configuration = config.get_section(config.config_ini_section, {})
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode — uses async engine."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
