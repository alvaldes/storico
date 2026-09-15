"""Export API routes — export tasks in JSON or Markdown format."""

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import PlainTextResponse

from storico.api.dependencies import get_repository, get_workspace_for_user
from storico.api.schemas.task import TaskResponse
from storico.domain.entities import Workspace, WorkspaceRole
from storico.infrastructure.database.repositories import (
    SQLAlchemyTaskRepository,
    SQLAlchemyUserStoryRepository,
)

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


def _build_markdown(tasks: list[TaskResponse], story_text: dict[UUID, str]) -> str:
    """Build a Markdown export grouped by story.

    One section per story (``## {story text}``), each task rendered as a
    ``- **{title}** — {description}`` bullet, labels as ``#label`` inline, and
    dependencies as ``→ {title}`` references.
    """
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
                bullet += " " + " ".join(f"→ {dep}" for dep in task.dependencies)
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
