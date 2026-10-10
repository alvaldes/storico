"""Export API routes — file export (JSON/Markdown) and the Trello board export."""

import asyncio
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
from storico.api.schemas.trello_export import TrelloExportCreateRequest, TrelloExportResponse
from storico.application.export.export_workspace_to_trello import (
    AmbiguousExportScopeError,
    resolve_export_scope,
    run_trello_export,
)
from storico.domain.entities import EntityNotFound, Workspace, WorkspaceRole
from storico.domain.entities.trello_export import TrelloExport
from storico.domain.entities.workspace_trello_config import WorkspaceTrelloConfig
from storico.domain.services.dependency_resolution import (
    build_dependency_title_index,
    resolve_dependency,
)
from storico.domain.services.llm_config_readiness import normalize_optional
from storico.infrastructure.database.repositories import (
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


@router.get("/tasks")
async def export_tasks(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    story_repo: StoryRepoDep = None,  # type: ignore[assignment]
    format: str = Query("json", description="Export format: json or markdown"),
) -> PlainTextResponse:
    """Export tasks from a workspace in the requested format.

    Supported formats:
    - ``json`` (default): JSON array of tasks
    - ``markdown``: Markdown document with one section per story

    Only each story's current version (the highest-numbered ``completed``
    run) is exported — the filter rides the serializing statement itself, so
    a superseded version's tasks can never leak into a file.

    The response includes a ``Content-Disposition`` header for file download.
    """
    workspace, _ = ctx  # validates workspace membership

    if format not in ("json", "markdown"):
        raise ApiError(
            status_code=status.HTTP_400_BAD_REQUEST,
            error_code=UNSUPPORTED_EXPORT_FORMAT,
            detail=f"Unsupported format '{format}'. Supported formats: json, markdown",
        )

    tasks = await repo.list_current_by_workspace(workspace.id)
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

    if format == "markdown":
        stories = await story_repo.list_by_workspace(workspace.id)
        story_text: dict[UUID, str] = {s.id: s.raw_text for s in stories}
        content = _build_markdown(task_responses, story_text)
        media_type = "text/markdown; charset=utf-8"
        filename = f"tasks-export-{workspace.id}.md"
    else:
        content = json.dumps(
            [t.model_dump(mode="json") for t in task_responses],
            indent=2,
            ensure_ascii=False,
        )
        media_type = "application/json; charset=utf-8"
        filename = f"tasks-export-{workspace.id}.json"

    return PlainTextResponse(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
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
