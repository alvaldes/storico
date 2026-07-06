"""Integration tests for the UserStory CRUD API endpoints."""

from uuid import uuid4

RAW_TEXT = "As a user, I want to log in so that I can access my account"


class TestCreateStory:
    """POST /api/v1/stories/"""

    async def test_create_story(self, async_client):
        """POST with valid data returns 201 and a UserStoryResponse body."""
        project_id = uuid4()
        payload = {
            "project_id": str(project_id),
            "actor": "user",
            "feature": "log in",
            "benefit": "access my account",
            "raw_text": RAW_TEXT,
        }
        response = await async_client.post("/api/v1/stories/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["actor"] == "user"
        assert data["feature"] == "log in"
        assert data["benefit"] == "access my account"
        assert data["raw_text"] == RAW_TEXT
        assert data["project_id"] == str(project_id)
        assert "id" in data
        assert "created_at" in data


class TestListStories:
    """GET /api/v1/stories/"""

    async def test_list_stories(self, async_client):
        """POST one story, GET returns it in the items list."""
        await async_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(uuid4()),
                "actor": "user",
                "feature": "view profile",
                "benefit": "see my details",
                "raw_text": RAW_TEXT,
            },
        )

        response = await async_client.get("/api/v1/stories/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["feature"] == "view profile"
        assert data["page"] == 1

    async def test_list_stories_empty(self, async_client):
        """GET with no stories returns empty list."""
        response = await async_client.get("/api/v1/stories/")
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0

    async def test_list_stories_by_project(self, async_client):
        """GET ?project_id= filters stories by project."""
        project_a = uuid4()
        project_b = uuid4()

        await async_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project_a),
                "actor": "user",
                "feature": "feature A",
                "benefit": "benefit",
                "raw_text": RAW_TEXT,
            },
        )
        await async_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project_b),
                "actor": "admin",
                "feature": "feature B",
                "benefit": "benefit",
                "raw_text": RAW_TEXT,
            },
        )

        # Filter by project_b
        response = await async_client.get(
            f"/api/v1/stories/?project_id={project_b}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["feature"] == "feature B"


class TestGetStory:
    """GET /api/v1/stories/{story_id}"""

    async def test_get_story(self, async_client):
        """POST then GET by id returns the story."""
        create_resp = await async_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(uuid4()),
                "actor": "user",
                "feature": "get story",
                "benefit": "test retrieval",
                "raw_text": RAW_TEXT,
            },
        )
        story_id = create_resp.json()["id"]

        response = await async_client.get(f"/api/v1/stories/{story_id}")
        assert response.status_code == 200
        assert response.json()["id"] == story_id
        assert response.json()["feature"] == "get story"

    async def test_get_story_not_found(self, async_client):
        """GET with a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await async_client.get(f"/api/v1/stories/{fake_id}")
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"


class TestUpdateStory:
    """PUT /api/v1/stories/{story_id}"""

    async def test_update_story(self, async_client):
        """POST then PUT updates the story fields."""
        create_resp = await async_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(uuid4()),
                "actor": "user",
                "feature": "old feature",
                "benefit": "old benefit",
                "raw_text": RAW_TEXT,
            },
        )
        story_id = create_resp.json()["id"]

        response = await async_client.put(
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

    async def test_delete_story(self, async_client):
        """POST then DELETE returns 204."""
        create_resp = await async_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(uuid4()),
                "actor": "user",
                "feature": "to delete",
                "benefit": "gone",
                "raw_text": RAW_TEXT,
            },
        )
        story_id = create_resp.json()["id"]

        response = await async_client.delete(f"/api/v1/stories/{story_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await async_client.get(f"/api/v1/stories/{story_id}")
        assert get_resp.status_code == 404

    async def test_delete_story_not_found(self, async_client):
        """DELETE on a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await async_client.delete(f"/api/v1/stories/{fake_id}")
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"
