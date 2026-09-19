"""Tests for migration 0024 — encrypting stored workspace LLM credentials.

The backend suite builds its schema with ``Base.metadata.create_all``, so the revision never
runs there. These tests exercise the real migration against a scratch database, which is the
only place its refusal, its idempotency and its downgrade can be observed at all.

The master key is supplied through the application settings, exactly as the migration reads
it, so the "no key configured" case is the real deployment condition rather than a patched
stub.
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from uuid import UUID, uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from cryptography.fernet import Fernet
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import storico
from storico.config.settings import _reset_settings_cache

_MIGRATION_PATH = (
    Path(storico.__file__).parent
    / "infrastructure"
    / "database"
    / "alembic"
    / "versions"
    / "0024_encrypt_workspace_api_keys.py"
)

_PLAINTEXT = "sk-live-0123456789abcdef"
_MASTER_KEY = Fernet.generate_key().decode("ascii")


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("_migration_0024", _MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _table_as_0023_left_it() -> sa.Table:
    """``workspace_llm_configs`` at the shape revision 0024 is applied to."""
    return sa.Table(
        "workspace_llm_configs",
        sa.MetaData(),
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=True),
        sa.Column("max_tokens", sa.Integer(), nullable=True),
        sa.Column("base_url", sa.String(500), nullable=True),
        sa.Column("api_key", sa.String(500), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def _reflected(engine: Engine) -> sa.Table:
    """The table as the database now holds it, so assertions describe the real column."""
    return sa.Table("workspace_llm_configs", sa.MetaData(), autoload_with=engine)


@pytest.fixture
def engine() -> Engine:
    """A scratch database holding ``workspace_llm_configs`` at its pre-0024 shape.

    ``StaticPool`` keeps every connection on the single in-memory database; without it each
    new connection would get its own empty one and the revision would find no rows.
    """
    engine = sa.create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    _table_as_0023_left_it().create(engine)
    return engine


@pytest.fixture(autouse=True)
def master_key(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Configure a master key the way a deployment would, through the app settings."""
    monkeypatch.setenv("STORICO_ENCRYPTION_KEY", _MASTER_KEY)
    _reset_settings_cache()
    yield
    _reset_settings_cache()


def _seed(engine: Engine, api_key: str | None) -> UUID:
    """Insert one row holding ``api_key`` and return its id."""
    row_id = uuid4()
    table = _table_as_0023_left_it()
    with Session(engine) as session:
        session.execute(
            table.insert().values(
                id=row_id,
                workspace_id=uuid4(),
                provider="openai",
                api_key=api_key,
                updated_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
        session.commit()
    return row_id


def _read(engine: Engine, row_id: UUID) -> str | None:
    """The stored credential, read by reflecting the real table."""
    table = _reflected(engine)
    with Session(engine) as session:
        return session.execute(sa.select(table.c.api_key).where(table.c.id == row_id)).scalar_one()


def _run(engine: Engine, direction: str) -> None:
    migration = _load_migration()
    with engine.begin() as conn:
        context = MigrationContext.configure(conn)
        with Operations.context(context):
            getattr(migration, direction)()


def test_upgrade_encrypts_a_plaintext_credential(engine: Engine) -> None:
    """The whole point: a stored credential stops being readable in the column."""
    row_id = _seed(engine, _PLAINTEXT)

    _run(engine, "upgrade")

    stored = _read(engine, row_id)
    assert stored is not None
    assert stored.startswith("v1:")
    assert _PLAINTEXT not in stored
    assert Fernet(_MASTER_KEY).decrypt(stored.removeprefix("v1:")).decode("utf-8") == _PLAINTEXT


def test_upgrade_leaves_an_already_encrypted_value_alone(engine: Engine) -> None:
    """A partially applied or re-run migration must not double-encrypt."""
    already_encrypted = "v1:already-encrypted-by-an-earlier-run"
    row_id = _seed(engine, already_encrypted)

    _run(engine, "upgrade")

    assert _read(engine, row_id) == already_encrypted


def test_upgrade_leaves_null_alone(engine: Engine) -> None:
    """There is no secret to protect, and inventing one would be a lie."""
    row_id = _seed(engine, None)

    _run(engine, "upgrade")

    assert _read(engine, row_id) is None


def test_upgrade_leaves_an_empty_credential_alone(engine: Engine) -> None:
    """The other spelling of "no credential": nothing to encrypt, so nothing is written."""
    row_id = _seed(engine, "")

    _run(engine, "upgrade")

    assert _read(engine, row_id) == ""


def test_upgrade_is_idempotent(engine: Engine) -> None:
    """Fernet is non-deterministic, so an unchanged value proves the second run skipped it."""
    row_id = _seed(engine, _PLAINTEXT)
    _run(engine, "upgrade")
    once = _read(engine, row_id)

    _run(engine, "upgrade")

    assert _read(engine, row_id) == once


def test_upgrade_refuses_to_run_without_a_master_key(
    engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reporting success while leaving plaintext behind is the failure this revision removes."""
    row_id = _seed(engine, _PLAINTEXT)
    monkeypatch.delenv("STORICO_ENCRYPTION_KEY", raising=False)
    _reset_settings_cache()

    with pytest.raises(RuntimeError) as caught:
        _run(engine, "upgrade")

    assert "STORICO_ENCRYPTION_KEY" in str(caught.value)
    # Refusing means refusing: the credential is untouched rather than half-migrated.
    assert _read(engine, row_id) == _PLAINTEXT


def test_downgrade_returns_the_values_to_plaintext(engine: Engine) -> None:
    """The reverse is real and works — which is what makes the upgrade reviewable."""
    row_id = _seed(engine, _PLAINTEXT)
    _run(engine, "upgrade")
    assert (_read(engine, row_id) or "").startswith("v1:")

    _run(engine, "downgrade")

    assert _read(engine, row_id) == _PLAINTEXT


def test_the_revision_follows_0023() -> None:
    """A wrong ``down_revision`` would leave the migration chain with two heads."""
    migration = _load_migration()

    assert migration.revision == "0024"
    assert migration.down_revision == "0023"
