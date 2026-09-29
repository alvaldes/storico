"""Tests for migration 0028 — extraction versioning.

The backend suite builds its schema with ``Base.metadata.create_all``, so the migration
itself never runs there. These tests exercise the real revision against a scratch database,
loaded by path exactly as ``test_add_completed_at_migration.py`` does.

SQLite stands in for Postgres because it is the only database available without Docker.
What SQLite can prove here is the refusal path, which raises before any DDL — the DDL and
the downgrade are proven against the Postgres container by the integration suite, because
SQLite cannot ``ADD COLUMN … NOT NULL`` without a default.
"""

from __future__ import annotations

import importlib.util
import sqlite3
from datetime import datetime
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import storico

_MIGRATION_PATH = (
    Path(storico.__file__).parent
    / "infrastructure"
    / "database"
    / "alembic"
    / "versions"
    / "0028_extraction_versioning.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_migration_0028", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _extractions_as_0027_left_them() -> sa.Table:
    """``extractions`` before ``0028`` — no version number, provider, temperature or prompt."""
    return sa.Table(
        "extractions",
        sa.MetaData(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_story_id", sa.Uuid(), nullable=False),
        sa.Column("model_used", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("user_story_status", sa.String(30), nullable=False),
        sa.Column("error_info", sa.Text(), nullable=True),
        sa.Column("prompt_config", sa.JSON(), nullable=True),
        sa.Column("raw_response", sa.Text(), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def _tasks_as_0027_left_them() -> sa.Table:
    """``tasks`` before ``0028`` — no ``extraction_id`` yet."""
    return sa.Table(
        "tasks",
        sa.MetaData(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_story_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("labels", sa.JSON(), nullable=True),
        sa.Column("dependencies", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


@pytest.fixture
def engine() -> Engine:
    """A scratch database holding both tables at their pre-0028 shape.

    ``StaticPool`` keeps every connection on the single in-memory database; without it each
    new connection would get its own empty one and the revision would find no table.
    """
    engine = sa.create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    _extractions_as_0027_left_them().create(engine)
    _tasks_as_0027_left_them().create(engine)
    return engine


def _run(engine: Engine, direction: str) -> None:
    migration = _load_migration()
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            getattr(migration, direction)()


def _seed_legacy_row_in_each_table(engine: Engine) -> None:
    """One extraction and one task — the smallest database the guard must refuse.

    The ``commit()`` is the whole point: a ``Session`` that only ``execute``\ s rolls its
    inserts back on exit, and a guard that reads a pair it believes empty walks straight
    into the DDL — which is how this test first failed, on SQLite's refusal to alter a
    constraint rather than on the sentence the guard is supposed to raise.
    """
    with Session(engine) as session:
        session.execute(
            _extractions_as_0027_left_them()
            .insert()
            .values(
                id=uuid4(),
                user_story_id=uuid4(),
                model_used="llama3.2",
                status="pending",
                user_story_status="pending_extraction",
                raw_response="",
                created_at=datetime(2026, 9, 28),
            )
        )
        session.execute(
            _tasks_as_0027_left_them()
            .insert()
            .values(
                id=uuid4(),
                user_story_id=uuid4(),
                title="Set up database schema",
                description="Create the necessary tables",
                status="backlog",
                priority="medium",
                created_at=datetime(2026, 9, 28),
                updated_at=datetime(2026, 9, 28),
            )
        )
        session.commit()


def test_the_revision_follows_0027() -> None:
    """A wrong ``down_revision`` would leave the migration chain with two heads."""
    migration = _load_migration()

    assert migration.revision == "0028"
    assert migration.down_revision == "0027"


def test_the_unit_environment_supports_returning() -> None:
    """The allocation statement uses ``RETURNING``; SQLite needs 3.35.0 for it.

    The recorded fallback if a unit environment predates it is one extra
    ``SELECT version_number WHERE id = :id`` keyed on the primary key — never on
    ``MAX``, so a concurrent run cannot be mistaken for this one.
    """
    assert sqlite3.sqlite_version_info >= (3, 35, 0)


def test_upgrade_refuses_a_populated_database(engine: Engine) -> None:
    """One row anywhere in the pair is enough: the guard raises before any DDL.

    The refusal names the no-backfill decision (D11) instead of leaving the operator to
    meet a Postgres ``NOT NULL`` error halfway through a half-migrated schema.
    """
    _seed_legacy_row_in_each_table(engine)

    with pytest.raises(RuntimeError, match="0028 refuses to run"):
        _run(engine, "upgrade")


def test_the_refusal_leaves_the_pre_0028_schema_untouched(engine: Engine) -> None:
    """No 0028 column or table may exist after the refusal — not half a migration."""
    _seed_legacy_row_in_each_table(engine)

    with pytest.raises(RuntimeError):
        _run(engine, "upgrade")

    inspector = sa.inspect(engine)
    extraction_columns = {column["name"] for column in inspector.get_columns("extractions")}
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    assert "version_number" not in extraction_columns
    assert "provider" not in extraction_columns
    assert "temperature" not in extraction_columns
    assert "prompt_rendered" not in extraction_columns
    assert "extraction_id" not in task_columns
    assert "task_invalidations" not in inspector.get_table_names()
