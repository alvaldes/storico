"""Integration tests for the Export API endpoint — GET /api/v1/workspaces/{id}/export/tasks.

Tests content-type, filename header, content shape for JSON and Markdown,
and error handling for unknown format.
"""

from uuid import uuid4

import jwt as pyjwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import Task, User
from storico.domain.entities.project import Project
from storico.domain.entities.user_story import UserStory
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
from storico.infrastructure.database.repositories import (
    SQLAlchemyTaskRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyWorkspaceMemberRepository,
    SQLAlchemyWorkspaceRepository,
)
from storico.infrastructure.database.repositories.project_repository import (
    SQLAlchemyProjectRepository,
)
from storico.infrastructure.database.repositories.user_story_repository import (
    SQLAlchemyUserStoryRepository,
)

def _get_jwt_secret() -> str:
    """Load the JWT secret from Settings (respects env overrides)."""
    from storico.config.settings import Settings

    return Settings.load().auth_jwt_secret


def _auth_headers(user_id: str) -> dict:
    secret = _get_jwt_secret()
    token = pyjwt.encode({"sub": user_id}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _create_user(db_session: AsyncSession) -> User:
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email="export@test.com", name="Export Test")
    saved = await repo.save(user)
    await repo.link_account(saved.id, "google", "g-export-test")
    return saved


async def _create_workspace(
    db_session: AsyncSession, user_id, name="Export Workspace"
) -> Workspace:
    repo = SQLAlchemyWorkspaceRepository(db_session)
    ws = Workspace(name=name, slug=name.lower().replace(" ", "-"), owner_id=user_id)
    saved = await repo.save(ws)
    # Add membership
    member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
    member = WorkspaceMember(
        workspace_id=saved.id, user_id=user_id, role=WorkspaceRole.ADMIN
    )
    await member_repo.add(member)
    return saved


async def _create_story(
    db_session: AsyncSession, workspace_id
) -> UserStory:
    project_repo = SQLAlchemyProjectRepository(db_session)
    project = Project(
        name="Test Project",
        workspace_id=workspace_id,
    )
    project = await project_repo.save(project)

    story_repo = SQLAlchemyUserStoryRepository(db_session)
    story = UserStory(
        project_id=project.id,
        actor="user",
        feature="log in",
        benefit="access account",
        raw_text="As a user, I want to log in so that I can access my account",
    )
    return await story_repo.save(story)


async def _create_tasks(
    db_session: AsyncSession, story_id, count=3
) -> list[Task]:
    repo = SQLAlchemyTaskRepository(db_session)
    tasks = []
    for i in range(count):
        task = Task(
            user_story_id=story_id,
            title=f"Task {i + 1}",
            description=f"Description for task {i + 1}",
            status="todo",
            priority="medium",
            labels=["backend", "api"] if i == 0 else ["frontend"],
            dependencies=[],
        )
        saved = await repo.save(task)
        tasks.append(saved)
    return tasks


class TestExportTasks:
    """GET /api/v1/workspaces/{workspace_id}/export/tasks"""

    @pytest.mark.asyncio
    async def test_export_json(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET ?format=json returns JSON with correct content-type and filename."""
        user = await _create_user(db_session)
        ws = await _create_workspace(db_session, user.id)
        story = await _create_story(db_session, ws.id)
        await _create_tasks(db_session, story.id, count=2)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json; charset=utf-8"
        assert (
            response.headers["content-disposition"]
            == f'attachment; filename="tasks-export-{ws.id}.json"'
        )

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["title"] == "Task 1"
        assert data[0]["description"] == "Description for task 1"
        assert data[0]["labels"] == ["backend", "api"]
        assert "created_at" in data[0]
        assert "updated_at" in data[0]

    @pytest.mark.asyncio
    async def test_export_markdown(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET ?format=markdown returns Markdown with correct headers."""
        user = await _create_user(db_session)
        ws = await _create_workspace(db_session, user.id)
        story = await _create_story(db_session, ws.id)
        await _create_tasks(db_session, story.id, count=1)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/export/tasks?format=markdown",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert (
            response.headers["content-disposition"]
            == f'attachment; filename="tasks-export-{ws.id}.md"'
        )

        content = response.text
        assert "# Tasks Export" in content
        assert "**Total tasks**: 1" in content
        assert "## 1. Task 1" in content
        assert "Description for task 1" in content
        assert "**Labels**: backend, api" in content

    @pytest.mark.asyncio
    async def test_export_json_empty(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET with no tasks returns empty JSON array."""
        user = await _create_user(db_session)
        ws = await _create_workspace(db_session, user.id)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_export_markdown_empty(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET with no tasks returns Markdown with zero count."""
        user = await _create_user(db_session)
        ws = await _create_workspace(db_session, user.id)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/export/tasks?format=markdown",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        assert "# Tasks Export" in response.text
        assert "**Total tasks**: 0" in response.text

    @pytest.mark.asyncio
    async def test_export_json_tasks_have_all_fields(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET ?format=json returns all expected task fields."""
        user = await _create_user(db_session)
        ws = await _create_workspace(db_session, user.id)
        story = await _create_story(db_session, ws.id)
        await _create_tasks(db_session, story.id, count=1)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        task = response.json()[0]
        assert "id" in task
        assert "user_story_id" in task
        assert "title" in task
        assert "description" in task
        assert "status" in task
        assert "priority" in task
        assert "labels" in task
        assert "dependencies" in task
        assert "created_at" in task
        assert "updated_at" in task

    @pytest.mark.asyncio
    async def test_export_markdown_labels_and_deps(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET ?format=markdown renders labels and dependencies."""
        user = await _create_user(db_session)
        ws = await _create_workspace(db_session, user.id)
        story = await _create_story(db_session, ws.id)
        task_repo = SQLAlchemyTaskRepository(db_session)
        task = Task(
            user_story_id=story.id,
            title="Task with meta",
            description="Has labels and deps",
            status="todo",
            priority="high",
            labels=["db", "backend"],
            dependencies=["US-001", "US-002"],
        )
        await task_repo.save(task)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/export/tasks?format=markdown",
            headers=_auth_headers(str(user.id)),
        )
        assert "**Labels**: db, backend" in response.text
        assert "**Dependencies**: US-001, US-002" in response.text

    @pytest.mark.asyncio
    async def test_export_unknown_format(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET with unsupported format returns 400."""
        user = await _create_user(db_session)
        ws = await _create_workspace(db_session, user.id)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws.id}/export/tasks?format=csv",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 400
        assert "Unsupported format" in response.text

    @pytest.mark.asyncio
    async def test_export_unauthorized(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET without auth headers returns 401."""
        ws_id = uuid4()
        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/export/tasks?format=json",
            headers={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_workspace_not_found(
        self, async_client, db_session: AsyncSession
    ) -> None:
        """GET with non-existent workspace returns 404."""
        user = await _create_user(db_session)
        fake_id = uuid4()

        response = await async_client.get(
            f"/api/v1/workspaces/{fake_id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 404
