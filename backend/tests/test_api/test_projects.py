"""Integration tests for the Project CRUD API endpoints."""

from uuid import uuid4


class TestCreateProject:
    """POST /api/v1/projects/"""

    async def test_create_project(self, async_client):
        """POST with valid data returns 201 and a ProjectResponse body."""
        owner_id = uuid4()
        payload = {
            "name": "My Project",
            "description": "A test project",
            "owner_id": str(owner_id),
        }
        response = await async_client.post("/api/v1/projects/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "My Project"
        assert data["description"] == "A test project"
        assert data["owner_id"] == str(owner_id)
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data


class TestListProjects:
    """GET /api/v1/projects/"""

    async def test_list_projects(self, async_client):
        """POST one project, GET returns it in the items list."""
        await async_client.post(
            "/api/v1/projects/",
            json={"name": "Project A", "owner_id": str(uuid4())},
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

    async def test_get_project(self, async_client):
        """POST then GET by id returns the project."""
        owner_id = uuid4()
        create_resp = await async_client.post(
            "/api/v1/projects/",
            json={"name": "Target", "owner_id": str(owner_id)},
        )
        project_id = create_resp.json()["id"]

        response = await async_client.get(f"/api/v1/projects/{project_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == project_id
        assert data["name"] == "Target"
        assert data["owner_id"] == str(owner_id)

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

    async def test_update_project(self, async_client):
        """POST then PUT updates the project fields."""
        create_resp = await async_client.post(
            "/api/v1/projects/",
            json={"name": "Before", "description": "Old desc", "owner_id": str(uuid4())},
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

    async def test_delete_project(self, async_client):
        """POST then DELETE returns 204."""
        create_resp = await async_client.post(
            "/api/v1/projects/",
            json={"name": "To Delete", "owner_id": str(uuid4())},
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
