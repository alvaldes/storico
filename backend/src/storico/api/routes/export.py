"""Export API routes — export tasks in JSON or Markdown format."""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from storico.api.dependencies import get_current_user, get_repository, get_workspace_for_user
from storico.api.schemas.task import TaskResponse
from storico.domain.entities import User, Workspace, WorkspaceRole
from storico.infrastructure.database.repositories import SQLAlchemyTaskRepository

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/export",
    tags=["export"],
)

TaskRepoDep = Annotated[
    SQLAlchemyTaskRepository,
    Depends(get_repository(SQLAlchemyTaskRepository)),
]


def _build_markdown(tasks: list[TaskResponse]) -> str:
    """Build markdown export from a list of tasks."""
    lines = ["# Tasks Export", "", f"**Total tasks**: {len(tasks)}", ""]
    for i, task in enumerate(tasks, 1):
        lines.append(f"## {i}. {task.title}")
        if task.description:
            lines.append("")
            lines.append(task.description)
        if task.labels:
            lines.append("")
            lines.append(f"**Labels**: {', '.join(task.labels)}")
        if task.dependencies:
            lines.append("")
            lines.append(f"**Dependencies**: {', '.join(task.dependencies)}")
        lines.append(f"\n---\n")
    return "\n".join(lines)


@router.get("/tasks")
async def export_tasks(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    repo: TaskRepoDep = None,  # type: ignore[assignment]
    format: str = Query("json", description="Export format: json or markdown"),
) -> PlainTextResponse:
    """Export tasks from a workspace in the requested format.

    Supported formats:
    - ``json`` (default): JSON array of tasks
    - ``markdown``: Markdown document with task details

    The response includes a ``Content-Disposition`` header for file download.
    """
    workspace, _ = ctx  # validates workspace membership

    if format not in ("json", "markdown"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported format '{format}'. Supported formats: json, markdown",
        )

    tasks = await repo.list_by_workspace(workspace.id)
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
        content = _build_markdown(task_responses)
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
