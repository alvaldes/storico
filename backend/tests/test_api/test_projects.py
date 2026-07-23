"""Integration tests for the Project CRUD API endpoints."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from tests._helpers import create_workspace


class TestCreateProject:
    """POST /api/v1/projects/"""

    async def test_create_project(
        self, async_client, db_session: AsyncSession
    ):
        """POST with valid data returns 201 and a ProjectResponse body."""
        ws = await create_workspace(db_session)
        payload = {
            "name": "My Project",
            "description": "A test project",
            "workspace_id": str(ws.id),
        }
        response = await async_client.post("/api/v1/projects/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "My Project"
        assert data["description"] == "A test project"
        assert data["workspace_id"] == str(ws.id)
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data


class TestListProjects:
    """GET /api/v1/projects/"""

    async def test_list_projects(
        self, async_client, db_session: AsyncSession
    ):
        """POST one project, GET returns it in the items list."""
        ws = await create_workspace(db_session)
        await async_client.post(
            "/api/v1/projects/",
            json={"name": "Project A", "workspace_id": str(ws.id)},
        )

        response = await async_client.get("/api/v1/projects/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["name"] == "Project A"
        assert data["page"] == 1
        assert data["size"] == 20

    async def test_list_projects_empty(self, async_client):
        """GET with no projects returns empty list."""
        response = await async_client.get("/api/v1/projects/")
        assert response.status_code == 200

        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1
        assert data["size"] == 20


class TestGetProject:
    """GET /api/v1/projects/{project_id}"""

    async def test_get_project(
        self, async_client, db_session: AsyncSession
    ):
        """POST then GET by id returns the project."""
        ws = await create_workspace(db_session)
        create_resp = await async_client.post(
            "/api/v1/projects/",
            json={"name": "Target", "workspace_id": str(ws.id)},
        )
        project_id = create_resp.json()["id"]

        response = await async_client.get(f"/api/v1/projects/{project_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "Target"
        assert data["workspace_id"] == str(ws.id)

    async def test_get_project_not_found(self, async_client):
        """GET with a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await async_client.get(f"/api/v1/projects/{fake_id}")
        assert response.status_code == 404

        data = response.json()
        assert "detail" in data
        assert data["type"] == "entity_not_found"


class TestUpdateProject:
    """PUT /api/v1/projects/{project_id}"""

    async def test_update_project(
        self, async_client, db_session: AsyncSession
    ):
        """POST then PUT updates the project fields."""
        ws = await create_workspace(db_session)
        create_resp = await async_client.post(
            "/api/v1/projects/",
            json={
                "name": "Before",
                "description": "Old desc",
                "workspace_id": str(ws.id),
            },
        )
        project_id = create_resp.json()["id"]

        response = await async_client.put(
            f"/api/v1/projects/{project_id}",
            json={"name": "After", "description": "New desc"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["name"] == "After"
        assert data["description"] == "New desc"
        assert data["id"] == project_id

    async def test_update_project_not_found(self, async_client):
        """PUT on a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await async_client.put(
            f"/api/v1/projects/{fake_id}",
            json={"name": "Nope"},
        )
        assert response.status_code == 404

        data = response.json()
        assert data["type"] == "entity_not_found"


class TestDeleteProject:
    """DELETE /api/v1/projects/{project_id}"""

    async def test_delete_project(
        self, async_client, db_session: AsyncSession
    ):
        """POST then DELETE returns 204."""
        ws = await create_workspace(db_session)
        create_resp = await async_client.post(
            "/api/v1/projects/",
            json={"name": "To Delete", "workspace_id": str(ws.id)},
        )
        project_id = create_resp.json()["id"]

        response = await async_client.delete(f"/api/v1/projects/{project_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await async_client.get(f"/api/v1/projects/{project_id}")
        assert get_resp.status_code == 404

    async def test_delete_project_not_found(self, async_client):
        """DELETE on a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await async_client.delete(f"/api/v1/projects/{fake_id}")
        assert response.status_code == 404

        data = response.json()
        assert data["type"] == "entity_not_found"
