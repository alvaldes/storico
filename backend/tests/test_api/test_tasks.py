"""Integration tests for the Task CRUD API endpoints.

Tests must seed the full ``workspace → project → story`` chain plus the caller's
membership because every route in this module resolves a task's workspace by
walking ``task → story → project`` and then requires membership in that
workspace — ``POST /`` included, which resolves the walk from its ``user_story_id``
body field before it persists anything.
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import User
from storico.infrastructure.database.repositories import (
    SQLAlchemyTaskRepository,
    SQLAlchemyUserRepository,
)


class TestCreateTask:
    """POST /api/v1/tasks/"""

    async def test_create_task(self, authed_client, seed_workspace):
        """POST with valid data returns 201 and a TaskResponse body.

        The story is seeded rather than a bare ``uuid4()`` so the created task is
        addressable by the read routes, and because POST walks the same
        ``story → project → workspace`` chain as the read routes and requires
        membership before it persists.
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

    async def test_create_task_is_forbidden_for_a_non_member(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """POST into a workspace the caller is not a member of returns 403.

        The foreign key on ``tasks.user_story_id`` is not an authorization
        control: the story id alone used to be enough to write a task into
        someone else's workspace. ``member=False`` keeps the story addressable
        while withholding exactly the membership the route must require, and the
        empty repository read afterwards proves nothing was persisted.
        """
        story = await seed_workspace(member=False)

        response = await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story.story_id),
                "title": "Injected task",
                "description": "Written into a workspace the caller cannot reach",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Not a member of this workspace"

        persisted = await SQLAlchemyTaskRepository(db_session).list_by_story(story.story_id)
        assert persisted == []

    async def test_create_task_is_forbidden_in_another_users_workspace(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """POST into another user's workspace returns 403, not 201.

        ``seed_workspace(user=other_user)`` builds a fully consistent chain —
        ``other_user`` really is its admin member — so the only thing between the
        authenticated caller and a 201 is the membership check on the caller's
        identity rather than on the story's existence.
        """
        other_user = await SQLAlchemyUserRepository(db_session).save(
            User(email="other@test.com", name="Other Test")
        )
        story = await seed_workspace(user=other_user)

        response = await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story.story_id),
                "title": "Cross-tenant task",
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "Not a member of this workspace"

        persisted = await SQLAlchemyTaskRepository(db_session).list_by_story(story.story_id)
        assert persisted == []

    async def test_create_task_rejects_an_unknown_story_id(self, authed_client):
        """POST with a story id that does not exist returns 404.

        An unknown story is reported as the caller's own head entity
        (``UserStory``), so the route never reveals which hop of the
        ``story → project → workspace`` walk failed.
        """
        response = await authed_client.post(
            "/api/v1/tasks/",
            json={"user_story_id": str(uuid4()), "title": "Orphan task"},
        )
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"

    async def test_create_task_still_succeeds_for_a_member(self, authed_client, seed_workspace):
        """POST into one's own workspace still returns 201 and reads back.

        The positive pin for the new authorization check: rejecting non-members
        must not disturb the member path or make the created task unreadable.
        """
        story = await seed_workspace()

        response = await authed_client.post(
            "/api/v1/tasks/",
            json={"user_story_id": str(story.story_id), "title": "Member task"},
        )
        assert response.status_code == 201
        assert response.json()["title"] == "Member task"

        listed = await authed_client.get(f"/api/v1/tasks/?user_story_id={story.story_id}")
        assert listed.status_code == 200
        assert listed.json()["total"] == 1
        assert listed.json()["items"][0]["title"] == "Member task"


class TestListTasks:
    """GET /api/v1/tasks/"""

    async def test_list_tasks(self, authed_client, seed_workspace):
        """POST one task against a seeded story, GET returns it in the items list.

        The "no filter" branch folds the caller's memberships into a single statement that
        joins tasks to their story and project, so the task only comes back when the whole
        chain exists. The fold itself is asserted in ``test_unfiltered_list_queries.py``.
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

    async def test_update_task_rejects_invalid_transition(self, authed_client, seed_workspace):
        """PUT with a forbidden Kanban move returns the canonical 400 payload.

        ``todo -> done`` skips ``in_progress`` and ``review``, so the state machine
        rejects it. The ``detail`` object is the client contract owned by this
        route: the decision now lives in ``TaskService.ensure_transition_allowed``,
        which raises ``InvalidStateTransition`` that the route translates here. This
        pins that translation key by key and in order, and pins the sorted
        ``allowed_transitions`` list, so the single decision site cannot drift the
        wire format without failing this test.
        """
        story_id = (await seed_workspace()).story_id
        create_resp = await authed_client.post(
            "/api/v1/tasks/",
            json={
                "user_story_id": str(story_id),
                "title": "Cannot skip review",
                "status": "todo",
            },
        )
        task_id = create_resp.json()["id"]

        response = await authed_client.put(
            f"/api/v1/tasks/{task_id}",
            json={"status": "done"},
        )

        assert response.status_code == 400

        detail = response.json()["detail"]
        assert list(detail.keys()) == [
            "detail",
            "error_code",
            "current_state",
            "attempted_state",
            "allowed_transitions",
        ]
        assert detail == {
            "detail": "Invalid state transition",
            "error_code": "INVALID_STATE_TRANSITION",
            "current_state": "todo",
            "attempted_state": "done",
            "allowed_transitions": ["backlog", "in_progress"],
        }

        # The rejected write must not have reached persistence.
        fetched = await authed_client.get(f"/api/v1/tasks/{task_id}")
        assert fetched.json()["status"] == "todo"

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
