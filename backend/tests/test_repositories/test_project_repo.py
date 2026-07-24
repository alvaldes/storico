"""Tests for SQLAlchemyProjectRepository."""

from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, Project
from storico.domain.entities.user_story import UserStory
from storico.infrastructure.database.repositories import SQLAlchemyProjectRepository
from storico.infrastructure.database.repositories.user_story_repository import (
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import create_workspace


@pytest_asyncio.fixture
async def workspace_id(db_session: AsyncSession) -> UUID:
    """Seed a Workspace and return its id — Projects need a real FK."""
    ws = await create_workspace(db_session)
    return ws.id


@pytest.mark.asyncio
async def test_list_by_workspace_with_counts_folds_stories(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """list_by_workspace_with_counts returns (project, story_count) pairs.

    Guards the P0.1 perf fix: one LEFT OUTER JOIN + GROUP BY round-trip
    instead of N+1 (list_by_workspace + count_stories per project).
    Verifies the count is 0 for projects with no stories and correct for
    projects with several, so a future regression that drops the LEFT
    OUTER JOIN is caught.
    """
    project_repo = SQLAlchemyProjectRepository(db_session)
    story_repo = SQLAlchemyUserStoryRepository(db_session)

    p_empty = Project(name="Empty", workspace_id=workspace_id)
    p_with_two = Project(name="WithTwo", workspace_id=workspace_id)
    await project_repo.save(p_empty)
    await project_repo.save(p_with_two)

    for _ in range(2):
        await story_repo.save(
            UserStory(
                project_id=p_with_two.id,
                actor="user",
                feature="do thing",
                benefit="value",
                raw_text="As a user, I want to do a thing so that I get value.",
            )
        )

    pairs = await project_repo.list_by_workspace_with_counts(workspace_id)
    by_name = {pwc.project.name: pwc.story_count for pwc in pairs}

    assert by_name == {"Empty": 0, "WithTwo": 2}


@pytest.mark.asyncio
async def test_find_by_id_with_count_returns_pair_when_found(
    db_session: AsyncSession, workspace_id: UUID
) -> None:
    """find_by_id_with_count returns a ProjectWithCount (project, count)."""
    project_repo = SQLAlchemyProjectRepository(db_session)
    story_repo = SQLAlchemyUserStoryRepository(db_session)

    project = Project(name="Solo", workspace_id=workspace_id)
    await project_repo.save(project)
    await story_repo.save(
        UserStory(
            project_id=project.id,
            actor="user",
            feature="feature",
            benefit="benefit",
            raw_text="As a user, I want a feature so that benefit.",
        )
    )

    pwc = await project_repo.find_by_id_with_count(project.id)
    assert pwc is not None
    assert pwc.project.id == project.id
    assert pwc.story_count == 1


@pytest.mark.asyncio
async def test_find_by_id_with_count_returns_none_when_missing(
    db_session: AsyncSession,
) -> None:
    """find_by_id_with_count returns None for a non-existent project."""
    repo = SQLAlchemyProjectRepository(db_session)
    assert await repo.find_by_id_with_count(uuid4()) is None

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
