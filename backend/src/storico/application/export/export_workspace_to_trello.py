"""The Trello export use case — the background run.

The scope rule the trigger applies lives in
``domain/services/export_scope.py`` — the same rule the file export resolves
through, one implementation for both.

``run_trello_export`` is the background function the route dispatches with
``asyncio.create_task`` — the extraction's dispatch site, mirrored: no Celery,
no Redis, the work runs in the API process (D5). It builds its own session from
the process engine, because the route's request session is gone by the time the
task runs. It never lets a plain failure escape: the job row is the only answer
a polling client has, so every failure — typed or not — must land in it. The
faults that cannot are the ones in a terminal write itself: the save that was
recording the failure is the failure's last stop, so when it faults there is
nowhere left to write — the runner logs it and leaves the row to the startup
sweep, which makes it terminal at the next boot. A cancellation is the other
boundary: it is written to the row and then re-raised, because swallowing it
would break the asyncio contract that is trying to stop the task.

The failure→code mapping lives in the domain, next to the failures: each
``TrelloExportError`` member carries its code as a class attribute, with the
same literal ``api/error_codes.py`` — the single registry the frontend
guard greps — declares, and the pin test
(``tests/test_unit/test_trello_error_codes.py``) keeps the two from drifting.
One mapping, read by both the job row and the HTTP envelope, in the direction
the architecture allows: nothing here imports from ``api``.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from storico.domain.entities.exceptions import (
    TRELLO_EXPORT_INTERRUPTED,
    TrelloExportError,
)
from storico.domain.entities.trello_board import TrelloBoardPlan, TrelloBoardRef
from storico.domain.entities.trello_export import (
    TrelloExport,
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


async def execute_trello_export(
    *,
    export_id: UUID,
    workspace_id: UUID,
    board_name: str,
    scope: TrelloExportScope,
    project_id: UUID | None,
    user_story_id: UUID | None,
    extraction_id: UUID | None = None,
    credentials: WorkspaceTrelloConfig,
    task_repo: TaskRepository,
    story_repo: UserStoryRepository,
    export_repo: TrelloExportRepository,
    port: TrelloExportPort,
) -> None:
    """Run one export job against the given repositories and port.

    The lifecycle is pending → running → completed/failed. ``pending`` is never
    written here — the route created the row in that state. The failure
    contract, defect by defect:

    - A failure after ``create_board`` returned keeps the board identity. The
      reference is captured in a local the moment it exists and every failure
      handler — typed and generic alike — writes it, so a board that exists on
      Trello stays reachable from the row the member is polling.
    - A cancellation (``asyncio.CancelledError`` is a ``BaseException``;
      ``except Exception`` never sees it) writes ``failed`` with
      ``TRELLO_EXPORT_INTERRUPTED`` under ``asyncio.shield`` — so the write
      itself is not cancelled — and then re-raises: swallowing a cancellation
      would break the asyncio contract that is trying to stop the task.
    - A fault before the job row was read leaves the row ``pending`` — there is
      nothing to write to — and does not raise out of the task.
    - Any other fault lands in the row as ``failed``/``INTERNAL_ERROR``.
    - A fault in a terminal write — the save a failure handler is running —
      cannot be recorded: there is no working write left. It is logged, the row
      stays where it is, and the startup sweep makes it terminal at the next
      boot. The handler does not raise; an escaping exception would reach
      nobody.

    A row a dead process strands at ``pending``/``running`` is covered by the
    startup sweep this table owns — ``recover_stuck_trello_exports``
    (``infrastructure/tasks/trello_export_task.py``, wired in the same lifespan
    block as the extraction's ``recover_stuck_extractions``) — which marks it
    ``failed``/``TRELLO_EXPORT_INTERRUPTED`` at the next boot.

    The credentials travel only between the caller and the port. They are never
    written to the job row and never appear in a log message: the row stores the
    outcome, the logs store the code.
    """
    board_ref: TrelloBoardRef | None = None
    job: TrelloExport | None = None
    try:
        job = await export_repo.find_by_id(export_id)
        if job is None:
            logger.error("Trello export job %s vanished before its run started", export_id)
            return

        await export_repo.save(replace(job, status=TrelloExportStatus.RUNNING))

        plan = await build_board_plan_for_scope(
            workspace_id=workspace_id,
            board_name=board_name,
            scope=scope,
            project_id=project_id,
            user_story_id=user_story_id,
            extraction_id=extraction_id,
            task_repo=task_repo,
            story_repo=story_repo,
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
    except asyncio.CancelledError:
        logger.warning("Trello export %s was cancelled; recording the interruption", export_id)
        if job is not None:
            await asyncio.shield(_mark_interrupted(export_repo, job, board_ref))
        raise
    except TrelloExportError as exc:
        if job is None:
            # Unreachable today — the early return above covers the only way
            # ``job`` can be ``None`` — but a dereference here is one refactor
            # away, and there is no row to write to anyway.
            logger.error(
                "Trello export %s failed with code=%s before its job row could be read",
                export_id,
                exc.code,
            )
            return
        # The typed family: code + board identity. A failure raised after the
        # board was created carries its ``board_ref`` so the half-built board
        # stays reachable from the job row the member is polling; when it does
        # not, the local captured at creation time stands in.
        kept_ref = exc.board_ref if exc.board_ref is not None else board_ref
        logger.error(
            "Trello export %s failed: code=%s had_board=%s",
            export_id,
            exc.code,
            kept_ref is not None,
        )
        await _record_failure(
            export_repo,
            job,
            error_code=exc.code,
            board_ref=kept_ref,
        )
    except Exception:
        if job is None:
            # The fault happened before the job row was even read — there is
            # nothing to write to, and raising would only kill the task with
            # the row stranded. It stays pending; the startup sweep makes it
            # terminal at the next boot.
            logger.exception("Trello export %s failed before its job row could be read", export_id)
            return
        # Anything else must still land in the row — a polling client with a
        # job stuck at ``running`` forever is worse than a coded failure — and
        # it must keep the board identity when the board already exists.
        logger.exception("Trello export %s failed unexpectedly", export_id)
        await _record_failure(
            export_repo,
            job,
            error_code="INTERNAL_ERROR",
            board_ref=board_ref,
        )
    except BaseException:
        # Neither a cancellation nor an ``Exception`` — ``KeyboardInterrupt``
        # and friends inside the task. The row still must not be stranded;
        # write the interruption and let the exception propagate.
        if job is not None:
            await asyncio.shield(_mark_interrupted(export_repo, job, board_ref))
        raise


async def _record_failure(
    export_repo: TrelloExportRepository,
    job: TrelloExport,
    *,
    error_code: str,
    board_ref: TrelloBoardRef | None,
) -> None:
    """Write the terminal ``failed`` state for a job whose work already failed.

    The write itself is guarded the way ``_mark_interrupted`` guards its own:
    a fault in the save is logged, not raised, because the handler this is
    called from is the failure's last stop — raising out of it would escape
    the task with the row still ``running`` and nothing left to write it. The
    startup sweep recovers a row this write could not reach.
    """
    try:
        await export_repo.save(
            replace(
                job,
                status=TrelloExportStatus.FAILED,
                error_code=error_code,
                board_id=board_ref.id if board_ref else None,
                board_url=board_ref.url if board_ref else None,
                completed_at=datetime.now(UTC),
            )
        )
    except Exception:
        logger.exception(
            "Could not record the failure of Trello export %s (code=%s); "
            "the startup sweep recovers the row at the next boot",
            job.id,
            error_code,
        )


async def _mark_interrupted(
    export_repo: TrelloExportRepository,
    job: TrelloExport,
    board_ref: TrelloBoardRef | None,
) -> None:
    """Write the terminal state a cancelled or dying task leaves behind.

    Awaited under ``asyncio.shield`` by its callers so the write itself is not
    cancelled. A write that faults is logged, not raised: the cancellation the
    caller is holding must still propagate, and the startup sweep recovers a
    row this write could not reach.
    """
    try:
        await export_repo.save(
            replace(
                job,
                status=TrelloExportStatus.FAILED,
                error_code=TRELLO_EXPORT_INTERRUPTED,
                board_id=board_ref.id if board_ref else None,
                board_url=board_ref.url if board_ref else None,
                completed_at=datetime.now(UTC),
            )
        )
    except Exception:
        logger.exception("Could not record the interruption of Trello export %s", job.id)


async def run_trello_export(
    export_id: UUID,
    workspace_id: UUID,
    board_name: str,
    scope: TrelloExportScope,
    project_id: UUID | None,
    user_story_id: UUID | None,
    credentials: WorkspaceTrelloConfig,
    extraction_id: UUID | None = None,
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
            extraction_id=extraction_id,
            credentials=credentials,
            task_repo=SQLAlchemyTaskRepository(session),
            story_repo=SQLAlchemyUserStoryRepository(session),
            export_repo=SQLAlchemyTrelloExportRepository(session),
            port=PyTrelloExportAdapter(),
        )


async def build_board_plan_for_scope(
    *,
    workspace_id: UUID,
    board_name: str,
    scope: TrelloExportScope,
    project_id: UUID | None,
    user_story_id: UUID | None,
    task_repo: TaskRepository,
    story_repo: UserStoryRepository,
    extraction_id: UUID | None = None,
) -> TrelloBoardPlan:
    """The plan the runner would send — reads for the scope, then the pure builder.

    The single application-layer entry point for plan assembly: the trigger's
    background run and the ``GET .../export/trello/preview`` route both call
    this, so the preview can only ever show the plan the runner would send.
    When ``extraction_id`` names a version (story scope only — a version
    belongs to a story, enforced by the routes), its tasks are read through
    ``list_by_story_version`` — the same predicate the file export rides, so
    the cross-story-leak protection its ``WHERE`` carries comes along — and a
    superseded version exports exactly as it was. Without one, every story's
    current version is read, the behaviour this function has always had.
    """
    tasks = await _read_tasks(
        task_repo, scope, workspace_id, project_id, user_story_id, extraction_id
    )
    story_text_by_id = await _read_story_text(
        story_repo, scope, workspace_id, project_id, user_story_id
    )
    return build_trello_board_plan(
        board_name=board_name,
        tasks=tasks,
        story_text_by_id=story_text_by_id,
    )


async def _read_tasks(
    task_repo: TaskRepository,
    scope: TrelloExportScope,
    workspace_id: UUID,
    project_id: UUID | None,
    user_story_id: UUID | None,
    extraction_id: UUID | None = None,
):
    """Rows for the scope. Current versions by default; a named version reads
    through the one version predicate that exists — ``list_by_story_version``,
    whose ``WHERE`` keeps both filters, so an extraction id from another story
    matches nothing instead of leaking into this export."""
    match scope:
        case TrelloExportScope.WORKSPACE:
            return await task_repo.list_current_by_workspace(workspace_id)
        case TrelloExportScope.PROJECT:
            assert project_id is not None  # resolved by resolve_export_scope
            return await task_repo.list_current_by_project(project_id)
        case TrelloExportScope.STORY:
            assert user_story_id is not None
            if extraction_id is not None:
                # A version named on purpose: no currency predicate, or the
                # trigger could never export a superseded version's tasks.
                return await task_repo.list_by_story_version(user_story_id, extraction_id)
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
