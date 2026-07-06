"""Tests for SQLAlchemyUserStoryRepository."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import UserStory
from storico.infrastructure.database.repositories import SQLAlchemyUserStoryRepository


@pytest.fixture
def project_id() -> UUID:
    return uuid4()


@pytest.mark.asyncio
async def test_save_and_find_by_id(
    db_session: AsyncSession, project_id: UUID
) -> None:
    """Save a user story and retrieve it by id."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    story = UserStory(
        project_id=project_id,
        actor="user",
        feature="log in",
        benefit="access account",
        raw_text="As a user, I want to log in so that I can access my account",
    )

    saved = await repo.save(story)
    assert saved == story

    found = await repo.find_by_id(story.id)
    assert found is not None
    assert found.project_id == project_id
    assert found.actor == "user"
    assert found.feature == "log in"
    assert found.benefit == "access account"
    assert found.raw_text.startswith("As a user")


@pytest.mark.asyncio
async def test_find_by_id_returns_none(db_session: AsyncSession) -> None:
    """find_by_id returns None for a non-existent user story."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    result = await repo.find_by_id(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_by_project(db_session: AsyncSession, project_id: UUID) -> None:
    """list_by_project returns only stories for the given project."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    other_id = uuid4()

    s1 = UserStory(project_id=project_id, actor="user", feature="f1", benefit="b1", raw_text="t1")
    s2 = UserStory(project_id=project_id, actor="user", feature="f2", benefit="b2", raw_text="t2")
    s3 = UserStory(project_id=other_id, actor="admin", feature="f3", benefit="b3", raw_text="t3")
    await repo.save(s1)
    await repo.save(s2)
    await repo.save(s3)

    project_stories = await repo.list_by_project(project_id)
    assert len(project_stories) == 2
    features = {s.feature for s in project_stories}
    assert features == {"f1", "f2"}


@pytest.mark.asyncio
async def test_list_by_project_empty(db_session: AsyncSession) -> None:
    """list_by_project returns empty list when no stories match."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    result = await repo.list_by_project(uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_list_all(db_session: AsyncSession, project_id: UUID) -> None:
    """list returns all user stories."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    s1 = UserStory(project_id=project_id, actor="user", feature="f1", benefit="b1", raw_text="t1")
    s2 = UserStory(project_id=project_id, actor="user", feature="f2", benefit="b2", raw_text="t2")
    await repo.save(s1)
    await repo.save(s2)

    stories = await repo.list()
    assert len(stories) == 2
