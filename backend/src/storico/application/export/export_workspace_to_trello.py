"""The Trello export use case — scope resolution and the background run.

``resolve_export_scope`` is the pure rule the Kanban cascade already applies
(feature ``versioning-visibility``'s D7): ``project_id``, ``user_story_id`` or
the whole workspace, never two — two targets are refused, not resolved, because
an ``if``/``elif`` chain would silently answer one of them, a wrong answer
shaped like a right one.

``run_trello_export`` is the background function the route dispatches with
``asyncio.create_task`` — the extraction's dispatch site, mirrored: no Celery,
no Redis, the work runs in the API process (D5). It builds its own session from
the process engine, because the route's request session is gone by the time the
task runs. It never raises: the job row is the only answer a polling client
has, so every failure — typed or not — must land in it, and a coroutine that
died with an unhandled exception would leave the member polling a job that
never moves.

The failure→code mapping lives in ``api/errors.py`` next to the envelope
handler that shares it. That is an application→api import, deliberately taken:
``api/error_codes.py`` is this repository's single registry for code strings,
and a second mapping in the domain would let the job row and the HTTP envelope
disagree about what a failure is called.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from storico.api.errors import trello_export_error_code
from storico.domain.entities.exceptions import TrelloExportError
from storico.domain.entities.trello_export import (
    TrelloExportScope,
    TrelloExportStatus,
)
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.domain.ports import (
    TaskRepository,
    TrelloExportPort,
    TrelloExportRepository,
    UserStoryRepository,
)
from storico.domain.services.trello_board_plan import build_trello_board_plan
from storico.infrastructure.database.base import create_session_factory, get_engine
from storico.infrastructure.database.repositories import (
    SQLAlchemyTaskRepository,
    SQLAlchemyTrelloExportRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.export.trello_adapter import PyTrelloExportAdapter

logger = logging.getLogger(__name__)


class AmbiguousExportScopeError(ValueError):
    """Two export targets in one request — refused, never resolved."""


def resolve_export_scope(project_id: UUID | None, user_story_id: UUID | None) -> TrelloExportScope:
    """Resolve exactly one export scope from the optional targets.

    Raises ``AmbiguousExportScopeError`` when both are given — the same shape
    refusal the tasks route answers with 422 ``REQUEST_VALIDATION_FAILED``.
    """
    if project_id is not None and user_story_id is not None:
        raise AmbiguousExportScopeError(
            "project_id and user_story_id are mutually exclusive: an export "
            "covers the workspace, one project or one story, never two"
        )
    if project_id is not None:
        return TrelloExportScope.PROJECT
    if user_story_id is not None:
        return TrelloExportScope.STORY
    return TrelloExportScope.WORKSPACE


async def execute_trello_export(
    *,
    export_id: UUID,
    workspace_id: UUID,
    board_name: str,
    scope: TrelloExportScope,
    project_id: UUID | None,
    user_story_id: UUID | None,
    credentials: WorkspaceTrelloConfig,
    task_repo: TaskRepository,
    story_repo: UserStoryRepository,
    export_repo: TrelloExportRepository,
    port: TrelloExportPort,
) -> None:
    """Run one export job against the given repositories and port.

    The lifecycle is pending → running → completed/failed. ``pending`` is never
    written here — the route created the row in that state — so a crash of the
    whole process leaves the row at ``running``: the honest record is "work
    started and nobody finished it", which the extraction flow handles with its
    own startup recovery, and which this job reports as-is rather than faking a
    terminal state it did not observe.

    The credentials travel only between the caller and the port. They are never
    written to the job row and never appear in a log message: the row stores the
    outcome, the logs store the code.
    """
    job = await export_repo.find_by_id(export_id)
    if job is None:
        logger.error("Trello export job %s vanished before its run started", export_id)
        return

    await export_repo.save(replace(job, status=TrelloExportStatus.RUNNING))

    try:
        tasks = await _read_tasks(task_repo, scope, workspace_id, project_id, user_story_id)
        story_text_by_id = await _read_story_text(
            story_repo, scope, workspace_id, project_id, user_story_id
        )
        plan = build_trello_board_plan(
            board_name=board_name,
            tasks=tasks,
            story_text_by_id=story_text_by_id,
        )
        board_ref = await port.create_board(plan, credentials)
        cards_created = sum(len(column.cards) for column in plan.columns)
        await export_repo.save(
            replace(
                job,
                status=TrelloExportStatus.COMPLETED,
                board_id=board_ref.id,
                board_url=board_ref.url,
                cards_created=cards_created,
                completed_at=datetime.now(UTC),
            )
        )
    except TrelloExportError as exc:
        # The typed family: code + board identity. A failure raised after the
        # board was created carries its ``board_ref`` so the half-built board
        # stays reachable from the job row the member is polling.
        logger.error(
            "Trello export %s failed: code=%s had_board=%s",
            export_id,
            trello_export_error_code(exc),
            exc.board_ref is not None,
        )
        await export_repo.save(
            replace(
                job,
                status=TrelloExportStatus.FAILED,
                error_code=trello_export_error_code(exc),
                board_id=exc.board_ref.id if exc.board_ref else None,
                board_url=exc.board_ref.url if exc.board_ref else None,
                completed_at=datetime.now(UTC),
            )
        )
    except Exception:
        # Anything else must still land in the row — a polling client with a
        # job stuck at ``running`` forever is worse than a coded failure.
        logger.exception("Trello export %s failed unexpectedly", export_id)
        await export_repo.save(
            replace(
                job,
                status=TrelloExportStatus.FAILED,
                error_code="INTERNAL_ERROR",
                completed_at=datetime.now(UTC),
            )
        )


async def run_trello_export(
    export_id: UUID,
    workspace_id: UUID,
    board_name: str,
    scope: TrelloExportScope,
    project_id: UUID | None,
    user_story_id: UUID | None,
    credentials: WorkspaceTrelloConfig,
) -> None:
    """Dispatch shape: ``asyncio.create_task(run_trello_export(...))`` in the route.

    Builds the production repositories — its own session on the process engine —
    and delegates to :func:`execute_trello_export`, which is the testable core.
    """
    factory = create_session_factory(get_engine())
    async with factory() as session:
        await execute_trello_export(
            export_id=export_id,
            workspace_id=workspace_id,
            board_name=board_name,
            scope=scope,
            project_id=project_id,
            user_story_id=user_story_id,
            credentials=credentials,
            task_repo=SQLAlchemyTaskRepository(session),
            story_repo=SQLAlchemyUserStoryRepository(session),
            export_repo=SQLAlchemyTrelloExportRepository(session),
            port=PyTrelloExportAdapter(),
        )


async def _read_tasks(
    task_repo: TaskRepository,
    scope: TrelloExportScope,
    workspace_id: UUID,
    project_id: UUID | None,
    user_story_id: UUID | None,
):
    """Current-version rows for the scope — the same filter the file export rides."""
    match scope:
        case TrelloExportScope.WORKSPACE:
            return await task_repo.list_current_by_workspace(workspace_id)
        case TrelloExportScope.PROJECT:
            assert project_id is not None  # resolved by resolve_export_scope
            return await task_repo.list_current_by_project(project_id)
        case TrelloExportScope.STORY:
            assert user_story_id is not None
            return await task_repo.list_current_by_story(user_story_id)


async def _read_story_text(
    story_repo: UserStoryRepository,
    scope: TrelloExportScope,
    workspace_id: UUID,
    project_id: UUID | None,
    user_story_id: UUID | None,
) -> dict:
    """Story texts for the plan's attribution block, scoped like the tasks."""
    match scope:
        case TrelloExportScope.WORKSPACE:
            stories = await story_repo.list_by_workspace(workspace_id)
        case TrelloExportScope.PROJECT:
            assert project_id is not None
            stories = await story_repo.list_by_project(project_id)
        case TrelloExportScope.STORY:
            assert user_story_id is not None
            story = await story_repo.find_by_id(user_story_id)
            stories = [story] if story is not None else []
    return {story.id: story.raw_text for story in stories}
