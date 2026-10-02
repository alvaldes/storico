"""Tests for migration 0029 — the ``story_deletions`` audit table.

The backend suite builds its schema with ``Base.metadata.create_all``, so the migration itself
never runs there. These tests exercise the real revision against a scratch database: the table
is created with the shape the design settles, the index is the owner-resolved composite, and
the downgrade removes the table again.

The table is inspected by reflecting the real schema, so the assertions describe the database
rather than the model. SQLite stands in for Postgres because it is the only database available
without Docker in this environment. That covers the DDL shape and the round trip; the
*behaviour* of the ``ON DELETE SET NULL`` actor reference (an account deletion nulls
``deleted_by`` instead of erasing the record) is NOT proven here — SQLite does not enforce
foreign keys by default, so a local assertion would pass for the wrong reason. Task 4.16 and
the integration suite (Docker/Postgres) own that behaviour.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Engine
from sqlalchemy.pool import StaticPool

import storico
from storico.infrastructure.database.models.base import Base

_MIGRATION_PATH = (
    Path(storico.__file__).parent
    / "infrastructure"
    / "database"
    / "alembic"
    / "versions"
    / "0029_story_deletions.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_migration_0029", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine() -> Engine:
    """A scratch database. The table is new in 0029, so the pre-state is empty.

    ``StaticPool`` keeps every connection on the single in-memory database; without it each new
    connection would get its own empty one and the revision would create a table nobody sees.
    """
    return sa.create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )


def _run(engine: Engine, direction: str) -> None:
    migration = _load_migration()
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            getattr(migration, direction)()


def test_the_revision_follows_0028() -> None:
    """A wrong ``down_revision`` would leave the migration chain with two heads."""
    migration = _load_migration()

    assert migration.revision == "0029"
    assert migration.down_revision == "0028"


def _columns_of(engine: Engine) -> dict[str, dict]:
    """The table's columns as the database now holds them.

    ``Table(..., autoload_with=...)`` is not used here: reflecting the table would make
    SQLAlchemy also resolve the referenced ``users`` table, which does not exist in this
    scratch database. Column-level inspection describes the real schema without that walk.
    """
    inspector = sa.inspect(engine)
    return {column["name"]: column for column in inspector.get_columns("story_deletions")}


def test_upgrade_creates_the_table_with_the_designed_shape(engine: Engine) -> None:
    """The record carries the story's identity as values — no FK to the story it records."""
    _run(engine, "upgrade")

    columns = _columns_of(engine)
    expected = {
        "id",
        "story_id",
        "project_id",
        "workspace_id",
        "actor",
        "feature",
        "benefit",
        "version_numbers",
        "deleted_by",
        "deleted_at",
    }
    assert set(columns) == expected
    # The audit trail's timestamp is the moment of the deletion: never null, never backfilled.
    assert columns["deleted_at"]["nullable"] is False
    # The actor reference is nullable by design: an account deletion nulls it (SET NULL) and
    # the record stays.
    assert columns["deleted_by"]["nullable"] is True


def test_upgrade_declares_only_the_actor_foreign_key(engine: Engine) -> None:
    """The only FK is ``deleted_by -> users.id``.

    A foreign key to ``stories``, ``projects`` or ``extractions`` would destroy the record with
    the very delete it records — the whole point of this table is that it survives it. The
    reflected set is checked against ``users`` alone, which pins the absence of the story and
    extraction references on the migration side, not just the model side.
    """
    _run(engine, "upgrade")

    inspector = sa.inspect(engine)
    foreign_keys = inspector.get_foreign_keys("story_deletions")
    assert len(foreign_keys) == 1
    fk = foreign_keys[0]
    assert fk["referred_table"] == "users"
    assert fk["constrained_columns"] == ["deleted_by"]
    assert fk["referred_columns"] == ["id"]
    # The ondelete action travels in the DDL; SQLite reflects it without enforcing it, so
    # this pins the declaration only — the behaviour (an account deletion nulls deleted_by
    # and the record stays) is owned by the Postgres integration suite (task 4.16).
    assert fk["options"].get("ondelete") == "SET NULL"


def test_upgrade_creates_the_owner_resolved_composite_index(engine: Engine) -> None:
    """``(workspace_id, deleted_at)`` — the owner's decision, recorded in tasks.md 4.10.

    The only plausible query against an audit record is "what was deleted in this workspace,
    newest first"; ``story_id`` is not a lookup the UI can perform because the story is gone.
    """
    _run(engine, "upgrade")

    inspector = sa.inspect(engine)
    indexes = {index["name"]: index for index in inspector.get_indexes("story_deletions")}
    index = indexes["ix_story_deletions_workspace_deleted_at"]
    assert index["column_names"] == ["workspace_id", "deleted_at"]


def test_downgrade_drops_the_table(engine: Engine) -> None:
    """The revision is reversible, which is what lets it be reasoned about before it is run."""
    _run(engine, "upgrade")
    assert "story_deletions" in sa.inspect(engine).get_table_names()

    _run(engine, "downgrade")

    assert "story_deletions" not in sa.inspect(engine).get_table_names()


def test_the_model_declares_no_foreign_key_to_stories_or_extractions() -> None:
    """The model itself must not grow the FK a future "clean up" would be tempted to add.

    A future edit that adds ``ForeignKey("stories.id")`` (or ``projects``/``extractions``)
    silently turns every audit record into nothing the moment its story is deleted. This pins
    the absence: the model's complete FK set is exactly the actor reference to ``users``.
    """
    from storico.infrastructure.database.models.story_deletion import StoryDeletionModel

    targets = {fk.target_fullname for fk in StoryDeletionModel.__table__.foreign_keys}
    assert targets == {"users.id"}
    for fk in StoryDeletionModel.__table__.foreign_keys:
        assert not fk.target_fullname.startswith(("stories.", "extractions.", "projects."))


def test_the_model_builds_in_the_sqlite_unit_schema(engine: Engine) -> None:
    """``version_numbers`` is ``sa.JSON``, so ``Base.metadata.create_all`` constructs the table.

    A Postgres ``ARRAY`` would look more correct but does not exist on SQLite, where the unit
    suite builds its schema — the table could not be constructed at all. Slice (a) made the
    same portability choice. The round trip below also exercises the write path the deletion
    service will use, including the nullable actor reference.
    """
    from storico.infrastructure.database.models.story_deletion import StoryDeletionModel

    Base.metadata.create_all(engine)
    story_id, project_id, workspace_id = uuid4(), uuid4(), uuid4()
    deleted_at = datetime(2026, 9, 30, 12, 0, 0, tzinfo=UTC)

    with sa.orm.Session(engine) as session:
        session.add(
            StoryDeletionModel(
                id=uuid4(),
                story_id=story_id,
                project_id=project_id,
                workspace_id=workspace_id,
                actor="As a user",
                feature="I want to log in",
                benefit="so that I can access my account",
                version_numbers=[1, 2],
                deleted_by=None,
                deleted_at=deleted_at,
            )
        )
        session.commit()

    with sa.orm.Session(engine) as session:
        row = session.execute(sa.select(StoryDeletionModel)).scalar_one()
    assert row.story_id == story_id
    assert row.version_numbers == [1, 2]
    assert row.deleted_by is None
    # SQLite stores and returns DATETIME values naive, so the timezone comparison is done on
    # the naive value; the TIMESTAMPTZ behaviour itself is a Postgres property this suite
    # cannot prove (task 4.16 / CI own it).
    assert row.deleted_at.replace(tzinfo=UTC) == deleted_at
