"""Integration tests for the Task CRUD API endpoints.

Tests must seed the full ``workspace → project → story`` chain plus the caller's
membership because every route in this module resolves a task's workspace by
walking ``task → story → project`` and then requires membership in that workspace.
"""

from uuid import uuid4


class TestCreateTask:
    """POST /api/v1/tasks/"""

    async def test_create_task(self, authed_client, seed_workspace):
        """POST with valid data returns 201 and a TaskResponse body.

        The story is seeded rather than a bare ``uuid4()`` so the created task is
        addressable by the read routes.
        """
        story_id = (await seed_workspace()).story_id
        payload = {
            "user_story_id": str(story_id),
            "title": "Implement login",
            "description": "Build the login form",
            "status": "backlog",
            "priority": "high",
        }
        response = await authed_client.post("/api/v1/tasks/", json=payload)
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

    async def test_create_task_with_labels(self, authed_client, seed_workspace):
        """POST with labels and dependencies returns them in the response."""
        story_id = (await seed_workspace()).story_id
        payload = {
            "user_story_id": str(story_id),
            "title": "Build API endpoint",
            "description": "Create the REST endpoint",
            "labels": ["backend", "api"],
            "dependencies": ["US-001"],
        }
        response = await authed_client.post("/api/v1/tasks/", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["labels"] == ["backend", "api"]
        assert data["dependencies"] == ["US-001"]


class TestListTasks:
    """GET /api/v1/tasks/"""

    async def test_list_tasks(self, authed_client, seed_workspace):
        """POST one task against a seeded story, GET returns it in the items list.

        The "no filter" branch fans out over the caller's memberships and joins
        tasks to their story and project, so the task only comes back when the
        whole chain exists.
        """
        story_id = (await seed_workspace()).story_id
        await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_id),
                "title": "Task one",
            },
        )

        response = await authed_client.get("/api/v1/tasks/")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["title"] == "Task one"

    async def test_list_tasks_empty(self, authed_client, seed_workspace):
        """GET with no tasks returns empty list.

        A workspace with no stories and no tasks is seeded so the caller is a
        member of something: the empty result must come from "access but no
        rows", not from having no memberships at all, which is a different path
        through the same branch.
        """
        await seed_workspace(stories=0)

        response = await authed_client.get("/api/v1/tasks/")
        assert response.status_code == 200
        assert response.json()["items"] == []
        assert response.json()["total"] == 0

    async def test_list_tasks_by_story(self, authed_client, seed_workspace):
        """GET ?user_story_id= filters tasks by user story."""
        story_a, story_b = (await seed_workspace(stories=2)).story_ids

        await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_a),
                "title": "Story A task",
            },
        )
        await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_b),
                "title": "Story B task",
            },
        )

        response = await authed_client.get(f"/api/v1/tasks/?user_story_id={story_b}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Story B task"


class TestGetTask:
    """GET /api/v1/tasks/{task_id}"""

    async def test_get_task(self, authed_client, seed_workspace):
        """POST then GET by id returns the task."""
        story_id = (await seed_workspace()).story_id
        create_resp = await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_id),
                "title": "Target task",
            },
        )
        task_id = create_resp.json()["id"]

        response = await authed_client.get(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 200
        assert response.json()["id"] == task_id
        assert response.json()["title"] == "Target task"

    async def test_get_task_not_found(self, authed_client):
        """GET with a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await authed_client.get(f"/api/v1/tasks/{fake_id}")
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"


class TestUpdateTask:
    """PUT /api/v1/tasks/{task_id}"""

    async def test_update_task(self, authed_client, seed_workspace):
        """POST then PUT updates the task fields.

        The task starts in ``todo`` because the Kanban state machine only allows
        ``todo → in_progress``: a task created in ``backlog`` cannot legally reach
        ``in_progress`` in one step, and that rejection is a separate contract from
        the field updates this test is about.
        """
        story_id = (await seed_workspace()).story_id
        create_resp = await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_id),
                "title": "Before",
                "description": "Old desc",
                "status": "todo",
                "priority": "low",
            },
        )
        task_id = create_resp.json()["id"]

        response = await authed_client.put(
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

    async def test_update_task_labels(self, authed_client, seed_workspace):
        """POST with labels, PUT with different labels, verify updated."""
        story_id = (await seed_workspace()).story_id
        create_resp = await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_id),
                "title": "Labeled task",
                "labels": ["backend", "database"],
            },
        )
        task_id = create_resp.json()["id"]

        # Update labels
        response = await authed_client.put(
            f"/api/v1/tasks/{task_id}",
            json={"labels": ["frontend", "ui"]},
        )
        assert response.status_code == 200
        assert response.json()["labels"] == ["frontend", "ui"]


class TestDeleteTask:
    """DELETE /api/v1/tasks/{task_id}"""

    async def test_delete_task(self, authed_client, seed_workspace):
        """POST then DELETE returns 204."""
        story_id = (await seed_workspace()).story_id
        create_resp = await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_id),
                "title": "To delete",
            },
        )
        task_id = create_resp.json()["id"]

        response = await authed_client.delete(f"/api/v1/tasks/{task_id}")
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await authed_client.get(f"/api/v1/tasks/{task_id}")
        assert get_resp.status_code == 404

    async def test_delete_task_not_found(self, authed_client):
        """DELETE on a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await authed_client.delete(f"/api/v1/tasks/{fake_id}")
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"
