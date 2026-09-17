"""Tests for SQLAlchemyCustomProviderRepository.

Covers the workspace scoping the providers API depends on: two workspaces may
register the same provider name, and neither sees the other's rows.
"""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import CustomProvider, RepositoryError
from storico.infrastructure.database.models import Base
from storico.infrastructure.database.repositories import (
    SQLAlchemyCustomProviderRepository,
)
from tests._helpers import create_workspace


@pytest.fixture
def repo(db_session: AsyncSession) -> SQLAlchemyCustomProviderRepository:
    return SQLAlchemyCustomProviderRepository(db_session)


async def _workspace_id(db_session: AsyncSession, name: str) -> UUID:
    workspace = await create_workspace(db_session, name=name)
    return workspace.id


@pytest.mark.asyncio
async def test_create_then_list_returns_the_row(
    repo: SQLAlchemyCustomProviderRepository, db_session: AsyncSession
) -> None:
    """A created provider reads back with its name and workspace."""
    workspace_id = await _workspace_id(db_session, "Alpha")

    created = await repo.create(CustomProvider(workspace_id=workspace_id, name="deepseek"))
    assert created.name == "deepseek"

    found = await repo.list_by_workspace(workspace_id)
    assert [p.name for p in found] == ["deepseek"]
    assert found[0].id == created.id
    assert found[0].workspace_id == workspace_id


@pytest.mark.asyncio
async def test_list_is_empty_for_a_fresh_workspace(
    repo: SQLAlchemyCustomProviderRepository, db_session: AsyncSession
) -> None:
    """An untouched workspace lists nothing."""
    workspace_id = await _workspace_id(db_session, "Beta")

    assert await repo.list_by_workspace(workspace_id) == []


@pytest.mark.asyncio
async def test_list_is_scoped_to_the_workspace(
    repo: SQLAlchemyCustomProviderRepository, db_session: AsyncSession
) -> None:
    """A row written for one workspace is invisible to another."""
    alpha = await _workspace_id(db_session, "Alpha")
    beta = await _workspace_id(db_session, "Beta")

    await repo.create(CustomProvider(workspace_id=alpha, name="deepseek"))

    assert await repo.list_by_workspace(beta) == []
    assert await repo.find_by_workspace_and_name(beta, "deepseek") is None


@pytest.mark.asyncio
async def test_same_name_is_allowed_in_two_workspaces(
    repo: SQLAlchemyCustomProviderRepository, db_session: AsyncSession
) -> None:
    """The uniqueness is per workspace, so a shared vendor name is not a conflict."""
    alpha = await _workspace_id(db_session, "Alpha")
    beta = await _workspace_id(db_session, "Beta")

    await repo.create(CustomProvider(workspace_id=alpha, name="groq"))
    await repo.create(CustomProvider(workspace_id=beta, name="groq"))

    assert [p.name for p in await repo.list_by_workspace(alpha)] == ["groq"]
    assert [p.name for p in await repo.list_by_workspace(beta)] == ["groq"]


@pytest.mark.asyncio
async def test_duplicate_name_in_one_workspace_is_rejected(
    repo: SQLAlchemyCustomProviderRepository, db_session: AsyncSession
) -> None:
    """The composite unique constraint stops a second row for the same name."""
    workspace_id = await _workspace_id(db_session, "Alpha")
    await repo.create(CustomProvider(workspace_id=workspace_id, name="groq"))

    with pytest.raises(RepositoryError):
        await repo.create(CustomProvider(workspace_id=workspace_id, name="groq"))


@pytest.mark.asyncio
async def test_list_is_ordered_by_name(
    repo: SQLAlchemyCustomProviderRepository, db_session: AsyncSession
) -> None:
    """The list order is stable so the select does not reshuffle between loads."""
    workspace_id = await _workspace_id(db_session, "Alpha")
    for name in ("groq", "anthropic-proxy", "deepseek"):
        await repo.create(CustomProvider(workspace_id=workspace_id, name=name))

    found = await repo.list_by_workspace(workspace_id)
    assert [p.name for p in found] == ["anthropic-proxy", "deepseek", "groq"]


@pytest.mark.asyncio
async def test_get_returns_none_for_unknown_id(
    repo: SQLAlchemyCustomProviderRepository,
) -> None:
    """An unknown id resolves to None rather than raising."""
    assert await repo.get(uuid4()) is None


@pytest.mark.asyncio
async def test_rename_updates_the_name_and_the_timestamp(
    repo: SQLAlchemyCustomProviderRepository, db_session: AsyncSession
) -> None:
    """Rename returns the updated row and keeps the same identity.

    Both timestamps are read back through the repository rather than compared
    against the in-memory entity: the test database is SQLite, which drops
    ``tzinfo`` on a ``DateTime(timezone=True)`` column, so an in-memory aware
    value and a read-back naive one are never equal.
    """
    workspace_id = await _workspace_id(db_session, "Alpha")
    created = await repo.create(CustomProvider(workspace_id=workspace_id, name="grok"))
    before = await repo.get(created.id)
    assert before is not None

    renamed = await repo.rename(created.id, "groq")

    assert renamed is not None
    assert renamed.id == created.id
    assert renamed.name == "groq"
    assert renamed.created_at == before.created_at
    assert renamed.updated_at >= before.updated_at
    assert [p.name for p in await repo.list_by_workspace(workspace_id)] == ["groq"]


@pytest.mark.asyncio
async def test_rename_returns_none_for_unknown_id(
    repo: SQLAlchemyCustomProviderRepository,
) -> None:
    """Renaming a provider that does not exist reports None, never a new row."""
    assert await repo.rename(uuid4(), "groq") is None


@pytest.mark.asyncio
async def test_rename_onto_a_sibling_name_is_rejected(
    repo: SQLAlchemyCustomProviderRepository, db_session: AsyncSession
) -> None:
    """Renaming onto a name the workspace already holds violates the constraint."""
    workspace_id = await _workspace_id(db_session, "Alpha")
    await repo.create(CustomProvider(workspace_id=workspace_id, name="groq"))
    second = await repo.create(CustomProvider(workspace_id=workspace_id, name="deepseek"))

    with pytest.raises(RepositoryError):
        await repo.rename(second.id, "groq")


def test_workspace_fk_cascades() -> None:
    """The workspace FK deletes its provider rows with the workspace.

    Asserted on the declared metadata rather than by deleting a workspace: the
    test database is SQLite, where ``ON DELETE CASCADE`` is inert unless
    ``PRAGMA foreign_keys=ON`` is set, so a behavioural test here would pass
    while the constraint was missing.
    """
    table = Base.metadata.tables["custom_providers"]
    foreign_keys = table.c.workspace_id.foreign_keys

    assert len(foreign_keys) == 1
    assert foreign_keys.copy().pop().ondelete == "CASCADE"
    assert foreign_keys.copy().pop().target_fullname == "workspaces.id"


@pytest.mark.asyncio
async def test_integrity_error_is_wrapped_as_repository_error(
    db_session: AsyncSession,
) -> None:
    """A constraint violation surfaces as RepositoryError, not a raw SQLAlchemyError."""
    workspace_id = await create_workspace(db_session, name="Alpha")
    repo = SQLAlchemyCustomProviderRepository(db_session)
    await repo.create(CustomProvider(workspace_id=workspace_id.id, name="groq"))

    other = SQLAlchemyCustomProviderRepository(db_session)
    with pytest.raises(RepositoryError) as excinfo:
        await other.create(CustomProvider(workspace_id=workspace_id.id, name="groq"))

    assert isinstance(excinfo.value.__cause__, IntegrityError)
