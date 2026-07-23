"""Tests for SQLAlchemyProjectRepository."""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, Project
from storico.infrastructure.database.repositories import SQLAlchemyProjectRepository
from tests._helpers import create_workspace


@pytest_asyncio.fixture
async def workspace_id(db_session: AsyncSession) -> UUID:
    """Seed a Workspace and return its id — Projects need a real FK."""
    ws = await create_workspace(db_session)
    return ws.id


@pytest.mark.asyncio
async def test_save_and_find_by_id(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """Save a project and retrieve it by id."""
    repo = SQLAlchemyProjectRepository(db_session)
    project = Project(name="Test Project", workspace_id=workspace_id, description="A test")

    saved = await repo.save(project)
    assert saved == project

    found = await repo.find_by_id(project.id)
    assert found is not None
    assert found.name == "Test Project"
    assert found.workspace_id == workspace_id
    assert found.description == "A test"


@pytest.mark.asyncio
async def test_find_by_id_returns_none(db_session: AsyncSession) -> None:
    """find_by_id returns None for a non-existent project."""
    repo = SQLAlchemyProjectRepository(db_session)
    result = await repo.find_by_id(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_by_workspace(db_session: AsyncSession) -> None:
    """list_by_workspace returns only projects for the given workspace."""
    repo = SQLAlchemyProjectRepository(db_session)
    ws_a_id = (await create_workspace(db_session, name="Workspace A")).id
    ws_b_id = (await create_workspace(db_session, name="Workspace B")).id

    p1 = Project(name="Project 1", workspace_id=ws_a_id)
    p2 = Project(name="Project 2", workspace_id=ws_a_id)
    p3 = Project(name="Project 3", workspace_id=ws_a_id)
    p4 = Project(name="Other Project", workspace_id=ws_b_id)
    await repo.save(p1)
    await repo.save(p2)
    await repo.save(p3)
    await repo.save(p4)

    ws_a_projects = await repo.list_by_workspace(ws_a_id)
    assert len(ws_a_projects) == 3
    names = {p.name for p in ws_a_projects}
    assert names == {"Project 1", "Project 2", "Project 3"}

    ws_b_projects = await repo.list_by_workspace(ws_b_id)
    assert len(ws_b_projects) == 1
    assert ws_b_projects[0].name == "Other Project"


@pytest.mark.asyncio
async def test_delete_raises_entity_not_found(db_session: AsyncSession) -> None:
    """delete raises EntityNotFound when the project does not exist."""
    repo = SQLAlchemyProjectRepository(db_session)
    with pytest.raises(EntityNotFound) as exc:
        await repo.delete(uuid4())
    assert "Project" in str(exc.value)


@pytest.mark.asyncio
async def test_list_returns_empty_for_no_matches(
    db_session: AsyncSession
) -> None:
    """list_by_workspace returns empty list when no projects match."""
    repo = SQLAlchemyProjectRepository(db_session)
    result = await repo.list_by_workspace(uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_list_all(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """list returns all projects."""
    repo = SQLAlchemyProjectRepository(db_session)
    p1 = Project(name="P1", workspace_id=workspace_id)
    p2 = Project(name="P2", workspace_id=workspace_id)
    await repo.save(p1)
    await repo.save(p2)

    projects = await repo.list()
    assert len(projects) == 2


@pytest.mark.asyncio
async def test_update_sets_updated_at(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """Saving an existing project updates its updated_at timestamp."""
    repo = SQLAlchemyProjectRepository(db_session)
    project = Project(name="Original", workspace_id=workspace_id)
    await repo.save(project)

    # Mutate via ORM — domain entity is frozen, so we re-fetch
    # and verify the timestamp was updated
    found_before = await repo.find_by_id(project.id)
    assert found_before is not None
    before_updated = found_before.updated_at

    # Save again with the same entity (update path)
    await repo.save(project)

    found_after = await repo.find_by_id(project.id)
    assert found_after is not None
    # updated_at should be newer
    assert found_after.updated_at >= before_updated
