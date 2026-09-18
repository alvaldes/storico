"""Tests for migration 0022 — dropping the per-user LLM settings.

The backend suite builds its schema with ``Base.metadata.create_all``, so the revision never
runs there. These tests exercise the real module against a scratch database: the JSON column
is seeded with the shapes a real deployment holds and the transform is read back.

SQLite stands in for Postgres because it is the only database available without Docker in
this environment. What is asserted here is the document transform, which is database-agnostic;
this revision touches no DDL.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import storico
from storico.infrastructure.database.models import Base

# The revision modules are not importable by name (the file name starts with a digit and
# ``versions`` is not a package), so the module is loaded from its path.
_MIGRATION_PATH = (
    Path(storico.__file__).parent
    / "infrastructure"
    / "database"
    / "alembic"
    / "versions"
    / "0022_drop_user_preference_llm.py"
)

#: A fixed timestamp, so "the revision left it alone" is an assertion about a known value.
_SAVED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

_PREFERENCES = sa.table(
    "user_preferences",
    sa.column("user_id", sa.Uuid()),
    sa.column("preferences", sa.JSON()),
    sa.column("updated_at", sa.DateTime(timezone=True)),
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_migration_0022", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine() -> Engine:
    """A scratch database holding only ``user_preferences``.

    ``StaticPool`` keeps every session and connection on the single in-memory database;
    without it each new connection would get its own empty one.
    """
    engine = sa.create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # SQLite does not enforce the foreign key to ``users`` unless it is asked to, so this
    # table can stand alone — which is all this revision reads and writes.
    Base.metadata.tables["user_preferences"].create(engine)
    return engine


def _run_migration(engine: Engine) -> None:
    """Run the revision's ``upgrade()`` against the scratch database."""
    migration = _load_migration()
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            migration.upgrade()


def _seed(engine: Engine, user_id: UUID, preferences: object) -> None:
    """Store one preferences document exactly as given."""
    # Through a Session rather than the raw connection, as the sibling migration test does:
    # the insert is built from the metadata table, so it is parameterized either way, and a
    # Session is the surface this codebase reads and writes JSON columns through.
    with Session(engine) as session:
        session.execute(
            _PREFERENCES.insert().values(
                user_id=user_id,
                preferences=preferences,
                updated_at=_SAVED_AT,
            )
        )
        session.commit()


def _stored(engine: Engine, user_id: UUID) -> object:
    """Read one stored document back."""
    with Session(engine) as session:
        return session.execute(
            sa.select(_PREFERENCES.c.preferences).where(_PREFERENCES.c.user_id == user_id)
        ).scalar_one()


def _updated_at(engine: Engine, user_id: UUID) -> object:
    """Read the row's ``updated_at``, which the revision must leave alone."""
    with Session(engine) as session:
        return session.execute(
            sa.select(_PREFERENCES.c.updated_at).where(_PREFERENCES.c.user_id == user_id)
        ).scalar_one()


class TestUpgrade:
    """What the revision leaves behind."""

    @pytest.mark.unit
    def test_it_removes_the_llm_block_and_keeps_the_rest(self, engine: Engine) -> None:
        """The whole point: the credential store stops existing, the preferences stay."""
        user_id = uuid4()
        _seed(
            engine,
            user_id,
            {
                "llm": {
                    "provider": "openai",
                    "openai": {"model": "gpt-4o-mini", "apiKey": "sk-legacy"},
                },
                "export": {"defaultFormat": "markdown"},
            },
        )

        _run_migration(engine)

        assert _stored(engine, user_id) == {"export": {"defaultFormat": "markdown"}}

    @pytest.mark.unit
    def test_a_document_without_the_block_is_untouched(self, engine: Engine) -> None:
        """A row that never had the field keeps its content."""
        user_id = uuid4()
        _seed(engine, user_id, {"export": {"defaultFormat": "json"}})

        _run_migration(engine)

        assert _stored(engine, user_id) == {"export": {"defaultFormat": "json"}}

    @pytest.mark.unit
    def test_an_empty_document_is_untouched(self, engine: Engine) -> None:
        """Nothing to remove, nothing to write."""
        user_id = uuid4()
        _seed(engine, user_id, {})

        _run_migration(engine)

        assert _stored(engine, user_id) == {}

    @pytest.mark.unit
    def test_it_is_idempotent(self, engine: Engine) -> None:
        """Running it twice is a no-op the second time, not a different result."""
        user_id = uuid4()
        _seed(engine, user_id, {"llm": {"provider": "ollama"}, "export": {}})

        _run_migration(engine)
        first = _stored(engine, user_id)
        _run_migration(engine)

        assert _stored(engine, user_id) == first == {"export": {}}

    @pytest.mark.unit
    def test_every_row_is_processed_not_only_the_first(self, engine: Engine) -> None:
        """Each user's document is cleaned, independently."""
        with_llm = [uuid4(), uuid4()]
        without = uuid4()
        for user_id in with_llm:
            _seed(engine, user_id, {"llm": {"provider": "gemini"}, "export": {}})
        _seed(engine, without, {"export": {"defaultFormat": "trello"}})

        _run_migration(engine)

        for user_id in with_llm:
            assert _stored(engine, user_id) == {"export": {}}
        assert _stored(engine, without) == {"export": {"defaultFormat": "trello"}}

    @pytest.mark.unit
    def test_the_save_timestamp_is_not_rewritten(self, engine: Engine) -> None:
        """``updated_at`` keeps answering "when did the user last save"."""
        user_id = uuid4()
        _seed(engine, user_id, {"llm": {"provider": "ollama"}})

        _run_migration(engine)

        assert _updated_at(engine, user_id) is not None
        assert _stored(engine, user_id) == {}


class TestDowngrade:
    """The revision's other direction does not invent data."""

    @pytest.mark.unit
    def test_downgrade_changes_nothing(self, engine: Engine) -> None:
        """It does not write an empty block where the removed one used to be."""
        user_id = uuid4()
        _seed(
            engine,
            user_id,
            {"llm": {"provider": "ollama"}, "export": {"defaultFormat": "json"}},
        )
        _run_migration(engine)

        migration = _load_migration()
        with engine.begin() as conn:
            context = MigrationContext.configure(conn)
            with Operations.context(context):
                assert migration.downgrade() is None

        assert _stored(engine, user_id) == {"export": {"defaultFormat": "json"}}
