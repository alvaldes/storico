"""Export API routes — file export (JSON/Markdown/CSV) and the Trello board export."""

import asyncio
import csv
import io
import json
import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import PlainTextResponse

from storico.api.dependencies import (
    get_repository,
    get_trello_config_repository,
    get_workspace_for_user,
)
from storico.api.error_codes import (
    PROJECT_NOT_IN_WORKSPACE,
    REQUEST_VALIDATION_FAILED,
    STORY_NOT_IN_WORKSPACE,
    TRELLO_CREDENTIALS_MISSING,
    TRELLO_EXPORT_NOT_FOUND,
    UNSUPPORTED_EXPORT_FORMAT,
)
from storico.api.errors import ApiError
from storico.api.schemas.task import TaskResponse
from storico.api.schemas.trello_export import (
    TrelloBoardPlanResponse,
    TrelloExportCreateRequest,
    TrelloExportResponse,
)
from storico.application.export.export_workspace_to_trello import (
    build_board_plan_for_scope,
    run_trello_export,
)
from storico.domain.entities import EntityNotFound, Workspace, WorkspaceRole
from storico.domain.entities.trello_export import TrelloExport, TrelloExportScope
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.domain.services.dependency_resolution import (
    build_dependency_title_index,
    resolve_dependency,
)
from storico.domain.services.export_scope import (
    AmbiguousExportScopeError,
    resolve_export_scope,
)
from storico.domain.services.llm_config_readiness import normalize_optional
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyProjectRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyTrelloExportRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_trello_config_repository import (
    SQLAlchemyWorkspaceTrelloConfigRepository,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/export",
    tags=["export"],
)

TaskRepoDep = Annotated[
    SQLAlchemyTaskRepository,
    Depends(get_repository(SQLAlchemyTaskRepository)),
]
StoryRepoDep = Annotated[
    SQLAlchemyUserStoryRepository,
    Depends(get_repository(SQLAlchemyUserStoryRepository)),
]
ProjectRepoDep = Annotated[
    SQLAlchemyProjectRepository,
    Depends(get_repository(SQLAlchemyProjectRepository)),
]
TrelloConfigRepoDep = Annotated[
    SQLAlchemyWorkspaceTrelloConfigRepository,
    Depends(get_trello_config_repository),
]
TrelloExportRepoDep = Annotated[
    SQLAlchemyTrelloExportRepository,
    Depends(get_repository(SQLAlchemyTrelloExportRepository)),
]
ExtractionRepoDep = Annotated[
    SQLAlchemyExtractionRepository,
    Depends(get_repository(SQLAlchemyExtractionRepository)),
]


def _build_markdown(tasks: list[TaskResponse], story_text: dict[UUID, str]) -> str:
    """Build a Markdown export grouped by story.

    One section per story (``## {story text}``), each task rendered as a
    ``- **{title}** — {description}`` bullet, labels as ``#label`` inline, and
    dependencies as ``→ {title}`` references. The dependency references resolve
    through the shared rule in ``domain/services/dependency_resolution.py`` —
    the same code the Trello plan uses, extracted verbatim from this module.
    """
    # Resolve dependency references to the referenced task's title.
    title_index = build_dependency_title_index([(str(t.id), t.title) for t in tasks])

    by_story: dict[UUID, list[TaskResponse]] = {}
    for task in tasks:
        by_story.setdefault(task.user_story_id, []).append(task)

    lines = ["# Tasks Export", ""]
    for story_id, story_tasks in by_story.items():
        lines.append(f"## {story_text.get(story_id, 'Untitled story')}")
        lines.append("")
        for task in story_tasks:
            bullet = f"- **{task.title}**"
            if task.description:
                bullet += f" — {task.description}"
            if task.labels:
                bullet += " " + " ".join(f"#{label}" for label in task.labels)
            if task.dependencies:
                bullet += " " + " ".join(
                    f"→ {resolve_dependency(dep, title_index)}" for dep in task.dependencies
                )
            lines.append(bullet)
        lines.append("")
    return "\n".join(lines)


# The CSV column order is a contract (record ``export-page-rework``, E3): a
# file people parse stops being free to reorder. Adding a column is compatible;
# renaming or reordering one is not.
CSV_COLUMNS = (
    "story",
    "version",
    "title",
    "description",
    "status",
    "priority",
    "labels",
    "dependencies",
)


def _build_csv(
    tasks: list[TaskResponse],
    story_text: dict[UUID, str],
    version_by_task_id: dict[UUID, int | str],
) -> str:
    """Build the CSV export — one row per task, columns in contract order.

    Written through the ``csv`` module so a description containing a newline
    or a comma is quoted and survives the round trip. Multi-value cells
    (``labels``, ``dependencies``) are joined with ``;`` — a separator that
    never appears inside a task id or a label, so the cell splits cleanly.
    """
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(CSV_COLUMNS)
    for task in tasks:
        writer.writerow(
            [
                story_text.get(task.user_story_id, "Untitled story"),
                version_by_task_id.get(task.id, ""),
                task.title,
                task.description or "",
                task.status.value,
                task.priority or "",
                ";".join(task.labels),
                ";".join(task.dependencies),
            ]
        )
    return buffer.getvalue()


@router.get("/tasks")
async def export_tasks(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    format: str = Query("json", description="Export format: json, markdown or csv"),
    project_id: UUID | None = Query(None, description="Narrow the export to one project"),
    user_story_id: UUID | None = Query(None, description="Narrow the export to one story"),
    extraction_id: UUID | None = Query(
        None, description="Export exactly this version (requires user_story_id)"
    ),
    preview: bool = Query(
        False,
        description="Return the body inline, without the attachment header",
    ),
) -> PlainTextResponse:
    """Export tasks from a workspace in the requested format and scope.

    Supported formats:
    - ``json`` (default): JSON array of tasks
    - ``markdown``: Markdown document with one section per story
    - ``csv``: one row per task, columns in this order — ``story, version,
      title, description, status, priority, labels, dependencies`` — with
      multi-value cells (``labels``, ``dependencies``) joined by ``;``. The
      column order is a contract: adding a column later is compatible;
      renaming or reordering one is not.

    **Scope — one target, never two** (the same rule the Trello trigger
    resolves through): no target exports the whole workspace; ``project_id``
    or ``user_story_id`` narrows it to that project or story; both together
    answer ``422 REQUEST_VALIDATION_FAILED``. A target must exist and sit in
    the path workspace (a foreign project or story answers ``403``, a missing
    one ``404``).

    **Version**: without ``extraction_id``, each story's current version (the
    highest-numbered ``completed`` run) is exported — the filter rides the
    serializing statement itself, so a superseded version's tasks can never
    leak into the file. With ``extraction_id`` **and** ``user_story_id``, the
    named version's tasks are exported even when a newer run superseded it —
    the version is identified by its extraction id, never by its version
    number, which is a position in a history the next run moves. An
    ``extraction_id`` without ``user_story_id`` answers ``422``: a version
    belongs to a story, and a version asked for at project or workspace level
    is a question with no answer. The ``version`` column of the CSV carries
    the run's version number; the ``json`` and ``markdown`` shapes are
    unchanged.

    The response includes a ``Content-Disposition`` header for file download,
    unless ``preview=true``: then the exact same body — the same endpoint, the
    same parameters, one code path — is returned **without** that header, so
    the browser displays it instead of saving it. One serialization, two
    dispositions: what a preview shows cannot differ from what the download
    saves, because they are the same bytes.
    """
    workspace, _ = ctx  # validates workspace membership

    if format not in ("json", "markdown", "csv"):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=UNSUPPORTED_EXPORT_FORMAT,
            detail=f"Unsupported format '{format}'. Supported formats: json, markdown, csv",
        )

    try:
        scope = resolve_export_scope(project_id, user_story_id)
    except AmbiguousExportScopeError as exc:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=REQUEST_VALIDATION_FAILED,
            detail=str(exc),
        )

    if extraction_id is not None and user_story_id is None:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=REQUEST_VALIDATION_FAILED,
            detail=(
                "extraction_id requires user_story_id: a version belongs to a "
                "story, so it can only be asked for at story level"
            ),
        )

    if project_id is not None:
        await _validate_project_in_workspace(project_id, workspace, project_repo)
    if user_story_id is not None:
        await _validate_story_in_workspace(user_story_id, workspace, story_repo, project_repo)

    match scope:
        case TrelloExportScope.WORKSPACE:
            tasks = await repo.list_current_by_workspace(workspace.id)
        case TrelloExportScope.PROJECT:
            assert project_id is not None  # resolved by resolve_export_scope
            tasks = await repo.list_current_by_project(project_id)
        case TrelloExportScope.STORY:
            assert user_story_id is not None  # resolved by resolve_export_scope
            if extraction_id is not None:
                # A version named on purpose: no currency predicate, or the
                # selector could never export a superseded version's tasks.
                tasks = await repo.list_by_story_version(user_story_id, extraction_id)
            else:
                tasks = await repo.list_current_by_story(user_story_id)

    task_responses = [
        TaskResponse(
            id=t.id,
            user_story_id=t.user_story_id,
            title=t.title,
            description=t.description,
            status=t.status,
            priority=t.priority,
            labels=t.labels,
            dependencies=t.dependencies,
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in tasks
    ]

    story_text: dict[UUID, str] = {}
    if format in ("markdown", "csv"):
        match scope:
            case TrelloExportScope.WORKSPACE:
                stories = await story_repo.list_by_workspace(workspace.id)
            case TrelloExportScope.PROJECT:
                assert project_id is not None
                stories = await story_repo.list_by_project(project_id)
            case TrelloExportScope.STORY:
                assert user_story_id is not None
                story = await story_repo.find_by_id(user_story_id)
                stories = [story] if story is not None else []
        story_text = {s.id: s.raw_text for s in stories}

    if format == "markdown":
        content = _build_markdown(task_responses, story_text)
        media_type = "text/markdown; charset=utf-8"
        filename = f"tasks-export-{workspace.id}.md"
    elif format == "csv":
        # The version column rides the domain tasks' ``extraction_id`` — the
        # ``TaskResponse`` construction keeps ``extraction_id``/``version_number``
        # unset, so the ``json`` shape stays byte-identical to what it has always
        # produced and the new column costs the other two formats nothing.
        extraction_ids = list({t.extraction_id for t in tasks})
        version_numbers: dict[UUID, int] = (
            await extraction_repo.version_numbers(extraction_ids) if extraction_ids else {}
        )
        version_by_task_id: dict[UUID, int | str] = {
            t.id: version_numbers.get(t.extraction_id, "") for t in tasks
        }
        content = _build_csv(task_responses, story_text, version_by_task_id)
        media_type = "text/csv; charset=utf-8"
        filename = f"tasks-export-{workspace.id}.csv"
    else:
        content = json.dumps(
            [t.model_dump(mode="json") for t in task_responses],
            indent=2,
            ensure_ascii=False,
        )
        media_type = "application/json; charset=utf-8"
        filename = f"tasks-export-{workspace.id}.json"

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'} if not preview else None
    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers=headers,
    )


async def _validate_story_in_workspace(
    user_story_id: UUID,
    workspace: Workspace,
    story_repo: SQLAlchemyUserStoryRepository,
    project_repo: SQLAlchemyProjectRepository,
) -> None:
    """A story target must exist and sit in the path workspace.

    Same shape as the extraction route's validation: a missing story or project
    is a 404, a story whose project belongs to another workspace is a 403
    ``STORY_NOT_IN_WORKSPACE`` — existence and containment reported distinctly.
    """
    story = await story_repo.find_by_id(user_story_id)
    if story is None:
        raise EntityNotFound("UserStory", str(user_story_id))
    project = await project_repo.find_by_id(story.project_id)
    if project is None:
        raise EntityNotFound("UserStory", str(user_story_id))
    if project.workspace_id != workspace.id:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=STORY_NOT_IN_WORKSPACE,
            detail="This user story does not belong to the specified workspace",
        )


async def _validate_project_in_workspace(
    project_id: UUID,
    workspace: Workspace,
    project_repo: SQLAlchemyProjectRepository,
) -> None:
    """A project target must exist and sit in the path workspace."""
    project = await project_repo.find_by_id(project_id)
    if project is None:
        raise EntityNotFound("Project", str(project_id))
    if project.workspace_id != workspace.id:
        raise ApiError(
            status_code=status.HTTP_403_FORBIDDEN,
            error_code=PROJECT_NOT_IN_WORKSPACE,
            detail="This project does not belong to the specified workspace",
        )


async def _resolve_export_credentials(
    workspace: Workspace,
    config_repo: SQLAlchemyWorkspaceTrelloConfigRepository,
) -> WorkspaceTrelloConfig:
    """Return the decrypted credential pair, or refuse the export before anything is created.

    ``409`` and not ``400``: the request shape is fine — what conflicts is the
    workspace's configuration state with the operation, the same posture
    ``ACCOUNT_DELETE_BLOCKED`` takes. The state is fixable (an admin saves the
    pair in the settings), ``GET /settings/trello/status`` exists precisely so a
    member can check it first, and nothing has been created yet — so the answer
    is a conflict, not a malformed request, and never a 500. Half a pair (one
    credential stored, the other blank) is not configured: the export needs both.
    """
    config = await config_repo.get(workspace.id)
    if config is None or not (
        normalize_optional(config.api_key) and normalize_optional(config.token)
    ):
        raise ApiError(
            status_code=status.HTTP_409_CONFLICT,
            error_code=TRELLO_CREDENTIALS_MISSING,
            detail=(
                "This workspace has no Trello credentials configured. "
                "An admin must store the API key and token in the workspace "
                "settings before exporting."
            ),
        )
    return config


@router.post("/trello", status_code=status.HTTP_202_ACCEPTED)
async def export_to_trello(
    body: TrelloExportCreateRequest,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    config_repo: TrelloConfigRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    export_repo: TrelloExportRepoDep = None,  # type: ignore[assignment]
) -> TrelloExportResponse:
    """Send the workspace's current-version tasks to a new Trello board.

    **Asynchronous, like the extraction**: the job row is created pending, the
    work is dispatched with ``asyncio.create_task`` in the API process (D5 — no
    Celery, no Redis), and this answers ``202`` immediately. The client polls
    ``GET .../export/trello/{export_id}`` until the job reaches ``completed``
    (with the board URL) or ``failed`` (with its error code, and the board URL
    too when a half-built board exists).

    **Any member may trigger** (D7): the credentials are what is admin-only —
    the ``/settings/trello`` pair — and the export reads the same tasks
    ``GET .../export/tasks`` already lets any member read. A workspace with no
    credential pair stored answers ``409 TRELLO_CREDENTIALS_MISSING`` before
    anything is created.

    The scope is one of three, never two (D1): both optional targets given is a
    ``422`` — the rule the Kanban cascade applies. Only each story's current
    version is exported (D8), the same filter the file export rides.
    """
    workspace, _ = ctx  # validates workspace membership

    try:
        scope = resolve_export_scope(body.project_id, body.user_story_id)
    except AmbiguousExportScopeError as exc:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=REQUEST_VALIDATION_FAILED,
            detail=str(exc),
        )

    if body.project_id is not None:
        await _validate_project_in_workspace(body.project_id, workspace, project_repo)
    if body.user_story_id is not None:
        await _validate_story_in_workspace(body.user_story_id, workspace, story_repo, project_repo)

    credentials = await _resolve_export_credentials(workspace, config_repo)

    job = await export_repo.save(
        TrelloExport(
            workspace_id=workspace.id,
            scope=scope,
            project_id=body.project_id,
            user_story_id=body.user_story_id,
        )
    )

    # Fire-and-forget, mirroring the extraction dispatch: the route returns
    # before the work runs, and the row is the only thing the client polls.
    asyncio.create_task(
        run_trello_export(
            export_id=job.id,
            workspace_id=workspace.id,
            board_name=workspace.name,
            scope=scope,
            project_id=body.project_id,
            user_story_id=body.user_story_id,
            credentials=credentials,
        )
    )

    return TrelloExportResponse.model_validate(job)


@router.get("/trello/preview")
async def preview_trello_export(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    task_repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    project_repo: ProjectRepoDep = None,  # type: ignore[assignment]
    project_id: UUID | None = Query(None, description="Preview one project's board"),
    user_story_id: UUID | None = Query(None, description="Preview one story's board"),
) -> TrelloBoardPlanResponse:
    """Return the board plan the Trello trigger would send — as JSON, creating nothing.

    The shape (decision E4, record ``export-page-rework``): the board's name,
    its lists in Kanban order, and each card's title, description, labels and
    resolved dependency titles — the same ``TrelloBoardPlan`` the runner builds,
    through the same application entry point (``build_board_plan_for_scope``),
    so the preview can only ever show what the export would create.

    **It describes, it does not perform.** No ``trello_exports`` row is written
    and the workspace's Trello credentials are never read: describing what
    would be exported requires no permission to create it, so a workspace
    without credentials answers the preview instead of ``409``.

    **Scope — the trigger's rule, inherited**: no target previews the whole
    workspace's board; ``project_id`` or ``user_story_id`` narrows it; both
    together answer ``422 REQUEST_VALIDATION_FAILED``, a foreign target ``403``
    and a missing one ``404`` — the same refusals the trigger and the file
    export apply.

    The scope parameters stop at story level for now: a version dimension for
    the Trello export is planned (the same EP that teaches the trigger and the
    plan to carry it) and will join here as a parameter that requires
    ``user_story_id`` — the pairing the file export already enforces. No field
    is invented for it ahead of that decision.
    """
    workspace, _ = ctx  # validates workspace membership

    try:
        scope = resolve_export_scope(project_id, user_story_id)
    except AmbiguousExportScopeError as exc:
        raise ApiError(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            error_code=REQUEST_VALIDATION_FAILED,
            detail=str(exc),
        )

    if project_id is not None:
        await _validate_project_in_workspace(project_id, workspace, project_repo)
    if user_story_id is not None:
        await _validate_story_in_workspace(user_story_id, workspace, story_repo, project_repo)

    plan = await build_board_plan_for_scope(
        workspace_id=workspace.id,
        board_name=workspace.name,
        scope=scope,
        project_id=project_id,
        user_story_id=user_story_id,
        task_repo=task_repo,
        story_repo=story_repo,
    )
    return TrelloBoardPlanResponse.from_plan(plan)


@router.get("/trello/{export_id}")
async def get_trello_export(
    export_id: UUID,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    export_repo: TrelloExportRepoDep = None,  # type: ignore[assignment]
) -> TrelloExportResponse:
    """Report one export job's state, board URL and error code.

    Readable by any member — the same audience that may trigger the export. A
    job of another workspace is reported as a miss (404), so a foreign id is
    not distinguishable from an absent one.
    """
    workspace, _ = ctx
    job = await export_repo.find_by_id(export_id)
    if job is None or job.workspace_id != workspace.id:
        raise ApiError(
            status_code=status.HTTP_404_NOT_FOUND,
            error_code=TRELLO_EXPORT_NOT_FOUND,
            detail=f"Trello export '{export_id}' not found",
        )
    return TrelloExportResponse.model_validate(job)
