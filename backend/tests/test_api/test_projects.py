"""Integration tests for the Project CRUD API endpoints.

Tests exercise workspace-scoped routes at ``/api/v1/workspaces/{ws_id}/projects/``.
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities.user import User
from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from tests._helpers import create_workspace


def _make_member(
    db_session: AsyncSession, ws_id, user_id: str
) -> None:
    """Add a user as ADMIN member of a workspace."""
    import asyncio

    repo = SQLAlchemyWorkspaceMemberRepository(db_session)
    member = WorkspaceMember(
        workspace_id=ws_id,
        user_id=user_id,
        role=WorkspaceRole.ADMIN,
    )
    asyncio.get_event_loop().run_until_complete(repo.add(member))


class TestCreateProject:
    """POST /api/v1/workspaces/{workspace_id}/projects/"""

    async def test_create_project(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """POST with valid data returns 201 and a ProjectResponse body."""
        ws = await create_workspace(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=authed_user.id,
            role=WorkspaceRole.ADMIN,
        )
        await member_repo.add(member)

        payload = {
            "name": "My Project",
            "description": "A test project",
        }
        response = await authed_client.post(
            f"/api/v1/workspaces/{ws.id}/projects/", json=payload
        )
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "My Project"
        assert data["description"] == "A test project"
        assert data["workspace_id"] == str(ws.id)
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data


class TestListProjects:
    """GET /api/v1/workspaces/{workspace_id}/projects/"""

    async def test_list_projects(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """POST one project, GET returns it in the items list."""
        ws = await create_workspace(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=authed_user.id,
            role=WorkspaceRole.ADMIN,
        )
        await member_repo.add(member)

        await authed_client.post(
            f"/api/v1/workspaces/{ws.id}/projects/",
            json={"name": "Project A"},
        )

        response = await authed_client.get(
            f"/api/v1/workspaces/{ws.id}/projects/"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Project A"
        assert data["page"] == 1
        assert data["size"] == 20

    async def test_list_projects_empty(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """GET with no projects returns empty list."""
        ws = await create_workspace(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=authed_user.id,
            role=WorkspaceRole.ADMIN,
        )
        await member_repo.add(member)

        response = await authed_client.get(
            f"/api/v1/workspaces/{ws.id}/projects/"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 20


class TestGetProject:
    """GET /api/v1/workspaces/{workspace_id}/projects/{project_id}"""

    async def test_get_project(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """POST then GET by id returns the project."""
        ws = await create_workspace(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=authed_user.id,
            role=WorkspaceRole.ADMIN,
        )
        await member_repo.add(member)

        create_resp = await authed_client.post(
            f"/api/v1/workspaces/{ws.id}/projects/",
            json={"name": "Target"},
        )
        project_id = create_resp.json()["id"]

        response = await authed_client.get(
            f"/api/v1/workspaces/{ws.id}/projects/{project_id}"
        )
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "Target"
        assert data["workspace_id"] == str(ws.id)

    async def test_get_project_not_found(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """GET with a non-existent UUID returns 404."""
        ws = await create_workspace(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=authed_user.id,
            role=WorkspaceRole.ADMIN,
        )
        await member_repo.add(member)

        fake_id = str(uuid4())
        response = await authed_client.get(
            f"/api/v1/workspaces/{ws.id}/projects/{fake_id}"
        )
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert data["type"] == "entity_not_found"


class TestUpdateProject:
    """PUT /api/v1/workspaces/{workspace_id}/projects/{project_id}"""

    async def test_update_project(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """POST then PUT updates the project fields."""
        ws = await create_workspace(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=authed_user.id,
            role=WorkspaceRole.ADMIN,
        )
        await member_repo.add(member)

        create_resp = await authed_client.post(
            f"/api/v1/workspaces/{ws.id}/projects/",
            json={"name": "Before", "description": "Old desc"},
        )
        project_id = create_resp.json()["id"]

        response = await authed_client.put(
            f"/api/v1/workspaces/{ws.id}/projects/{project_id}",
            json={"name": "After", "description": "New desc"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "After"
        assert data["description"] == "New desc"
        assert data["id"] == project_id

    async def test_update_project_not_found(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """PUT on a non-existent UUID returns 404."""
        ws = await create_workspace(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=authed_user.id,
            role=WorkspaceRole.ADMIN,
        )
        await member_repo.add(member)

        fake_id = str(uuid4())
        response = await authed_client.put(
            f"/api/v1/workspaces/{ws.id}/projects/{fake_id}",
            json={"name": "Nope"},
        )
        assert response.status_code == 404

        data = response.json()
        assert data["type"] == "entity_not_found"


class TestDeleteProject:
    """DELETE /api/v1/workspaces/{workspace_id}/projects/{project_id}"""

    async def test_delete_project(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """POST then DELETE returns 204."""
        ws = await create_workspace(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=authed_user.id,
            role=WorkspaceRole.ADMIN,
        )
        await member_repo.add(member)

        create_resp = await authed_client.post(
            f"/api/v1/workspaces/{ws.id}/projects/",
            json={"name": "To Delete"},
        )
        project_id = create_resp.json()["id"]

        response = await authed_client.delete(
            f"/api/v1/workspaces/{ws.id}/projects/{project_id}"
        )
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await authed_client.get(
            f"/api/v1/workspaces/{ws.id}/projects/{project_id}"
        )
        assert get_resp.status_code == 404

    async def test_delete_project_not_found(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """DELETE on a non-existent UUID returns 404."""
        ws = await create_workspace(db_session)
        member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
        member = WorkspaceMember(
            workspace_id=ws.id,
            user_id=authed_user.id,
            role=WorkspaceRole.ADMIN,
        )
        await member_repo.add(member)

        fake_id = str(uuid4())
        response = await authed_client.delete(
            f"/api/v1/workspaces/{ws.id}/projects/{fake_id}"
        )
        assert response.status_code == 404

        data = response.json()
        assert data["type"] == "entity_not_found"
