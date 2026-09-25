"""Integration tests for the Project CRUD API endpoints.

Tests exercise workspace-scoped routes at ``/api/v1/workspaces/{ws_id}/projects/``.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from storico.domain.entities.project import Project
from storico.domain.entities.user import User
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
from storico.infrastructure.database.repositories.project_repository import (
    SQLAlchemyProjectRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from tests._helpers import create_workspace
from tests.test_api.test_unfiltered_list_queries import ReadsOf


def _make_member(db_session: AsyncSession, ws_id: UUID, user_id: UUID) -> None:
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

    async def test_create_project(self, authed_client, authed_user: User, db_session: AsyncSession):
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
        response = await authed_client.post(f"/api/v1/workspaces/{ws.id}/projects/", json=payload)
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

    async def test_list_projects(self, authed_client, authed_user: User, db_session: AsyncSession):
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

        response = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/")
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

        response = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 20


class TestListProjectsPagination:
    """GET /api/v1/workspaces/{workspace_id}/projects/ with paging params."""

    async def _seed_workspace_with_projects(
        self, db_session: AsyncSession, user: User, count: int = 3
    ) -> Workspace:
        """Seed a workspace the caller administers, with ``count`` projects.

        Projects get explicit ``created_at`` values one day apart so tests
        assert the SQL ordering rule, not wall-clock insertion order.
        """
        ws = await create_workspace(db_session)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.ADMIN)
        )
        repo = SQLAlchemyProjectRepository(db_session)
        for day in range(1, count + 1):
            await repo.save(
                Project(
                    name=f"Project day {day}",
                    workspace_id=ws.id,
                    created_at=datetime(2026, 1, day),
                )
            )
        return ws

    async def test_page_one_returns_two_items_and_full_total(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """?page=1&size=2 returns the first two of three projects, total 3."""
        ws = await self._seed_workspace_with_projects(db_session, authed_user)

        response = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/?page=1&size=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["size"] == 2

    async def test_page_two_returns_the_last_item_with_full_total(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """?page=2&size=2 returns the remaining project, still total 3."""
        ws = await self._seed_workspace_with_projects(db_session, authed_user)

        response = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/?page=2&size=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 1
        assert data["total"] == 3

    async def test_page_past_the_end_returns_no_items_and_the_real_total(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """?page=9&size=2 returns 0 items but total 3 — not a page count.

        This is the fallback path: an empty page carries the real total so
        clients can still render '3 projects' while showing no rows.
        """
        ws = await self._seed_workspace_with_projects(db_session, authed_user)

        response = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/?page=9&size=2")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3

    async def test_list_orders_by_created_at_desc(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """The newest project comes first, per the created_at DESC rule."""
        ws = await self._seed_workspace_with_projects(db_session, authed_user)

        response = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/")

        assert response.status_code == 200
        names = [item["name"] for item in response.json()["items"]]
        assert names == ["Project day 3", "Project day 2", "Project day 1"]

    async def test_list_reads_projects_exactly_once(
        self,
        authed_client,
        authed_user: User,
        db_session: AsyncSession,
        test_engine: AsyncEngine,
    ):
        """The list reads the projects table in exactly one statement.

        The dev database is a pooler where one statement costs ~2s, so the
        page, its story counts and its total must ride on a single query —
        no per-project count and no separate COUNT(*).
        """
        ws = await self._seed_workspace_with_projects(db_session, authed_user)

        with ReadsOf(test_engine, "projects") as reads:
            response = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/")

        assert response.status_code == 200
        assert len(reads.statements) == 1, (
            f"the project list read 'projects' {len(reads.statements)} times; "
            "page, counts and total must come from one statement"
        )


class TestGetProject:
    """GET /api/v1/workspaces/{workspace_id}/projects/{project_id}"""

    async def test_get_project(self, authed_client, authed_user: User, db_session: AsyncSession):
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

        response = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/{project_id}")
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
        response = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/{fake_id}")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert data["type"] == "entity_not_found"


class TestUpdateProject:
    """PUT /api/v1/workspaces/{workspace_id}/projects/{project_id}"""

    async def test_update_project(self, authed_client, authed_user: User, db_session: AsyncSession):
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

    async def test_delete_project(self, authed_client, authed_user: User, db_session: AsyncSession):
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

        response = await authed_client.delete(f"/api/v1/workspaces/{ws.id}/projects/{project_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await authed_client.get(f"/api/v1/workspaces/{ws.id}/projects/{project_id}")
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
        response = await authed_client.delete(f"/api/v1/workspaces/{ws.id}/projects/{fake_id}")
        assert response.status_code == 404

        data = response.json()
        assert data["type"] == "entity_not_found"


async def _seed_project_in_a_sibling_workspace(
    db_session: AsyncSession, user: User
) -> tuple[Workspace, UUID]:
    """Seed two workspaces the caller belongs to, with a project in the second.

    Returns ``(addressed, project_id)``: the caller is an ADMIN of *both*
    workspaces, so every membership check along the route succeeds and the path
    workspace ``addressed`` — which holds no project — is the only thing the
    request has in common with the project's real workspace.
    """
    member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
    addressed = await create_workspace(
        db_session,
        name="Addressed Workspace",
        slug=f"addressed-ws-{uuid4().hex[:8]}",
        owner_id=user.id,
    )
    owner_of_project = await create_workspace(
        db_session,
        name="Owning Workspace",
        slug=f"owning-ws-{uuid4().hex[:8]}",
        owner_id=user.id,
    )
    for workspace in (addressed, owner_of_project):
        await member_repo.add(
            WorkspaceMember(
                workspace_id=workspace.id,
                user_id=user.id,
                role=WorkspaceRole.ADMIN,
            )
        )

    project = await SQLAlchemyProjectRepository(db_session).save(
        Project(name="Project elsewhere", workspace_id=owner_of_project.id)
    )
    return addressed, project.id


class TestProjectContainment:
    """Addressing a project through a workspace that does not own it.

    ``_verify_project_belongs_to_workspace`` separates two facts that used to
    share a single 404: the project **does not exist** at all (still
    ``EntityNotFound``) and the project **exists but belongs to another
    workspace** — now a 403, matching the parallel story-containment check in
    ``test_extraction.py``. Because the caller is a member of both workspaces,
    only containment can turn these requests into 4xx.
    """

    async def test_get_project_is_forbidden_in_another_workspace(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """GET a project through a sibling workspace returns 403 with its own detail.

        The 404/403 split is the contract: existence keeps answering
        ``entity_not_found``, while containment gets the forbidding status and a
        detail parallel to the story case. Asserting the exact string keeps the
        two error kinds from collapsing back into one.
        """
        addressed, project_id = await _seed_project_in_a_sibling_workspace(db_session, authed_user)

        response = await authed_client.get(
            f"/api/v1/workspaces/{addressed.id}/projects/{project_id}"
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "This project does not belong to the specified workspace"
        )

    async def test_update_project_is_forbidden_in_another_workspace(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """PUT through a sibling workspace returns 403 and must not persist anything.

        The containment check runs before the update is built, so the foreign
        project must come back unchanged when re-read through its real
        workspace: a 403 that still applied the write would be worse than a 404.
        """
        addressed, project_id = await _seed_project_in_a_sibling_workspace(db_session, authed_user)

        response = await authed_client.put(
            f"/api/v1/workspaces/{addressed.id}/projects/{project_id}",
            json={"name": "Renamed by a non-owner workspace"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "This project does not belong to the specified workspace"
        )

        unchanged = await SQLAlchemyProjectRepository(db_session).find_by_id(project_id)
        assert unchanged is not None
        assert unchanged.name == "Project elsewhere"

    async def test_delete_project_is_forbidden_in_another_workspace(
        self, authed_client, authed_user: User, db_session: AsyncSession
    ):
        """DELETE through a sibling workspace returns 403 and leaves the row alive.

        The delete handler discards the helper's story count, so this also pins
        that the 403 is raised rather than swallowed on the way to
        ``repo.delete``.
        """
        addressed, project_id = await _seed_project_in_a_sibling_workspace(db_session, authed_user)

        response = await authed_client.delete(
            f"/api/v1/workspaces/{addressed.id}/projects/{project_id}"
        )

        assert response.status_code == 403
        assert response.json()["detail"] == (
            "This project does not belong to the specified workspace"
        )

        still_there = await SQLAlchemyProjectRepository(db_session).find_by_id(project_id)
        assert still_there is not None
