"""The ``workspace_ids`` scope of ``list_page`` across the three list repositories.

The unfiltered list routes used to await ``list_by_workspace`` once per workspace the caller
belongs to: one statement per workspace, so 12 of them for a caller in 12 workspaces, against a
Supabase pooler in ``us-east-1`` where a statement costs ~2s (a bare ``SELECT 1`` measures 800ms).
The folds were replaced by a single ``WHERE project.workspace_id IN (…)`` statement, which now
lives in each repository's ``list_page`` under its ``workspace_ids`` scope.

These tests pin that scope across the story, task and extraction repositories in one place:
same rows as the loop returned, and nothing from a workspace the caller did not ask about —
the second half matters because a query with the wrong ``WHERE`` would still be fast and wrong.
Each repository's own test module carries the rest of its ``list_page`` contract (totals,
ordering, the empty-list short circuit); this file holds only the cross-repository shape.
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
    """Stories from both requested workspaces, and none from the third.

    The half that matters: a fold with the wrong ``WHERE`` would still be fast
    — one statement either way — so the third workspace's absence is asserted
    explicitly rather than assumed from the row count.
    """
    repo = SQLAlchemyUserStoryRepository(db_session)
    alpha, _ = await chain("Alpha")
    beta, _ = await chain("Beta")
    gamma, gamma_story = await chain("Gamma")

    found, total = await repo.list_page(workspace_ids=[alpha.id, beta.id], limit=10, offset=0)

    assert total == 2
    assert {s.feature for s in found} == {"Alpha feature", "Beta feature"}
    assert gamma_story.id not in {s.id for s in found}
    assert gamma.id not in {s.project_id for s in found}


@pytest.mark.asyncio
async def test_tasks_span_the_requested_workspaces_only(db_session: AsyncSession, chain) -> None:
    """Tasks follow their story's project back to the workspace, under ``list_page``.

    The task fold moved to ``list_page`` in T5. The half that matters is
    unchanged from the fold it replaced: a query with the wrong ``WHERE`` would
    still be fast — one statement either way — so the third workspace's absence
    is asserted explicitly rather than assumed from the row count.
    """
    repo = SQLAlchemyTaskRepository(db_session)
    alpha, alpha_story = await chain("Alpha")
    beta, beta_story = await chain("Beta")
    _, gamma_story = await chain("Gamma")

    await repo.save(Task(user_story_id=alpha_story.id, title="Alpha task"))
    await repo.save(Task(user_story_id=beta_story.id, title="Beta task"))
    await repo.save(Task(user_story_id=gamma_story.id, title="Gamma task"))

    found, total = await repo.list_page(workspace_ids=[alpha.id, beta.id], limit=10, offset=0)

    assert total == 2
    assert {t.title for t in found} == {"Alpha task", "Beta task"}


@pytest.mark.asyncio
async def test_extractions_span_the_requested_workspaces_only(
    db_session: AsyncSession, chain
) -> None:
    """Extractions follow the same chain, through a different table, under ``list_page``.

    The extraction fold moved to ``list_page`` in T6. The half that matters is
    unchanged from the fold it replaced: a query with the wrong ``WHERE`` would
    still be fast — one statement either way — so the third workspace's absence
    is asserted explicitly rather than assumed from the row count.
    """
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

    found, total = await repo.list_page(workspace_ids=[alpha.id, beta.id], limit=10, offset=0)

    assert total == 2
    assert {e.model_used for e in found} == {"alpha-model", "beta-model"}


@pytest.mark.asyncio
async def test_an_empty_workspace_list_returns_nothing(db_session: AsyncSession, chain) -> None:
    """No memberships is not the same query with an empty ``IN ()``; it is no query at all.

    The fold moved to ``list_page`` — the story line in T4, the task line in T5
    and the extraction line in T6 — and each repository answers an empty
    ``workspace_ids`` there without a statement. This is the one place the three
    empty answers are pinned together as a value.

    It is deliberately not the place the ``IN ()`` regression is caught, even
    though the assertion below looks like it: an empty ``IN ()`` compiles to a
    false predicate that runs cleanly and returns zero rows, so this test would
    pass under that regression too. Only each repository's own zero-statement
    test — ``test_user_story_repo.py``, ``test_task_repo.py``,
    ``test_extraction_repo.py`` — can tell "no statement" from "a statement that
    matched nothing", because it counts statements on the engine rather than
    reading the result.
    """
    await chain("Alpha")

    for repo in (
        SQLAlchemyUserStoryRepository(db_session),
        SQLAlchemyTaskRepository(db_session),
        SQLAlchemyExtractionRepository(db_session),
    ):
        page, total = await repo.list_page(workspace_ids=[], limit=10, offset=0)
        assert page == []
        assert total == 0
