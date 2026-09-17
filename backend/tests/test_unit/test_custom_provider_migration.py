"""Tests for migration 0021 — the custom_providers table and its backfill.

The backend suite builds its schema with ``Base.metadata.create_all``, so the
migration itself never runs there. These tests exercise the real revision against
a scratch database: the DDL is applied, the backfill runs, and the resulting table
is compared against the ORM model so the two cannot drift apart.

SQLite stands in for Postgres because it is the only database available without
Docker in this environment. That is sufficient for what is asserted here — column
shape, constraint and index declarations, and the backfill's filtering — but it
means Postgres-specific behaviour of the DDL is not covered; see the residual risk
noted in the feature document.
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

# The revision modules are not importable by name (the file name starts with a
# digit and ``versions`` is not a package), so the module is loaded from its path.
_MIGRATION_PATH = (
    Path(storico.__file__).parent
    / "infrastructure"
    / "database"
    / "alembic"
    / "versions"
    / "0021_add_custom_providers.py"
)

# A lightweight view of the registry table, for reads that need no ORM entity.
_REGISTRY = sa.table(
    "custom_providers",
    sa.column("id", sa.Uuid()),
    sa.column("workspace_id", sa.Uuid()),
    sa.column("name", sa.String(50)),
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_migration_0021", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine() -> Engine:
    """A scratch database holding only the tables the revision depends on.

    Creating the whole metadata would create ``custom_providers`` too, and the
    revision's own ``create_table`` would then fail on an existing table.

    ``StaticPool`` keeps every session and connection on the single in-memory
    database; without it each new connection would get its own empty one.
    """
    engine = sa.create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    Base.metadata.tables["workspaces"].create(engine)
    Base.metadata.tables["workspace_llm_configs"].create(engine)
    return engine


def _seed_config(engine: Engine, workspace_id: UUID, provider: str) -> None:
    """Insert one workspace and its LLM config row."""
    now = datetime.now(UTC)
    with Session(engine) as session:
        session.execute(
            Base.metadata.tables["workspaces"]
            .insert()
            .values(
                id=workspace_id,
                name=f"ws-{str(workspace_id)[:8]}",
                slug=f"ws-{str(workspace_id)[:8]}",
                owner_id=uuid4(),
                created_at=now,
                updated_at=now,
            )
        )
        session.execute(
            Base.metadata.tables["workspace_llm_configs"]
            .insert()
            .values(
                id=uuid4(),
                workspace_id=workspace_id,
                provider=provider,
                updated_at=now,
            )
        )
        session.commit()


def _upgrade(engine: Engine) -> None:
    """Run the revision's ``upgrade()`` against the scratch database."""
    migration = _load_migration()
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            migration.upgrade()


def _registered_names(engine: Engine) -> dict[str, list[str]]:
    """Read back the registry grouped by workspace id."""
    with Session(engine) as session:
        rows = session.execute(
            sa.select(_REGISTRY.c.workspace_id, _REGISTRY.c.name).order_by(_REGISTRY.c.name)
        ).fetchall()

    grouped: dict[str, list[str]] = {}
    for workspace_id, name in rows:
        grouped.setdefault(str(workspace_id), []).append(name)
    return grouped


class TestBackfill:
    """The one-time copy of already-configured custom provider names."""

    def test_known_providers_are_not_registered(self, engine: Engine) -> None:
        """The four first-class names are not custom, so they get no row."""
        for name in ("ollama", "openai", "anthropic", "gemini"):
            _seed_config(engine, uuid4(), name)

        _upgrade(engine)

        assert _registered_names(engine) == {}

    def test_custom_names_are_copied_verbatim(self, engine: Engine) -> None:
        """An unusual but syntactically usable name is copied without rewriting it.

        Case is preserved on purpose: the name is the value the workspace config
        already holds and the value extraction matches on.
        """
        workspace_id = uuid4()
        _seed_config(engine, workspace_id, "Mistral")

        _upgrade(engine)

        assert _registered_names(engine) == {str(workspace_id): ["Mistral"]}

    def test_whitespace_is_trimmed(self, engine: Engine) -> None:
        """Surrounding whitespace would otherwise make an unselectable entry."""
        workspace_id = uuid4()
        _seed_config(engine, workspace_id, "  groq  ")

        _upgrade(engine)

        assert _registered_names(engine) == {str(workspace_id): ["groq"]}

    def test_blank_names_are_skipped(self, engine: Engine) -> None:
        """An empty or whitespace-only provider has no name to register."""
        _seed_config(engine, uuid4(), "")
        _seed_config(engine, uuid4(), "   ")

        _upgrade(engine)

        assert _registered_names(engine) == {}

    def test_the_same_name_survives_in_two_workspaces(self, engine: Engine) -> None:
        """Uniqueness is per workspace, so a shared vendor name is not a conflict."""
        first, second = uuid4(), uuid4()
        _seed_config(engine, first, "deepseek")
        _seed_config(engine, second, "deepseek")

        _upgrade(engine)

        assert _registered_names(engine) == {
            str(first): ["deepseek"],
            str(second): ["deepseek"],
        }

    def test_a_mixed_batch_keeps_only_the_custom_names(self, engine: Engine) -> None:
        """Known, blank, and custom rows in one run produce exactly the custom rows."""
        custom_a, custom_b = uuid4(), uuid4()
        _seed_config(engine, custom_a, "deepseek")
        _seed_config(engine, custom_b, "groq")
        _seed_config(engine, uuid4(), "gemini")
        _seed_config(engine, uuid4(), "")

        _upgrade(engine)

        assert _registered_names(engine) == {
            str(custom_a): ["deepseek"],
            str(custom_b): ["groq"],
        }

    def test_backfilled_rows_carry_ids(self, engine: Engine) -> None:
        """The ids come from the application's generator, not from the database.

        The id column has no server default, so a backfill that forgot to supply
        one would fail rather than insert a wrong-shaped id.
        """
        _seed_config(engine, uuid4(), "deepseek")

        _upgrade(engine)

        with Session(engine) as session:
            ids = session.execute(sa.select(_REGISTRY.c.id)).scalars().all()
        assert len(ids) == 1
        # SQLite stores a Uuid column as 32 hex characters without dashes.
        assert len(str(ids[0]).replace("-", "")) == 32


class TestMigratedTableMatchesTheModel:
    """The revision's DDL and the ORM model must describe the same table."""

    def test_columns_and_nullability_match(self, engine: Engine) -> None:
        _upgrade(engine)

        migrated = sa.inspect(engine).get_columns("custom_providers")
        model = Base.metadata.tables["custom_providers"]

        assert [c["name"] for c in migrated] == [c.name for c in model.columns]
        assert {c["name"]: c["nullable"] for c in migrated} == {
            c.name: c.nullable for c in model.columns
        }

    def test_primary_key_matches(self, engine: Engine) -> None:
        _upgrade(engine)

        migrated = sa.inspect(engine).get_pk_constraint("custom_providers")
        model = Base.metadata.tables["custom_providers"]

        assert migrated["constrained_columns"] == [c.name for c in model.primary_key.columns]

    def test_unique_constraint_matches(self, engine: Engine) -> None:
        """The composite uniqueness is what keeps a workspace's names distinct."""
        _upgrade(engine)

        migrated = sa.inspect(engine).get_unique_constraints("custom_providers")
        model = Base.metadata.tables["custom_providers"]
        model_unique = [
            sorted(c.name for c in constraint.columns)
            for constraint in model.constraints
            if isinstance(constraint, sa.UniqueConstraint)
        ]

        assert sorted(sorted(u["column_names"]) for u in migrated) == model_unique

    def test_workspace_index_matches(self, engine: Engine) -> None:
        _upgrade(engine)

        migrated = sa.inspect(engine).get_indexes("custom_providers")
        model = Base.metadata.tables["custom_providers"]
        model_indexes = {index.name: [c.name for c in index.columns] for index in model.indexes}

        assert {index["name"]: index["column_names"] for index in migrated} == model_indexes

    def test_foreign_key_targets_the_workspace_and_cascades(self, engine: Engine) -> None:
        _upgrade(engine)

        migrated = sa.inspect(engine).get_foreign_keys("custom_providers")

        assert len(migrated) == 1
        assert migrated[0]["referred_table"] == "workspaces"
        assert migrated[0]["constrained_columns"] == ["workspace_id"]
        # ``options`` is optional in the reflected constraint shape, so it is
        # probed rather than assumed — a missing key means no ON DELETE clause.
        assert migrated[0].get("options", {}).get("ondelete") == "CASCADE"


def test_the_revision_chains_onto_0020() -> None:
    """The new table is reachable from the migration chain's head."""
    migration = _load_migration()

    assert migration.revision == "0021"
    assert migration.down_revision == "0020"
