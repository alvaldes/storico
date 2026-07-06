"""Tests for SQLAlchemyTaskRepository."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import Task
from storico.infrastructure.database.repositories import SQLAlchemyTaskRepository


@pytest.fixture
def story_id() -> UUID:
    return uuid4()


@pytest.mark.asyncio
async def test_save_with_json_labels_and_deps(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """Save a task with labels and dependencies, then verify they round-trip."""
    repo = SQLAlchemyTaskRepository(db_session)
    task = Task(
        user_story_id=story_id,
        title="Implement login",
        description="Build the login form and validation",
        labels=["frontend", "auth"],
        dependencies=["US-001"],
    )

    saved = await repo.save(task)
    assert saved == task

    found = await repo.find_by_id(task.id)
    assert found is not None
    assert found.title == "Implement login"
    assert found.labels == ["frontend", "auth"]
    assert found.dependencies == ["US-001"]
    assert found.status == "backlog"
    assert found.priority == "medium"


@pytest.mark.asyncio
async def test_find_by_id_returns_none(db_session: AsyncSession) -> None:
    """find_by_id returns None for a non-existent task."""
    repo = SQLAlchemyTaskRepository(db_session)
    result = await repo.find_by_id(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_by_story(db_session: AsyncSession, story_id: UUID) -> None:
    """list_by_story returns only tasks for the given user story."""
    repo = SQLAlchemyTaskRepository(db_session)
    other_id = uuid4()

    t1 = Task(user_story_id=story_id, title="Task 1")
    t2 = Task(user_story_id=story_id, title="Task 2")
    t3 = Task(user_story_id=other_id, title="Other task")
    await repo.save(t1)
    await repo.save(t2)
    await repo.save(t3)

    tasks = await repo.list_by_story(story_id)
    assert len(tasks) == 2
    titles = {t.title for t in tasks}
    assert titles == {"Task 1", "Task 2"}


@pytest.mark.asyncio
async def test_list_by_story_empty(db_session: AsyncSession) -> None:
    """list_by_story returns empty list when no tasks match."""
    repo = SQLAlchemyTaskRepository(db_session)
    result = await repo.list_by_story(uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_update_sets_updated_at(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """Saving an existing task updates its updated_at timestamp."""
    repo = SQLAlchemyTaskRepository(db_session)
    task = Task(user_story_id=story_id, title="Original")
    await repo.save(task)

    found_before = await repo.find_by_id(task.id)
    assert found_before is not None
    before_updated = found_before.updated_at

    # Save again (update path)
    await repo.save(task)

    found_after = await repo.find_by_id(task.id)
    assert found_after is not None
    assert found_after.updated_at >= before_updated


@pytest.mark.asyncio
async def test_list_all(db_session: AsyncSession, story_id: UUID) -> None:
    """list returns all tasks."""
    repo = SQLAlchemyTaskRepository(db_session)
    t1 = Task(user_story_id=story_id, title="Task 1")
    t2 = Task(user_story_id=story_id, title="Task 2")
    await repo.save(t1)
    await repo.save(t2)

    tasks = await repo.list()
    assert len(tasks) == 2
