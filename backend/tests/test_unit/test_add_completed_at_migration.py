"""Tests for migration 0023 — the ``completed_at`` column on ``extractions``.

The backend suite builds its schema with ``Base.metadata.create_all``, so the migration itself
never runs there. These tests exercise the real revision against a scratch database: the column
is added, its nullability is what the invariant needs, and the downgrade removes it.

The table is built with SQLAlchemy Core rather than ``Base.metadata``, because the metadata
already declares the column and the revision has to face the schema it actually faced. Reading
back is done by reflecting the real table, so the assertions describe the database rather than
the model.

SQLite stands in for Postgres because it is the only database available without Docker in this
environment. That covers the DDL shape and the round trip; Postgres-specific behaviour of the
column is covered by the integration test that runs against a real database.
"""

from __future__ import annotations

import importlib.util
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
    / "0023_add_completed_at_to_extractions.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_migration_0023", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table_as_0022_left_it() -> sa.Table:
    """``extractions`` without ``completed_at`` — the shape the revision is applied to."""
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
    )


def _reflected(engine: Engine) -> sa.Table:
    """The table as the database now holds it, so assertions describe the real schema."""
    return sa.Table("extractions", sa.MetaData(), autoload_with=engine)


@pytest.fixture
def engine() -> Engine:
    """A scratch database holding ``extractions`` at its pre-0023 shape.

    ``StaticPool`` keeps every connection on the single in-memory database; without it each new
    connection would get its own empty one and the revision would find no table.
    """
    engine = sa.create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    _table_as_0022_left_it().create(engine)
    return engine


def _run(engine: Engine, direction: str) -> None:
    migration = _load_migration()
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            getattr(migration, direction)()


def test_upgrade_adds_a_nullable_column(engine: Engine) -> None:
    """Nullable is the point: a ``pending`` extraction has not finished, so it has no end time."""
    assert "completed_at" not in _reflected(engine).c

    _run(engine, "upgrade")

    added = _reflected(engine).c.completed_at
    assert added.nullable is True
    assert isinstance(added.type, sa.DateTime)


def test_upgrade_leaves_existing_rows_untouched(engine: Engine) -> None:
    """No backfill: a row that finished before the column existed keeps its null.

    Inventing a value here — ``created_at``, or deploy time — would report a completion instant
    that was never observed. The null is the honest answer, and this pins it.
    """
    before = _table_as_0022_left_it()
    with Session(engine) as session:
        session.execute(
            before.insert().values(
                id=uuid4(),
                user_story_id=uuid4(),
                model_used="llama3.2",
                status="completed",
                user_story_status="extracted",
                raw_response="r",
                created_at=datetime(2026, 1, 1),
            )
        )

    _run(engine, "upgrade")

    with Session(engine) as session:
        value = session.execute(sa.select(_reflected(engine).c.completed_at)).scalar()
    assert value is None


def test_downgrade_removes_it_again(engine: Engine) -> None:
    """The revision is reversible, which is what lets it be reasoned about before it is run."""
    _run(engine, "upgrade")
    assert "completed_at" in _reflected(engine).c

    _run(engine, "downgrade")

    assert "completed_at" not in _reflected(engine).c


def test_the_revision_follows_0022() -> None:
    """A wrong ``down_revision`` would leave the migration chain with two heads."""
    migration = _load_migration()

    assert migration.revision == "0023"
    assert migration.down_revision == "0022"
