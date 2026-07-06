"""Integration tests for the Task CRUD API endpoints."""

from uuid import uuid4


class TestCreateTask:
    """POST /api/v1/tasks/"""

    async def test_create_task(self, async_client):
        """POST with valid data returns 201 and a TaskResponse body."""
        story_id = uuid4()
        payload = {
            "user_story_id": str(story_id),
            "title": "Implement login",
            "description": "Build the login form",
            "status": "backlog",
            "priority": "high",
        }
        response = await async_client.post("/api/v1/tasks/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["title"] == "Implement login"
        assert data["description"] == "Build the login form"
        assert data["status"] == "backlog"
        assert data["priority"] == "high"
        assert data["user_story_id"] == str(story_id)
        assert data["labels"] == []
        assert data["dependencies"] == []
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_task_with_labels(self, async_client):
        """POST with labels and dependencies returns them in the response."""
        story_id = uuid4()
        payload = {
            "user_story_id": str(story_id),
            "title": "Build API endpoint",
            "description": "Create the REST endpoint",
            "labels": ["backend", "api"],
            "dependencies": ["US-001"],
        }
        response = await async_client.post("/api/v1/tasks/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["labels"] == ["backend", "api"]
        assert data["dependencies"] == ["US-001"]


class TestListTasks:
    """GET /api/v1/tasks/"""

    async def test_list_tasks(self, async_client):
        """POST one task, GET returns it in the items list."""
        await async_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(uuid4()),
                "title": "Task one",
            },
        )

        response = await async_client.get("/api/v1/tasks/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Task one"

    async def test_list_tasks_empty(self, async_client):
        """GET with no tasks returns empty list."""
        response = await async_client.get("/api/v1/tasks/")
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0

    async def test_list_tasks_by_story(self, async_client):
        """GET ?user_story_id= filters tasks by user story."""
        story_a = uuid4()
        story_b = uuid4()

        await async_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_a),
                "title": "Story A task",
            },
        )
        await async_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_b),
                "title": "Story B task",
            },
        )

        response = await async_client.get(
            f"/api/v1/tasks/?user_story_id={story_b}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Story B task"


class TestGetTask:
    """GET /api/v1/tasks/{task_id}"""

    async def test_get_task(self, async_client):
        """POST then GET by id returns the task."""
        create_resp = await async_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(uuid4()),
                "title": "Target task",
            },
        )
        task_id = create_resp.json()["id"]

        response = await async_client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["id"] == task_id
        assert response.json()["title"] == "Target task"

    async def test_get_task_not_found(self, async_client):
        """GET with a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await async_client.get(f"/api/v1/tasks/{fake_id}")
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"


class TestUpdateTask:
    """PUT /api/v1/tasks/{task_id}"""

    async def test_update_task(self, async_client):
        """POST then PUT updates the task fields."""
        create_resp = await async_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(uuid4()),
                "title": "Before",
                "description": "Old desc",
                "status": "backlog",
                "priority": "low",
            },
        )
        task_id = create_resp.json()["id"]

        response = await async_client.put(
            f"/api/v1/tasks/{task_id}",
            json={
                "title": "After",
                "description": "New desc",
                "status": "in_progress",
                "priority": "high",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["title"] == "After"
        assert data["description"] == "New desc"
        assert data["status"] == "in_progress"
        assert data["priority"] == "high"
        assert data["id"] == task_id

    async def test_update_task_labels(self, async_client):
        """POST with labels, PUT with different labels, verify updated."""
        create_resp = await async_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(uuid4()),
                "title": "Labeled task",
                "labels": ["backend", "database"],
            },
        )
        task_id = create_resp.json()["id"]

        # Update labels
        response = await async_client.put(
            f"/api/v1/tasks/{task_id}",
            json={"labels": ["frontend", "ui"]},
        )
        assert response.status_code == 200
        assert response.json()["labels"] == ["frontend", "ui"]


class TestDeleteTask:
    """DELETE /api/v1/tasks/{task_id}"""

    async def test_delete_task(self, async_client):
        """POST then DELETE returns 204."""
        create_resp = await async_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(uuid4()),
                "title": "To delete",
            },
        )
        task_id = create_resp.json()["id"]

        response = await async_client.delete(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await async_client.get(f"/api/v1/tasks/{task_id}")
        assert get_resp.status_code == 404

    async def test_delete_task_not_found(self, async_client):
        """DELETE on a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await async_client.delete(f"/api/v1/tasks/{fake_id}")
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"
