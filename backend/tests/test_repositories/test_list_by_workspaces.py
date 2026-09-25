"""Tests for the ``list_by_workspaces`` fold across the three list repositories.

The unfiltered list routes used to await ``list_by_workspace`` once per workspace the caller
belongs to: one statement per workspace, so 12 of them for a caller in 12 workspaces, against a
Supabase pooler in ``us-east-1`` where a statement costs ~2s (a bare ``SELECT 1`` measures 800ms).
``list_by_workspaces`` replaces that loop
with a single ``WHERE project.workspace_id IN (…)`` statement.

These tests are the contract for that fold: same rows as the loop returned, and nothing from a
workspace the caller did not ask about — the second half matters because a fold with the wrong
``WHERE`` would be fast and wrong.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import Extraction, Project, Task, UserStory
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import create_workspace


@pytest_asyncio.fixture
async def chain(db_session: AsyncSession):
    """Build a workspace → project → story chain on demand, one story each.

    A fixture over a plain helper because every test here needs three chains and the ids of
    the two that should come back.
    """

    async def _build(name: str):
        workspace = await create_workspace(
            db_session, name=name, slug=f"{name.lower()}-{uuid4().hex[:6]}"
        )
        project = await SQLAlchemyProjectRepository(db_session).save(
            Project(name=f"{name} project", workspace_id=workspace.id)
        )
        story = await SQLAlchemyUserStoryRepository(db_session).save(
            UserStory(
                project_id=project.id,
                actor="user",
                feature=f"{name} feature",
                benefit="value",
                raw_text=f"As a user, I want {name} so that value",
            )
        )
        return workspace, story

    return _build


@pytest.mark.asyncio
async def test_stories_span_the_requested_workspaces_only(db_session: AsyncSession, chain) -> None:
    """Stories from both requested workspaces, and none from the third."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    alpha, _ = await chain("Alpha")
    beta, _ = await chain("Beta")
    gamma, gamma_story = await chain("Gamma")

    found = await repo.list_by_workspaces([alpha.id, beta.id])

    assert {s.feature for s in found} == {"Alpha feature", "Beta feature"}
    assert gamma_story.id not in {s.id for s in found}
    assert gamma.id not in {s.project_id for s in found}


@pytest.mark.asyncio
async def test_tasks_span_the_requested_workspaces_only(db_session: AsyncSession, chain) -> None:
    """Tasks follow their story's project back to the workspace."""
    repo = SQLAlchemyTaskRepository(db_session)
    alpha, alpha_story = await chain("Alpha")
    beta, beta_story = await chain("Beta")
    _, gamma_story = await chain("Gamma")

    await repo.save(Task(user_story_id=alpha_story.id, title="Alpha task"))
    await repo.save(Task(user_story_id=beta_story.id, title="Beta task"))
    await repo.save(Task(user_story_id=gamma_story.id, title="Gamma task"))

    found = await repo.list_by_workspaces([alpha.id, beta.id])

    assert {t.title for t in found} == {"Alpha task", "Beta task"}


@pytest.mark.asyncio
async def test_extractions_span_the_requested_workspaces_only(
    db_session: AsyncSession, chain
) -> None:
    """Extractions follow the same chain, through a different table."""
    repo = SQLAlchemyExtractionRepository(db_session)
    alpha, alpha_story = await chain("Alpha")
    beta, beta_story = await chain("Beta")
    _, gamma_story = await chain("Gamma")

    for story, model in ((alpha_story, "alpha-model"), (beta_story, "beta-model")):
        await repo.save(
            Extraction(user_story_id=story.id, model_used=model, raw_response="1. summary: s")
        )
    await repo.save(
        Extraction(user_story_id=gamma_story.id, model_used="gamma-model", raw_response="x")
    )

    found = await repo.list_by_workspaces([alpha.id, beta.id])

    assert {e.model_used for e in found} == {"alpha-model", "beta-model"}


@pytest.mark.asyncio
async def test_an_empty_workspace_list_returns_nothing(db_session: AsyncSession, chain) -> None:
    """No memberships is not the same query with an empty ``IN ()``; it is no query at all."""
    repo = SQLAlchemyUserStoryRepository(db_session)
    await chain("Alpha")

    assert await repo.list_by_workspaces([]) == []
    assert await SQLAlchemyTaskRepository(db_session).list_by_workspaces([]) == []
    assert await SQLAlchemyExtractionRepository(db_session).list_by_workspaces([]) == []
