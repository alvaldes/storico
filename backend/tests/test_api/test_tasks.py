"""Integration tests for the Task CRUD API endpoints.

Tests must seed the full ``workspace → project → story`` chain plus the caller's
membership because every route in this module resolves a task's workspace by
walking ``task → story → project`` and then requires membership in that
workspace — ``POST /`` included, which resolves the walk from its ``user_story_id``
body field before it persists anything.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import User, UserStory
from storico.domain.entities.task import TaskStatus
from storico.infrastructure.database.repositories import (
    SQLAlchemyTaskRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import seed_task


class TestCreateTask:
    """POST /api/v1/tasks/ — retired with 410 Gone.

    Revision ``0028`` made ``tasks.extraction_id`` ``NOT NULL`` — every task must
    belong to the run that extracted it — so a manually created task can never be
    persisted. The route is retired: it answers 410 with a ``detail`` naming the
    rule (design decision D3) and writes nothing, for members and non-members
    alike. The handler reads no body and runs no authorization walk, because the
    story id it used to authorize against lived in the deleted request body.
    """

    async def test_create_task(self, authed_client, db_session: AsyncSession, seed_workspace):
        """POST /api/v1/tasks/ answers 410 and adds no row.

        The retirement replaces slice (a)'s pinned 500: the refusal is now a
        designed contract, not a schema accident.
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
        assert response.status_code == 410
        assert response.json()["error_code"] == "TASK_CREATION_ENDPOINT_REMOVED"
        assert "D3" in response.json()["detail"]

        persisted = await SQLAlchemyTaskRepository(db_session).list_by_story(story_id)
        assert persisted == []

    async def test_create_task_with_labels(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """POST /api/v1/tasks/ answers 410 with labels in the body too, and adds no row."""
        story_id = (await seed_workspace()).story_id
        payload = {
            "user_story_id": str(story_id),
            "title": "Build API endpoint",
            "description": "Create the REST endpoint",
            "labels": ["backend", "api"],
            "dependencies": ["US-001"],
        }
        response = await authed_client.post("/api/v1/tasks/", json=payload)
        assert response.status_code == 410
        assert response.json()["error_code"] == "TASK_CREATION_ENDPOINT_REMOVED"
        assert "D3" in response.json()["detail"]

        persisted = await SQLAlchemyTaskRepository(db_session).list_by_story(story_id)
        assert persisted == []

    async def test_create_task_answers_the_retirement_to_a_non_member_too(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A non-member's POST gets the same 410, and nothing persists.

        The retired door authorizes nothing: the story id it used to walk lived
        in the deleted request body, so the refusal is the retirement itself and
        it discloses nothing about any workspace.
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
        assert response.status_code == 410
        assert response.json()["error_code"] == "TASK_CREATION_ENDPOINT_REMOVED"

        persisted = await SQLAlchemyTaskRepository(db_session).list_by_story(story.story_id)
        assert persisted == []

    async def test_create_task_answers_the_retirement_in_another_users_workspace_too(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A POST addressed into another user's workspace gets the same 410.

        The chain is seeded consistently (``other_user`` really is its admin
        member), so the only thing between the authenticated caller and the old
        201 was the membership check — retired together with the route.
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
        assert response.status_code == 410
        assert response.json()["error_code"] == "TASK_CREATION_ENDPOINT_REMOVED"

        persisted = await SQLAlchemyTaskRepository(db_session).list_by_story(story.story_id)
        assert persisted == []

    async def test_create_task_answers_the_retirement_for_an_unknown_story_id_too(
        self, authed_client
    ):
        """POST with a story id that does not exist answers the same 410.

        The handler runs no walk, so it cannot report the miss of the walk's head
        entity: the retirement is the whole answer, and it reveals nothing about
        which story ids exist.
        """
        response = await authed_client.post(
            "/api/v1/tasks/",
            json={"user_story_id": str(uuid4()), "title": "Orphan task"},
        )
        assert response.status_code == 410
        assert response.json()["error_code"] == "TASK_CREATION_ENDPOINT_REMOVED"

    async def test_a_member_post_answers_the_retirement_too_and_persists_nothing(
        self, authed_client, seed_workspace
    ):
        """A member's POST gets the 410, not a 403 — and nothing persists.

        The positive pin for the retirement: a caller with full membership still
        meets the same door, because no identity may create a task by hand.
        """
        story = await seed_workspace()

        response = await authed_client.post(
            "/api/v1/tasks/",
            json={"user_story_id": str(story.story_id), "title": "Member task"},
        )
        assert response.status_code == 410
        assert response.json()["error_code"] == "TASK_CREATION_ENDPOINT_REMOVED"

        listed = await authed_client.get(f"/api/v1/tasks/?user_story_id={story.story_id}")
        assert listed.status_code == 200
        assert listed.json()["total"] == 0


class TestListTasks:
    """GET /api/v1/tasks/"""

    async def test_list_tasks(self, authed_client, db_session: AsyncSession, seed_workspace):
        """Seed one task against a seeded story, GET returns it in the items list.

        The "no filter" branch folds the caller's memberships into a single statement that
        joins tasks to their story and project, so the task only comes back when the whole
        chain exists. The fold itself is asserted in ``test_unfiltered_list_queries.py``.
        Seeded through the repository: the creation route cannot persist since ``0028``
        made ``tasks.extraction_id`` ``NOT NULL`` (the refusal is pinned in
        ``TestCreateTask``; slice (b) retires the route).
        """
        story_id = (await seed_workspace()).story_id
        await seed_task(db_session, story_id, "Task one")

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

    async def test_list_tasks_by_story(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """GET ?user_story_id= filters tasks by user story."""
        story_a, story_b = (await seed_workspace(stories=2)).story_ids

        await seed_task(db_session, story_a, "Story A task")
        await seed_task(db_session, story_b, "Story B task")

        response = await authed_client.get(f"/api/v1/tasks/?user_story_id={story_b}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["title"] == "Story B task"


class TestListTasksPagination:
    """GET /api/v1/tasks/ with paging params — every authorization branch.

    Each branch must report ``total`` as the full count of matching tasks,
    not the page size, and a page past the end must return 0 items with the
    real total. Tasks are saved through the repository with explicit
    ``created_at`` values so assertions pin the SQL ordering rule rather than
    wall-clock insertion order.
    """

    async def _seed_tasks(self, db_session: AsyncSession, seed_workspace, count: int):
        """Seed an accessible workspace with ``count`` tasks on one story, one day apart.

        Returns ``(workspace_id, story_id, titles)`` where ``titles`` is the
        creation order (oldest first), so tests can name rows.
        """
        seeded = await seed_workspace(stories=0)
        story = await SQLAlchemyUserStoryRepository(db_session).save(
            UserStory(
                project_id=seeded.project_id,
                actor="user",
                feature="paged feature",
                benefit="value",
                raw_text="As a user, I want the paged feature so that value",
            )
        )
        titles = [f"task {day}" for day in range(1, count + 1)]
        for day, title in enumerate(titles, start=1):
            await seed_task(db_session, story.id, title, created_at=datetime(2026, 1, day))
        return seeded.workspace_id, story.id, titles

    async def test_no_filter_returns_the_full_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?page=1&size=2 with no filter returns 2 of 3 tasks and total 3."""
        first = await seed_workspace(stories=0)
        second = await seed_workspace(stories=0)
        story_repo = SQLAlchemyUserStoryRepository(db_session)
        story_a = await story_repo.save(
            UserStory(
                project_id=first.project_id,
                actor="user",
                feature="first feature",
                benefit="value",
                raw_text="As a user, I want the first feature so that value",
            )
        )
        story_b = await story_repo.save(
            UserStory(
                project_id=second.project_id,
                actor="user",
                feature="second feature",
                benefit="value",
                raw_text="As a user, I want the second feature so that value",
            )
        )
        await seed_task(db_session, story_a.id, "task 1")
        await seed_task(db_session, story_a.id, "task 2")
        await seed_task(db_session, story_b.id, "task 3")

        response = await authed_client.get("/api/v1/tasks/?page=1&size=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["size"] == 2

    async def test_no_filter_past_the_end_returns_no_items_and_the_real_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?page=9&size=2 with no filter returns 0 items but total 3.

        The fallback path: an empty page carries the real total so clients can
        still render '3 tasks' while showing no rows.
        """
        first = await seed_workspace(stories=0)
        second = await seed_workspace(stories=0)
        story_repo = SQLAlchemyUserStoryRepository(db_session)
        story_a = await story_repo.save(
            UserStory(
                project_id=first.project_id,
                actor="user",
                feature="first feature",
                benefit="value",
                raw_text="As a user, I want the first feature so that value",
            )
        )
        story_b = await story_repo.save(
            UserStory(
                project_id=second.project_id,
                actor="user",
                feature="second feature",
                benefit="value",
                raw_text="As a user, I want the second feature so that value",
            )
        )
        await seed_task(db_session, story_a.id, "task 1")
        await seed_task(db_session, story_a.id, "task 2")
        await seed_task(db_session, story_b.id, "task 3")

        response = await authed_client.get("/api/v1/tasks/?page=9&size=2")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3

    async def test_workspace_filter_returns_the_full_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?workspace_id=&page=1&size=2 returns 2 of 3 tasks and total 3."""
        ws_id, _story_id, _titles = await self._seed_tasks(db_session, seed_workspace, 3)

        response = await authed_client.get(f"/api/v1/tasks/?workspace_id={ws_id}&page=1&size=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

    async def test_workspace_filter_past_the_end_returns_no_items_and_the_real_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?workspace_id=&page=9&size=2 returns 0 items but total 3."""
        ws_id, _story_id, _titles = await self._seed_tasks(db_session, seed_workspace, 3)

        response = await authed_client.get(f"/api/v1/tasks/?workspace_id={ws_id}&page=9&size=2")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3

    async def test_workspace_filter_orders_by_created_at_desc(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?workspace_id= orders the page by created_at DESC, the shared SQL rule.

        The old route fetched every matching row and sliced in Python with no
        order at all on this branch, so the page came back in insertion order —
        the RED this test observes.
        """
        ws_id, _story_id, titles = await self._seed_tasks(db_session, seed_workspace, 3)

        response = await authed_client.get(f"/api/v1/tasks/?workspace_id={ws_id}")

        assert response.status_code == 200
        returned = [item["title"] for item in response.json()["items"]]
        assert returned == list(reversed(titles))

    async def test_story_filter_returns_the_full_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?user_story_id=&page=1&size=2 returns 2 of 3 tasks and total 3."""
        _ws_id, story_id, _titles = await self._seed_tasks(db_session, seed_workspace, 3)

        response = await authed_client.get(f"/api/v1/tasks/?user_story_id={story_id}&page=1&size=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

    async def test_story_filter_past_the_end_returns_no_items_and_the_real_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?user_story_id=&page=9&size=2 returns 0 items but total 3."""
        _ws_id, story_id, _titles = await self._seed_tasks(db_session, seed_workspace, 3)

        response = await authed_client.get(f"/api/v1/tasks/?user_story_id={story_id}&page=9&size=2")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3


class TestGetTask:
    """GET /api/v1/tasks/{task_id}"""

    async def test_get_task(self, authed_client, db_session: AsyncSession, seed_workspace):
        """Seed a task then GET by id returns it."""
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "Target task")

        response = await authed_client.get(f"/api/v1/tasks/{task.id}")
        assert response.status_code == 200
        assert response.json()["id"] == str(task.id)
        assert response.json()["title"] == "Target task"

    async def test_get_task_not_found(self, authed_client):
        """GET with a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await authed_client.get(f"/api/v1/tasks/{fake_id}")
        assert response.status_code == 404
        assert response.json()["error_code"] == "ENTITY_NOT_FOUND"


class TestUpdateTask:
    """PUT /api/v1/tasks/{task_id}"""

    async def test_update_task(self, authed_client, db_session: AsyncSession, seed_workspace):
        """Seed a task then PUT updates the task fields.

        The task starts in ``todo`` because the Kanban state machine only allows
        ``todo → in_progress``: a task created in ``backlog`` cannot legally reach
        ``in_progress`` in one step, and that rejection is a separate contract from
        the field updates this test is about. Seeded through the repository: the
        creation route cannot persist since ``0028`` made ``tasks.extraction_id``
        ``NOT NULL``.
        """
        story_id = (await seed_workspace()).story_id
        task = await seed_task(
            db_session,
            story_id,
            "Before",
            description="Old desc",
            status=TaskStatus.TODO,
            priority="low",
        )

        response = await authed_client.put(
            f"/api/v1/tasks/{task.id}",
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
        assert data["id"] == str(task.id)

    async def test_update_task_rejects_invalid_transition(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
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
        task = await seed_task(db_session, story_id, "Cannot skip review", status=TaskStatus.TODO)

        response = await authed_client.put(
            f"/api/v1/tasks/{task.id}",
            json={"status": "done"},
        )

        assert response.status_code == 400

        detail = response.json()["detail"]
        assert response.json()["error_code"] == "INVALID_STATE_TRANSITION"
        assert list(detail.keys()) == [
            "detail",
            "current_state",
            "attempted_state",
            "allowed_transitions",
        ]
        assert detail == {
            "detail": "Invalid state transition",
            "current_state": "todo",
            "attempted_state": "done",
            "allowed_transitions": ["backlog", "in_progress"],
        }

        # The rejected write must not have reached persistence.
        fetched = await authed_client.get(f"/api/v1/tasks/{task.id}")
        assert fetched.json()["status"] == "todo"

    async def test_update_task_labels(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """Seed a task with labels, PUT with different labels, verify updated."""
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "Labeled task", labels=["backend", "database"])

        # Update labels
        response = await authed_client.put(
            f"/api/v1/tasks/{task.id}",
            json={"labels": ["frontend", "ui"]},
        )
        assert response.status_code == 200
        assert response.json()["labels"] == ["frontend", "ui"]


class TestDeleteTask:
    """DELETE /api/v1/tasks/{task_id} — retired with 410 Gone.

    The handler keeps the membership walk it has today, so a missing task still
    answers 404 and a non-member still answers 403 before the retirement is ever
    reached; a member learns the door is retired and the row survives.
    """

    async def test_delete_task(self, authed_client, db_session: AsyncSession, seed_workspace):
        """DELETE returns 410 and leaves the task row linked to its version.

        The retirement replaces the old 204: no product path deletes a single
        task (design decision D12), so the row must still exist — and still
        belong to the extraction run that produced it — after the call.
        """
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "To keep")

        response = await authed_client.delete(f"/api/v1/tasks/{task.id}")
        assert response.status_code == 410
        assert response.json()["error_code"] == "TASK_DELETE_ENDPOINT_REMOVED"
        assert "D12" in response.json()["detail"]

        # Verify the row is intact and still linked to its version.
        get_resp = await authed_client.get(f"/api/v1/tasks/{task.id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["id"] == str(task.id)
        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(task.id)
        assert persisted is not None
        assert persisted.extraction_id == task.extraction_id

    async def test_delete_task_not_found(self, authed_client):
        """DELETE on a non-existent UUID returns 404 — the walk fires before the 410."""
        fake_id = str(uuid4())
        response = await authed_client.delete(f"/api/v1/tasks/{fake_id}")
        assert response.status_code == 404
        assert response.json()["error_code"] == "ENTITY_NOT_FOUND"

    async def test_delete_task_refuses_a_non_member_before_the_retirement(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A non-member's DELETE answers 403 before the 410, and the row survives.

        The retirement must not teach a caller anything about a workspace they
        are not in: the answer is the same ``NOT_A_WORKSPACE_MEMBER`` refusal the
        walk gives today, the body names no workspace, and the task — its row
        and its link to its version — is untouched by the refused call.
        """
        seeded = await seed_workspace(member=False)
        task = await seed_task(db_session, seeded.story_id, "Untouchable")

        response = await authed_client.delete(f"/api/v1/tasks/{task.id}")
        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
        assert response.json()["detail"] == "Not a member of this workspace"
        assert str(seeded.workspace_id) not in response.text

        # The refused call changed nothing: the row is intact and still linked.
        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(task.id)
        assert persisted is not None
        assert persisted.extraction_id == task.extraction_id

    async def test_delete_on_the_collection_root_still_answers_405(self, authed_client):
        """DELETE /api/v1/tasks/ answers 405, not 410.

        The retirement is two exact published methods, not a catch-all: the
        collection root never had a DELETE handler and must keep saying so.
        """
        response = await authed_client.delete("/api/v1/tasks/")
        assert response.status_code == 405
        assert response.status_code != 410

    async def test_the_invalidations_revoke_path_is_not_swallowed_by_the_retirement(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """DELETE /api/v1/tasks/{task_id}/invalidations/current is not a 410.

        Neither retirement may become a ``/{path:path}`` catch-all: the marks
        work (slice (b) WU5) registers its revoke route on this exact path, and a
        greedy retirement would swallow it behind an ordering coupling. Today the
        route does not exist yet, so the answer is the router's plain 404 — the
        pin is that the answer is not the retirement.
        """
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "Marked later")

        response = await authed_client.delete(f"/api/v1/tasks/{task.id}/invalidations/current")
        assert response.status_code != 410
        assert b"TASK_DELETE_ENDPOINT_REMOVED" not in response.content
