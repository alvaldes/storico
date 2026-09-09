"""Integration tests for the UserStory CRUD API endpoints.

Tests must seed a workspace and project because the API validates that the
story's project exists and the authenticated user is a member of its workspace.
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import User
from storico.domain.entities.project import Project
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
from storico.infrastructure.database.repositories import (
    SQLAlchemyWorkspaceMemberRepository,
    SQLAlchemyWorkspaceRepository,
)
from storico.infrastructure.database.repositories.project_repository import (
    SQLAlchemyProjectRepository,
)

RAW_TEXT = "As a user, I want to log in so that I can access my account"


async def _seed_workspace_and_project(
    db_session: AsyncSession, user: User
) -> tuple[Workspace, Project]:
    """Create a workspace (user as owner + admin member) and a project in it."""
    ws_repo = SQLAlchemyWorkspaceRepository(db_session)
    ws = Workspace(
        name="Test Workspace",
        slug="test-workspace",
        owner_id=user.id,
    )
    ws = await ws_repo.save(ws)

    member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
    member = WorkspaceMember(
        workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.ADMIN
    )
    await member_repo.add(member)

    project_repo = SQLAlchemyProjectRepository(db_session)
    project = Project(name="Test Project", workspace_id=ws.id)
    project = await project_repo.save(project)

    return ws, project


async def _seed_second_workspace(
    db_session: AsyncSession, user: User
) -> Workspace:
    """Create a second workspace for multi-project tests."""
    ws_repo = SQLAlchemyWorkspaceRepository(db_session)
    ws = Workspace(name="WS 2", slug="ws-2", owner_id=user.id)
    ws = await ws_repo.save(ws)

    member_repo = SQLAlchemyWorkspaceMemberRepository(db_session)
    await member_repo.add(
        WorkspaceMember(
            workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.ADMIN
        )
    )
    return ws


class TestCreateStory:
    """POST /api/v1/stories/"""

    async def test_create_story(
        self, authed_client, db_session: AsyncSession, authed_user: User
    ):
        """POST with valid data returns 201 and a UserStoryResponse body."""
        _, project = await _seed_workspace_and_project(db_session, authed_user)
        payload = {
            "project_id": str(project.id),
            "actor": "user",
            "feature": "log in",
            "benefit": "access my account",
            "raw_text": RAW_TEXT,
        }
        response = await authed_client.post("/api/v1/stories/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["actor"] == "user"
        assert data["feature"] == "log in"
        assert data["benefit"] == "access my account"
        assert data["raw_text"] == RAW_TEXT
        assert data["project_id"] == str(project.id)
        assert "id" in data
        assert "created_at" in data

    async def test_create_duplicate_story_fails(
        self, authed_client, db_session: AsyncSession, authed_user: User
    ):
        """POST with same raw_text in same project returns 409 conflict."""
        _, project = await _seed_workspace_and_project(db_session, authed_user)
        payload = {
            "project_id": str(project.id),
            "actor": "user",
            "feature": "log in",
            "benefit": "access my account",
            "raw_text": RAW_TEXT,
        }
        # First creation succeeds
        response1 = await authed_client.post("/api/v1/stories/", json=payload)
        assert response1.status_code == 201

        # Second creation with same raw_text fails
        response2 = await authed_client.post("/api/v1/stories/", json=payload)
        assert response2.status_code == 409
        data = response2.json()
        assert data["type"] == "duplicate_entity"
        assert "raw_text" in data["detail"].lower()


class TestListStories:
    """GET /api/v1/stories/"""

    async def test_list_stories(
        self, authed_client, db_session: AsyncSession, authed_user: User
    ):
        """POST one story, GET returns it in the items list."""
        _, project = await _seed_workspace_and_project(db_session, authed_user)
        await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project.id),
                "actor": "user",
                "feature": "view profile",
                "benefit": "see my details",
                "raw_text": RAW_TEXT,
            },
        )

        response = await authed_client.get("/api/v1/stories/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["feature"] == "view profile"
        assert data["page"] == 1

    async def test_list_stories_empty(self, authed_client):
        """GET with no stories returns empty list."""
        response = await authed_client.get("/api/v1/stories/")
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0

    async def test_list_stories_by_project(
        self, authed_client, db_session: AsyncSession, authed_user: User
    ):
        """GET ?project_id= filters stories by project."""
        _, project_a = await _seed_workspace_and_project(db_session, authed_user)
        ws2 = await _seed_second_workspace(db_session, authed_user)
        project_repo = SQLAlchemyProjectRepository(db_session)
        project_b = await project_repo.save(
            Project(name="Project B", workspace_id=ws2.id)
        )

        await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project_a.id),
                "actor": "user",
                "feature": "feature A",
                "benefit": "benefit",
                "raw_text": RAW_TEXT,
            },
        )
        await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project_b.id),
                "actor": "admin",
                "feature": "feature B",
                "benefit": "benefit",
                "raw_text": RAW_TEXT,
            },
        )

        # Filter by project_b
        response = await authed_client.get(
            f"/api/v1/stories/?project_id={project_b.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["feature"] == "feature B"


class TestGetStory:
    """GET /api/v1/stories/{story_id}"""

    async def test_get_story(
        self, authed_client, db_session: AsyncSession, authed_user: User
    ):
        """POST then GET by id returns the story."""
        _, project = await _seed_workspace_and_project(db_session, authed_user)
        create_resp = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project.id),
                "actor": "user",
                "feature": "get story",
                "benefit": "test retrieval",
                "raw_text": RAW_TEXT,
            },
        )
        story_id = create_resp.json()["id"]

        response = await authed_client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200
        assert response.json()["id"] == story_id
        assert response.json()["feature"] == "get story"

    async def test_get_story_not_found(self, authed_client):
        """GET with a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await authed_client.get(f"/api/v1/stories/{fake_id}")
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"


class TestUpdateStory:
    """PUT /api/v1/stories/{story_id}"""

    async def test_update_story(
        self, authed_client, db_session: AsyncSession, authed_user: User
    ):
        """POST then PUT updates the story fields."""
        _, project = await _seed_workspace_and_project(db_session, authed_user)
        create_resp = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project.id),
                "actor": "user",
                "feature": "old feature",
                "benefit": "old benefit",
                "raw_text": RAW_TEXT,
            },
        )
        story_id = create_resp.json()["id"]

        response = await authed_client.put(
            f"/api/v1/stories/{story_id}",
            json={"actor": "admin", "feature": "new feature"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["actor"] == "admin"
        assert data["feature"] == "new feature"
        assert data["benefit"] == "old benefit"  # unchanged


class TestDeleteStory:
    """DELETE /api/v1/stories/{story_id}"""

    async def test_delete_story(
        self, authed_client, db_session: AsyncSession, authed_user: User
    ):
        """POST then DELETE returns 204."""
        _, project = await _seed_workspace_and_project(db_session, authed_user)
        create_resp = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project.id),
                "actor": "user",
                "feature": "to delete",
                "benefit": "gone",
                "raw_text": RAW_TEXT,
            },
        )
        story_id = create_resp.json()["id"]

        response = await authed_client.delete(f"/api/v1/stories/{story_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await authed_client.get(f"/api/v1/stories/{story_id}")
        assert get_resp.status_code == 404

    async def test_delete_story_not_found(self, authed_client):
        """DELETE on a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await authed_client.delete(f"/api/v1/stories/{fake_id}")
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"
