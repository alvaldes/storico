"""Integration tests for the Task CRUD API endpoints.

Tests must seed the full ``workspace → project → story`` chain plus the caller's
membership because every route in this module resolves a task's workspace by
walking ``task → story → project`` and then requires membership in that
workspace — ``POST /`` included, which resolves the walk from its ``user_story_id``
body field before it persists anything.
"""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID, uuid4

import pytest
from fastapi import Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from storico.api.dependencies import get_vector_store
from storico.api.routes import tasks as task_routes
from storico.domain.entities import User, UserStory
from storico.domain.entities.exceptions import VectorStoreError
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.task import TaskStatus
from storico.domain.entities.task_invalidation import TaskInvalidation
from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
from storico.domain.ports.vector_store_port import VectorStorePort
from storico.infrastructure.database.models import TaskInvalidationModel
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyTaskInvalidationRepository,
    SQLAlchemyTaskRepository,
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
)
from storico.infrastructure.database.repositories.workspace_member_repository import (
    SQLAlchemyWorkspaceMemberRepository,
)
from storico.infrastructure.database.session import get_session
from storico.infrastructure.vector.qdrant_adapter import QdrantAdapter
from tests._helpers import seed_extraction, seed_task
from tests.conftest import make_jwt_headers


def _auth_headers(user_id: str) -> dict:
    """JWT auth headers for a second user — mirrors conftest.make_jwt_headers."""
    return make_jwt_headers(user_id)


async def _create_user(db_session: AsyncSession, email: str) -> User:
    """Persist a user to authenticate a second caller against."""
    return await SQLAlchemyUserRepository(db_session).save(User(email=email, name="Second User"))


async def _mark_rows(db_session: AsyncSession, task_id: UUID) -> list[TaskInvalidationModel]:
    """Direct read of the task's ``task_invalidations`` rows — the no-write witness.

    Refusals are witnessed by reading the table, not by trusting the status
    code: a 4xx that had already written a row would pass a status-only pin.
    """
    result = await db_session.execute(
        select(TaskInvalidationModel).where(TaskInvalidationModel.task_id == task_id)
    )
    return list(result.scalars().all())


async def _seed_mark(
    db_session: AsyncSession,
    task_id: UUID,
    marked_by: UUID,
    *,
    reason: str = "Duplicates the login task from v1",
) -> TaskInvalidation:
    """Persist an active mark through the repository, as production writes one."""
    return await SQLAlchemyTaskInvalidationRepository(db_session).create(
        TaskInvalidation(task_id=task_id, reason=reason, marked_by=marked_by)
    )


async def _seed_two_completed_versions(
    db_session: AsyncSession, story_id: UUID
) -> tuple[object, object]:
    """Two completed runs: the first is frozen the moment the second completes."""
    completed = {"status": ExtractionStatus.COMPLETED, "completed_at": datetime.now(UTC)}
    v1 = await seed_extraction(db_session, story_id, **completed)
    v2 = await seed_extraction(db_session, story_id, **completed)
    return v1, v2


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
        # One completed version carries all the tasks: reads answer the story's
        # current version only (D-a-5 item 2), and one completed version per task
        # would leave only the highest-numbered one visible.
        version = await seed_extraction(
            db_session, story.id, status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC)
        )
        for day, title in enumerate(titles, start=1):
            await seed_task(
                db_session, story.id, title, extraction=version, created_at=datetime(2026, 1, day)
            )
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
        # One completed version per story: reads answer the story's current
        # version only (D-a-5 item 2), and one version per task would leave
        # only the highest-numbered one visible.
        version_a = await seed_extraction(
            db_session,
            story_a.id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        version_b = await seed_extraction(
            db_session,
            story_b.id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_task(db_session, story_a.id, "task 1", extraction=version_a)
        await seed_task(db_session, story_a.id, "task 2", extraction=version_a)
        await seed_task(db_session, story_b.id, "task 3", extraction=version_b)

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
        # One completed version per story: reads answer the story's current
        # version only (D-a-5 item 2), and one version per task would leave
        # only the highest-numbered one visible.
        version_a = await seed_extraction(
            db_session,
            story_a.id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        version_b = await seed_extraction(
            db_session,
            story_b.id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_task(db_session, story_a.id, "task 1", extraction=version_a)
        await seed_task(db_session, story_a.id, "task 2", extraction=version_a)
        await seed_task(db_session, story_b.id, "task 3", extraction=version_b)

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


class TestListTasksVersionReads:
    """GET /api/v1/tasks/?user_story_id=S[&extraction_id=X] — the version read.

    The default story read answers the story's current (highest-numbered
    ``completed``) version only; an explicit ``extraction_id`` reads exactly
    that version, so a superseded version's tasks stay addressable. A version
    that does not belong to the requested story — or does not exist — is
    refused with 422 ``REQUEST_VALIDATION_FAILED``, not 404. And
    ``extraction_id`` without ``user_story_id`` is refused with 422 by the
    route itself, before the repository is ever reached: the repository's
    ``ValueError`` for that same shape is an internal invariant, not an HTTP
    contract, and letting it escape would surface as a 500.
    """

    async def test_a_foreign_extraction_id_refuses_and_leaks_nothing(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?user_story_id=A&extraction_id=<version of story B> is 422, never story B's tasks."""
        seeded = await seed_workspace(stories=2)
        story_a, story_b = seeded.story_ids
        await seed_task(db_session, story_a, "Story A task")
        foreign_version = await seed_extraction(
            db_session, story_b, status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC)
        )
        await seed_task(db_session, story_b, "Story B task", extraction=foreign_version)

        response = await authed_client.get(
            f"/api/v1/tasks/?user_story_id={story_a}&extraction_id={foreign_version.id}"
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"
        # The refusal discloses nothing about story B: not its id, not its tasks.
        assert str(story_b) not in response.text
        assert "Story B task" not in response.text

    async def test_an_unknown_extraction_id_refuses_with_422(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?user_story_id=S&extraction_id=<no such version> is 422, not 404 or 500."""
        story_id = (await seed_workspace()).story_id
        await seed_task(db_session, story_id, "Story A task")

        response = await authed_client.get(
            f"/api/v1/tasks/?user_story_id={story_id}&extraction_id={uuid4()}"
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"

    async def test_extraction_id_without_user_story_id_refuses_before_the_repository(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """The 422 is the route's own answer, raised before any repository call.

        ``list_page`` raises ``ValueError`` when ``extraction_id`` arrives
        without ``user_story_id``. That is an internal invariant: if the route
        let the call through, the ``ValueError`` would fall to the generic
        error handler as a 500 — so a 422 carrying the registry code, on both
        the workspace and the unfiltered branch, is the proof the refusal
        happened before the repository was reached.
        """
        seeded = await seed_workspace()
        version = await seed_extraction(
            db_session,
            seeded.story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )

        workspace_response = await authed_client.get(
            f"/api/v1/tasks/?workspace_id={seeded.workspace_id}&extraction_id={version.id}"
        )
        assert workspace_response.status_code == 422
        assert workspace_response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"

        unfiltered_response = await authed_client.get(f"/api/v1/tasks/?extraction_id={version.id}")
        assert unfiltered_response.status_code == 422
        assert unfiltered_response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"

    async def test_a_story_whose_only_run_is_failed_reads_an_empty_page(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A story with no completed version has no current version: 200 with []."""
        story_id = (await seed_workspace()).story_id
        failed_version = await seed_extraction(db_session, story_id, status=ExtractionStatus.FAILED)
        await seed_task(db_session, story_id, "Orphaned task", extraction=failed_version)

        response = await authed_client.get(f"/api/v1/tasks/?user_story_id={story_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 0
        assert data["items"] == []

    async def test_an_explicit_superseded_extraction_id_reads_that_versions_tasks(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """History stays addressable: extraction_id=v1 reads v1's tasks, not v2's."""
        story_id = (await seed_workspace()).story_id
        v1 = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC)
        )
        await seed_task(db_session, story_id, "v1 task one", extraction=v1)
        await seed_task(db_session, story_id, "v1 task two", extraction=v1)
        v2 = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC)
        )
        await seed_task(db_session, story_id, "v2 task one", extraction=v2)
        await seed_task(db_session, story_id, "v2 task two", extraction=v2)

        current = await authed_client.get(f"/api/v1/tasks/?user_story_id={story_id}")
        assert current.status_code == 200
        assert current.json()["total"] == 2
        assert {item["title"] for item in current.json()["items"]} == {
            "v2 task one",
            "v2 task two",
        }

        historical = await authed_client.get(
            f"/api/v1/tasks/?user_story_id={story_id}&extraction_id={v1.id}"
        )
        assert historical.status_code == 200
        data = historical.json()
        assert data["total"] == 2
        assert {item["title"] for item in data["items"]} == {"v1 task one", "v1 task two"}


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
        """Seed a task then PUT updates the task fields the contract still accepts.

        The contract accepts only ``status``, ``labels`` and ``dependencies``
        (the D5/D21 field matrix): ``title``, ``description`` and ``priority``
        are deleted, not ignored, and their refusal is pinned by
        ``TestUpdateTaskFieldMatrix``. The task starts in ``todo`` because the
        Kanban state machine only allows ``todo → in_progress``: a task created
        in ``backlog`` cannot legally reach ``in_progress`` in one step. Seeded
        through the repository: the creation route cannot persist since ``0028``
        made ``tasks.extraction_id`` ``NOT NULL``.
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
            json={"status": "in_progress"},
        )
        assert response.status_code == 200

        data = response.json()
        assert data["title"] == "Before"
        assert data["description"] == "Old desc"
        assert data["status"] == "in_progress"
        assert data["priority"] == "low"
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


class TestUpdateTaskFieldMatrix:
    """PUT /api/v1/tasks/{task_id} — the D5/D21 field matrix.

    ``status`` and ``labels`` stay editable in every version state;
    ``dependencies`` is only editable while the task's version is the story's
    current one — a dependencies write on a frozen version answers 409
    ``TASK_VERSION_FROZEN`` with the current version number in the detail.
    ``title``, ``description`` and ``priority`` are deleted from the request
    schema, so sending any of them is refused 422 ``REQUEST_VALIDATION_FAILED``
    by the ``extra="forbid"`` schema — the observable contract change, not a
    silent ignore. Presence, not value, is what counts as a dependencies
    write: an explicit ``[]`` or ``null`` on a frozen version is refused
    exactly like any other write, while a body without the key keeps working.
    """

    async def _seed_versions(self, db_session: AsyncSession, seed_workspace):
        """Seed one story with completed versions v1 and v2, a task on each.

        Returns ``(frozen_task, current_task)``: the v1 task is frozen because
        the completed v2 is the story's current version, the v2 task is current.
        ``version_number`` is minted by the birth path, so the current version
        is number 2. Both tasks start in ``todo`` so legal transitions exist.
        """
        story_id = (await seed_workspace()).story_id
        v1 = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v1"
        )
        v2 = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v2"
        )
        frozen = await seed_task(
            db_session, story_id, "Frozen task", extraction=v1, status=TaskStatus.TODO
        )
        current = await seed_task(
            db_session, story_id, "Current task", extraction=v2, status=TaskStatus.TODO
        )
        return frozen, current

    async def test_status_stays_editable_on_a_frozen_version(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A ``status`` write on a frozen version answers 200 and is persisted.

        The Kanban board only ever sends ``{"status": …}``, so the board must
        keep moving cards of frozen versions too (design decision D5).
        """
        frozen, _current = await self._seed_versions(db_session, seed_workspace)

        response = await authed_client.put(
            f"/api/v1/tasks/{frozen.id}",
            json={"status": "in_progress"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"

        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(frozen.id)
        assert persisted.status is TaskStatus.IN_PROGRESS

    async def test_labels_stay_editable_on_a_frozen_version(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A ``labels`` write on a frozen version answers 200 and is persisted."""
        frozen, _current = await self._seed_versions(db_session, seed_workspace)

        response = await authed_client.put(
            f"/api/v1/tasks/{frozen.id}",
            json={"labels": ["frontend", "ui"]},
        )
        assert response.status_code == 200
        assert response.json()["labels"] == ["frontend", "ui"]

        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(frozen.id)
        assert persisted.labels == ["frontend", "ui"]

    async def test_dependencies_on_a_frozen_version_refuse_with_the_current_version_number(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A ``dependencies`` write on a frozen version answers 409, writes nothing.

        The ``detail`` names the story's current version number (2 — the number
        the birth path minted), and the task's dependencies are unchanged.
        """
        frozen, _current = await self._seed_versions(db_session, seed_workspace)

        response = await authed_client.put(
            f"/api/v1/tasks/{frozen.id}",
            json={"dependencies": ["T1"]},
        )
        assert response.status_code == 409
        assert response.json()["error_code"] == "TASK_VERSION_FROZEN"
        assert response.json()["detail"]["current_version"] == 2

        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(frozen.id)
        assert persisted.dependencies == frozen.dependencies

    async def test_dependencies_on_the_current_version_persist(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A ``dependencies`` write on the current version answers 200 and persists."""
        _frozen, current = await self._seed_versions(db_session, seed_workspace)

        response = await authed_client.put(
            f"/api/v1/tasks/{current.id}",
            json={"dependencies": ["T1", "T2"]},
        )
        assert response.status_code == 200
        assert response.json()["dependencies"] == ["T1", "T2"]

        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(current.id)
        assert persisted.dependencies == ["T1", "T2"]

    async def test_a_status_only_body_on_the_current_version_skips_the_frozen_lookup(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch
    ):
        """A ``{"status": …}``-only PUT never calls ``find_current_version``.

        The frozen refusal can only fire on a body that carries the
        ``dependencies`` key, so resolving the story's current version for a
        status-only write produces a verdict the handler never consults — one
        extra statement (~2s against the dev pooler) on the most common editor
        call, the write the Kanban board sends to keep a card alive. The call
        itself is the contract here: the response assertions stay in the same
        case so the lookup cannot be "saved" by breaking the write, and if the
        unconditional lookup creeps back this case fails on the counter even
        though the 200 would still be correct.
        """
        _frozen, current = await self._seed_versions(db_session, seed_workspace)

        calls: list[UUID] = []
        original = SQLAlchemyExtractionRepository.find_current_version

        async def counting_find_current_version(repo, user_story_id):
            calls.append(user_story_id)
            return await original(repo, user_story_id)

        monkeypatch.setattr(
            SQLAlchemyExtractionRepository,
            "find_current_version",
            counting_find_current_version,
        )

        response = await authed_client.put(
            f"/api/v1/tasks/{current.id}",
            json={"status": "in_progress"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "in_progress"

        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(current.id)
        assert persisted.status is TaskStatus.IN_PROGRESS

        assert calls == [], (
            "find_current_version ran for a status-only body: "
            f"{len(calls)} wasted lookup(s) for story {calls}"
        )

    async def test_a_dependencies_write_still_reaches_the_frozen_lookup(
        self, authed_client, db_session: AsyncSession, seed_workspace, monkeypatch
    ):
        """A body carrying ``dependencies`` on a frozen version still 409s.

        The mirror case: skipping the lookup for key-less bodies must not lose
        the refusal for bodies that have the key. The lookup runs exactly once,
        the frozen predicate fires on its verdict, and the 409 keeps the current
        version number in the detail. If the lookup were removed altogether,
        this case fails with a 200 and an empty counter — the pair of cases
        pins the lookup to exactly the payloads that can use it.
        """
        frozen, _current = await self._seed_versions(db_session, seed_workspace)

        calls: list[UUID] = []
        original = SQLAlchemyExtractionRepository.find_current_version

        async def counting_find_current_version(repo, user_story_id):
            calls.append(user_story_id)
            return await original(repo, user_story_id)

        monkeypatch.setattr(
            SQLAlchemyExtractionRepository,
            "find_current_version",
            counting_find_current_version,
        )

        response = await authed_client.put(
            f"/api/v1/tasks/{frozen.id}",
            json={"dependencies": ["T1"]},
        )
        assert response.status_code == 409
        assert response.json()["error_code"] == "TASK_VERSION_FROZEN"
        assert response.json()["detail"]["current_version"] == 2

        assert calls == [frozen.user_story_id]

        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(frozen.id)
        assert persisted.dependencies == frozen.dependencies

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("title", "After"),
            ("description", "New desc"),
            ("priority", "high"),
        ],
    )
    async def test_removed_fields_refuse_on_frozen_and_current(
        self,
        authed_client,
        db_session: AsyncSession,
        seed_workspace,
        field: str,
        value: str,
    ):
        """``title``, ``description`` and ``priority`` are 422 on every task.

        The fields are deleted from the contract, not ignored: the
        ``extra="forbid"`` schema refuses them during body validation, on both
        a frozen and a current task, and no field of either task changes.
        """
        frozen, current = await self._seed_versions(db_session, seed_workspace)

        for task in (frozen, current):
            response = await authed_client.put(
                f"/api/v1/tasks/{task.id}",
                json={field: value},
            )
            assert response.status_code == 422, (field, task.id)
            assert response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"

            persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(task.id)
            assert persisted.title == task.title
            assert persisted.description == task.description
            assert persisted.priority == task.priority
            assert persisted.status is task.status

    async def test_a_mixed_body_on_a_frozen_version_answers_409_not_400(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """An illegal transition plus a dependencies write on frozen → 409.

        The frozen-version refusal is checked before the state machine: the
        body's ``todo → done`` move is illegal, but the version-level reason is
        the one that will not be there tomorrow, so it wins (design decision
        D21). Neither path writes, so nothing partial can land.
        """
        frozen, _current = await self._seed_versions(db_session, seed_workspace)

        response = await authed_client.put(
            f"/api/v1/tasks/{frozen.id}",
            json={"status": "done", "dependencies": ["T1"]},
        )
        assert response.status_code == 409
        assert response.json()["error_code"] == "TASK_VERSION_FROZEN"

        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(frozen.id)
        assert persisted.status is TaskStatus.TODO

    async def test_an_explicit_empty_dependencies_array_is_still_a_write(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """``{"dependencies": []}`` on a frozen version is 409 and clears nothing.

        Presence, not value, is what counts as a write: an empty array carries
        the key, so it is refused, and the seeded dependencies survive.
        """
        story_id = (await seed_workspace()).story_id
        v1 = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v1"
        )
        v2 = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v2"
        )
        frozen = await seed_task(
            db_session,
            story_id,
            "Frozen task",
            extraction=v1,
            dependencies=["old-dep"],
        )
        # v2 exists only so v1 is superseded and the frozen predicate fires.
        await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v2 again"
        )
        assert v2.version_number == 2

        response = await authed_client.put(
            f"/api/v1/tasks/{frozen.id}",
            json={"dependencies": []},
        )
        assert response.status_code == 409
        assert response.json()["error_code"] == "TASK_VERSION_FROZEN"

        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(frozen.id)
        assert persisted.dependencies == ["old-dep"]

    async def test_explicit_null_dependencies_is_still_a_write(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """``{"dependencies": null}`` on a frozen version is 409.

        ``model_fields_set`` is populated by explicit presence even when the
        value is ``None``, so the null body is refused exactly like any other
        dependencies write on a frozen version.
        """
        frozen, _current = await self._seed_versions(db_session, seed_workspace)

        response = await authed_client.put(
            f"/api/v1/tasks/{frozen.id}",
            json={"dependencies": None},
        )
        assert response.status_code == 409
        assert response.json()["error_code"] == "TASK_VERSION_FROZEN"

    async def test_a_body_without_the_dependencies_key_keeps_working_on_a_frozen_version(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A ``status``-only body on a frozen version is 200 — no frozen refusal.

        A body that does not carry the ``dependencies`` key is not a
        dependencies write, whatever its other fields say.
        """
        story_id = (await seed_workspace()).story_id
        v1 = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v1"
        )
        await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v2"
        )
        frozen = await seed_task(
            db_session, story_id, "Frozen task", extraction=v1, status=TaskStatus.IN_PROGRESS
        )

        response = await authed_client.put(
            f"/api/v1/tasks/{frozen.id}",
            json={"status": "review"},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "review"

    async def test_a_story_with_no_completed_version_refuses_the_dependencies_write(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """No ``completed`` version means frozen, and the detail says so.

        ``current is None`` is the conservative reading of frozen (design
        decision D21): the 409's detail states there is no current version
        instead of inventing version number 0.
        """
        story_id = (await seed_workspace()).story_id
        pending = await seed_extraction(db_session, story_id)
        task = await seed_task(db_session, story_id, "Orphan task", extraction=pending)

        response = await authed_client.put(
            f"/api/v1/tasks/{task.id}",
            json={"dependencies": ["T1"]},
        )
        assert response.status_code == 409
        assert response.json()["error_code"] == "TASK_VERSION_FROZEN"
        assert "no current version" in response.json()["detail"]["detail"]
        assert response.json()["detail"]["current_version"] is None

    async def test_an_illegal_transition_on_a_frozen_version_writes_nothing(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A frozen version plus an illegal transition writes nothing.

        Without a dependencies key the frozen guard does not fire and the state
        machine still answers 400 — and the refused write must not have reached
        persistence.
        """
        frozen, _current = await self._seed_versions(db_session, seed_workspace)

        response = await authed_client.put(
            f"/api/v1/tasks/{frozen.id}",
            json={"status": "done"},
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "INVALID_STATE_TRANSITION"

        persisted = await SQLAlchemyTaskRepository(db_session).find_by_id(frozen.id)
        assert persisted.status is TaskStatus.TODO


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


class TestCreateInvalidation:
    """POST /api/v1/tasks/{task_id}/invalidations — the mark's door (WU5 / R8).

    The gate is ``require_task_owner_or_admin``: a ``MEMBER`` is refused with
    403 ``WORKSPACE_OWNER_OR_ADMIN_REQUIRED``, a non-member keeps the unchanged
    403 ``NOT_A_WORKSPACE_MEMBER``. Every refusal below is witnessed by a
    direct read of ``task_invalidations``, not by the status code alone.
    """

    async def test_a_valid_mark_round_trips_with_reason_actor_and_timestamp(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """201 with the mark record; exactly one row was persisted."""
        app.dependency_overrides[get_vector_store] = lambda: None
        story_id = (await seed_workspace()).story_id
        # A single completed run: its task sits on the story's current version.
        task = await seed_task(db_session, story_id, "Implement login")

        response = await authed_client.post(
            f"/api/v1/tasks/{task.id}/invalidations", json={"reason": "Duplicates the export task"}
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["reason"] == "Duplicates the export task"
        assert body["marked_by"] == str(authed_user.id)
        assert body["marked_at"]
        assert body["revoked_by"] is None
        assert body["revoked_at"] is None
        assert body["id"]
        rows = await _mark_rows(db_session, task.id)
        assert len(rows) == 1
        assert str(rows[0].id) == body["id"]

    @pytest.mark.parametrize("reason", ["", "   ", "\t\n"])
    async def test_a_blank_reason_is_refused_and_persists_nothing(
        self, authed_client, db_session: AsyncSession, seed_workspace, reason: str
    ):
        """All three blank shapes answer 422 REQUEST_VALIDATION_FAILED and write nothing.

        ``"\\t\\n"`` is the shape only the Pydantic validator can see: Python
        whitespace is wider than the column's ``length(trim(reason)) > 0``.
        """
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "Implement login")

        response = await authed_client.post(
            f"/api/v1/tasks/{task.id}/invalidations", json={"reason": reason}
        )

        assert response.status_code == 422
        assert response.json()["error_code"] == "REQUEST_VALIDATION_FAILED"
        assert await _mark_rows(db_session, task.id) == []

    async def test_a_second_active_mark_is_refused_with_the_live_reason_and_still_one_row(
        self, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """409 TASK_ALREADY_MARKED carries the active reason; no second row."""
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "Implement login")
        await _seed_mark(
            db_session, task.id, authed_user.id, reason="Duplicates the login task from v1"
        )

        response = await authed_client.post(
            f"/api/v1/tasks/{task.id}/invalidations", json={"reason": "A second, different reason"}
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "TASK_ALREADY_MARKED"
        assert "Duplicates the login task from v1" in str(response.json()["detail"])
        assert len(await _mark_rows(db_session, task.id)) == 1

    async def test_marking_a_frozen_version_is_refused_with_no_row(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A task of a superseded version cannot be marked: 409 TASK_VERSION_FROZEN, no row."""
        story_id = (await seed_workspace()).story_id
        v1, _ = await _seed_two_completed_versions(db_session, story_id)
        frozen_task = await seed_task(db_session, story_id, "Frozen task", extraction=v1)

        response = await authed_client.post(
            f"/api/v1/tasks/{frozen_task.id}/invalidations", json={"reason": "Too late"}
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "TASK_VERSION_FROZEN"
        assert await _mark_rows(db_session, frozen_task.id) == []

    async def test_a_member_is_refused_with_the_gate_code_and_no_row(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A MEMBER gets 403 WORKSPACE_OWNER_OR_ADMIN_REQUIRED; nothing persists."""
        owner = await _create_user(db_session, "mark-owner@test.com")
        member = await _create_user(db_session, "mark-member@test.com")
        seeded = await seed_workspace(user=owner)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id, user_id=member.id, role=WorkspaceRole.MEMBER
            )
        )
        task = await seed_task(db_session, seeded.story_id, "Implement login")

        response = await authed_client.post(
            f"/api/v1/tasks/{task.id}/invalidations",
            json={"reason": "Duplicates the export task"},
            headers=_auth_headers(str(member.id)),
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "WORKSPACE_OWNER_OR_ADMIN_REQUIRED"
        assert await _mark_rows(db_session, task.id) == []

    async def test_a_non_owner_admin_member_marks_and_revokes(
        self, app, db_session: AsyncSession, async_client, seed_workspace
    ):
        app.dependency_overrides[get_vector_store] = lambda: None
        """A member with role ADMIN who is not the owner passes both gates (task 4.2).

        The owner-success cases above carry ownership; this one carries only the
        ADMIN role, so both disjuncts of the gate rule are witnessed at the API.
        """
        owner = await _create_user(db_session, "admin-gate-owner@test.com")
        admin = await _create_user(db_session, "admin-gate-admin@test.com")
        seeded = await seed_workspace(user=owner)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id, user_id=admin.id, role=WorkspaceRole.ADMIN
            )
        )
        task = await seed_task(db_session, seeded.story_id, "Implement login")
        headers = _auth_headers(str(admin.id))

        marked = await async_client.post(
            f"/api/v1/tasks/{task.id}/invalidations",
            json={"reason": "Duplicates the export task"},
            headers=headers,
        )
        assert marked.status_code == 201, marked.text

        revoked = await async_client.delete(
            f"/api/v1/tasks/{task.id}/invalidations/current", headers=headers
        )
        assert revoked.status_code == 204

    async def test_a_non_member_keeps_the_not_a_workspace_member_code(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """The gate never speaks before the membership walk: a non-member keeps 403 NOT_A_WORKSPACE_MEMBER."""
        seeded = await seed_workspace(member=False)
        task = await seed_task(db_session, seeded.story_id, "Implement login")

        response = await authed_client.post(
            f"/api/v1/tasks/{task.id}/invalidations", json={"reason": "Duplicates the export task"}
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
        assert await _mark_rows(db_session, task.id) == []

    async def test_re_marking_after_a_revoke_writes_a_second_row_and_keeps_the_first_revoked(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """Both mark events stay readable: a new row, the first still revoked."""
        app.dependency_overrides[get_vector_store] = lambda: None
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "Implement login")
        first = await _seed_mark(db_session, task.id, authed_user.id)
        await authed_client.delete(f"/api/v1/tasks/{task.id}/invalidations/current")

        response = await authed_client.post(
            f"/api/v1/tasks/{task.id}/invalidations", json={"reason": "Still duplicated"}
        )

        assert response.status_code == 201, response.text
        rows = await _mark_rows(db_session, task.id)
        assert len(rows) == 2
        assert str(first.id) in {str(row.id) for row in rows}
        first_row = next(row for row in rows if row.id == first.id)
        assert first_row.revoked_at is not None
        assert first_row.revoked_by == authed_user.id


class TestListInvalidations:
    """GET /api/v1/tasks/{task_id}/invalidations — the mark history read (R9)."""

    async def test_the_history_lists_the_active_mark_first_with_every_field(
        self, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """Active mark first; every row carries all six fields; a MEMBER reads it too."""
        owner = await _create_user(db_session, "history-owner@test.com")
        member = await _create_user(db_session, "history-member@test.com")
        seeded = await seed_workspace(user=owner)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id, user_id=member.id, role=WorkspaceRole.MEMBER
            )
        )
        task = await seed_task(db_session, seeded.story_id, "Implement login")
        revoked_repo = SQLAlchemyTaskInvalidationRepository(db_session)
        older = await revoked_repo.create(
            TaskInvalidation(
                task_id=task.id,
                reason="older mark",
                marked_by=owner.id,
                marked_at=datetime.now(UTC) - timedelta(hours=1),
            )
        )
        await revoked_repo.revoke(older.id, revoked_by=owner.id, revoked_at=datetime.now(UTC))
        await _seed_mark(db_session, task.id, owner.id, reason="active mark")

        response = await authed_client.get(
            f"/api/v1/tasks/{task.id}/invalidations", headers=_auth_headers(str(member.id))
        )

        assert response.status_code == 200
        marks = response.json()
        assert len(marks) == 2
        assert marks[0]["revoked_at"] is None
        assert marks[0]["reason"] == "active mark"
        for mark in marks:
            assert set(mark) == {
                "id",
                "reason",
                "marked_by",
                "marked_at",
                "revoked_by",
                "revoked_at",
            }
        revoked_row = next(mark for mark in marks if mark["revoked_at"] is not None)
        assert revoked_row["id"] == str(older.id)
        assert revoked_row["revoked_by"] == str(owner.id)

    async def test_an_unmarked_task_reads_as_empty(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A task that has never been marked answers 200 []."""
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "Implement login")

        response = await authed_client.get(f"/api/v1/tasks/{task.id}/invalidations")

        assert response.status_code == 200
        assert response.json() == []


class TestRevokeInvalidation:
    """DELETE /api/v1/tasks/{task_id}/invalidations/current — revoke is an UPDATE (R10)."""

    async def test_revoking_records_who_and_when_and_keeps_the_row(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """204; the same row now records the revoker, and its original fields stay."""
        app.dependency_overrides[get_vector_store] = lambda: None
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "Implement login")
        marked_at = datetime.now(UTC) - timedelta(hours=2)
        mark = await SQLAlchemyTaskInvalidationRepository(db_session).create(
            TaskInvalidation(
                task_id=task.id,
                reason="Duplicates the export task",
                marked_by=authed_user.id,
                marked_at=marked_at,
            )
        )

        response = await authed_client.delete(f"/api/v1/tasks/{task.id}/invalidations/current")

        assert response.status_code == 204
        rows = await _mark_rows(db_session, task.id)
        assert len(rows) == 1
        row = rows[0]
        assert row.id == mark.id
        assert row.revoked_by == authed_user.id
        assert row.revoked_at is not None
        assert row.reason == "Duplicates the export task"
        assert row.marked_by == authed_user.id
        assert row.marked_at.replace(tzinfo=None) == marked_at.replace(tzinfo=None)

    async def test_revoking_on_a_frozen_version_is_refused_and_the_row_stays_active(
        self, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """409 TASK_VERSION_FROZEN; the mark row is unchanged and still active."""
        story_id = (await seed_workspace()).story_id
        v1, _ = await _seed_two_completed_versions(db_session, story_id)
        frozen_task = await seed_task(db_session, story_id, "Frozen task", extraction=v1)
        await _seed_mark(db_session, frozen_task.id, authed_user.id)

        response = await authed_client.delete(
            f"/api/v1/tasks/{frozen_task.id}/invalidations/current"
        )

        assert response.status_code == 409
        assert response.json()["error_code"] == "TASK_VERSION_FROZEN"
        rows = await _mark_rows(db_session, frozen_task.id)
        assert len(rows) == 1
        assert rows[0].revoked_at is None

    async def test_revoking_without_an_active_mark_is_404(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """No active mark: 404, and the task's row count stays at zero."""
        story_id = (await seed_workspace()).story_id
        task = await seed_task(db_session, story_id, "Implement login")

        response = await authed_client.delete(f"/api/v1/tasks/{task.id}/invalidations/current")

        assert response.status_code == 404
        assert await _mark_rows(db_session, task.id) == []

    async def test_a_member_revocation_is_refused_and_the_row_stays_active(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A MEMBER gets the gate code on revoke too; the active mark survives untouched."""
        owner = await _create_user(db_session, "revoke-owner@test.com")
        member = await _create_user(db_session, "revoke-member@test.com")
        seeded = await seed_workspace(user=owner)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id, user_id=member.id, role=WorkspaceRole.MEMBER
            )
        )
        task = await seed_task(db_session, seeded.story_id, "Implement login")
        await _seed_mark(db_session, task.id, owner.id)

        response = await authed_client.delete(
            f"/api/v1/tasks/{task.id}/invalidations/current", headers=_auth_headers(str(member.id))
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "WORKSPACE_OWNER_OR_ADMIN_REQUIRED"
        rows = await _mark_rows(db_session, task.id)
        assert len(rows) == 1
        assert rows[0].revoked_at is None


class TestRepetitionRead:
    """GET /api/v1/tasks/{task_id}/invalidations/repetition — the D16 read (R11).

    Exact normalized-title equality only — no fuzzy, no vector, no prefix. The
    title is resolved server-side from the task id; the read writes nothing.
    """

    async def test_a_matching_mark_from_another_version_is_offered(
        self, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """Casefold-plus-whitespace equality matches across versions."""
        story_id = (await seed_workspace()).story_id
        v1, v2 = await _seed_two_completed_versions(db_session, story_id)
        marked = await seed_task(db_session, story_id, "Implement  Login Retry", extraction=v1)
        edited = await seed_task(db_session, story_id, "Implement login retry", extraction=v2)
        await _seed_mark(
            db_session, marked.id, authed_user.id, reason="Already covered by the auth refactor"
        )

        response = await authed_client.get(f"/api/v1/tasks/{edited.id}/invalidations/repetition")

        assert response.status_code == 200
        matches = response.json()["matches"]
        assert len(matches) == 1
        assert matches[0]["version_number"] == 1
        assert matches[0]["reason"] == "Already covered by the auth refactor"
        assert matches[0]["marked_at"]

    async def test_no_normalized_match_reads_empty(
        self, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """Nothing similar on any other version answers {"matches": []}."""
        story_id = (await seed_workspace()).story_id
        v1, v2 = await _seed_two_completed_versions(db_session, story_id)
        marked = await seed_task(db_session, story_id, "Set up the database schema", extraction=v1)
        edited = await seed_task(db_session, story_id, "Implement login retry", extraction=v2)
        await _seed_mark(db_session, marked.id, authed_user.id)

        response = await authed_client.get(f"/api/v1/tasks/{edited.id}/invalidations/repetition")

        assert response.status_code == 200
        assert response.json() == {"matches": []}

    async def test_a_mark_on_the_tasks_own_version_is_not_offered(
        self, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """The same-version mark is excluded, even on an identical normalized title."""
        story_id = (await seed_workspace()).story_id
        v1, v2 = await _seed_two_completed_versions(db_session, story_id)
        _ = v1
        edited = await seed_task(db_session, story_id, "Implement login retry", extraction=v2)
        same_version = await seed_task(
            db_session, story_id, "Implement  Login  Retry", extraction=v2
        )
        await _seed_mark(db_session, same_version.id, authed_user.id)

        response = await authed_client.get(f"/api/v1/tasks/{edited.id}/invalidations/repetition")

        assert response.status_code == 200
        assert response.json() == {"matches": []}

    async def test_marks_from_other_stories_never_match(
        self, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """Another story's same-title mark is another story's business."""
        seeded = await seed_workspace(stories=2)
        other_story_id, story_id = seeded.story_ids
        v1, v2 = await _seed_two_completed_versions(db_session, story_id)
        edited = await seed_task(db_session, story_id, "Implement login retry", extraction=v2)
        foreign = await seed_task(db_session, other_story_id, "Implement  Login Retry")
        await _seed_mark(db_session, foreign.id, authed_user.id)
        _ = v1

        response = await authed_client.get(f"/api/v1/tasks/{edited.id}/invalidations/repetition")

        assert response.status_code == 200
        assert response.json() == {"matches": []}

    async def test_a_revoked_mark_is_not_offered(
        self, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """A revoked mark is history, not a live warning: the read answers empty."""
        story_id = (await seed_workspace()).story_id
        v1, v2 = await _seed_two_completed_versions(db_session, story_id)
        marked = await seed_task(db_session, story_id, "Implement  Login Retry", extraction=v1)
        edited = await seed_task(db_session, story_id, "Implement login retry", extraction=v2)
        mark = await _seed_mark(db_session, marked.id, authed_user.id)
        await SQLAlchemyTaskInvalidationRepository(db_session).revoke(
            mark.id, revoked_by=authed_user.id, revoked_at=datetime.now(UTC)
        )

        response = await authed_client.get(f"/api/v1/tasks/{edited.id}/invalidations/repetition")

        assert response.status_code == 200
        assert response.json() == {"matches": []}

    async def test_a_one_character_difference_yields_no_match_with_no_similarity_call(
        self,
        authed_client,
        authed_user: User,
        db_session: AsyncSession,
        seed_workspace,
        monkeypatch,
    ):
        """The match is exact equality; nothing similarity-shaped may run.

        Witness: ``QdrantAdapter.search_similar`` is monkeypatched to fail the
        test if it is ever invoked — the vector read must not be reachable from
        this endpoint (D16). A one-character title difference then answers no
        match, and the call never happened.
        """

        def _no_similarity(*args: object, **kwargs: object) -> None:
            pytest.fail("The repetition read computed a vector similarity (D16 forbids it)")

        monkeypatch.setattr(QdrantAdapter, "search_similar", _no_similarity)

        story_id = (await seed_workspace()).story_id
        v1, v2 = await _seed_two_completed_versions(db_session, story_id)
        marked = await seed_task(db_session, story_id, "Implement login retr", extraction=v1)
        edited = await seed_task(db_session, story_id, "Implement login retry", extraction=v2)
        await _seed_mark(db_session, marked.id, authed_user.id)

        response = await authed_client.get(f"/api/v1/tasks/{edited.id}/invalidations/repetition")

        assert response.status_code == 200
        assert response.json() == {"matches": []}

    async def test_the_repetition_read_writes_nothing(
        self, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ):
        """A matching read creates, updates and revokes nothing."""
        story_id = (await seed_workspace()).story_id
        v1, v2 = await _seed_two_completed_versions(db_session, story_id)
        marked = await seed_task(db_session, story_id, "Implement  Login Retry", extraction=v1)
        edited = await seed_task(db_session, story_id, "Implement login retry", extraction=v2)
        before = await _seed_mark(db_session, marked.id, authed_user.id)
        rows_before = await _mark_rows(db_session, marked.id)

        response = await authed_client.get(f"/api/v1/tasks/{edited.id}/invalidations/repetition")

        assert response.status_code == 200
        assert response.json()["matches"]
        rows_after = await _mark_rows(db_session, marked.id)
        assert [(row.id, row.revoked_at, row.revoked_by, row.reason) for row in rows_after] == [
            (row.id, row.revoked_at, row.revoked_by, row.reason) for row in rows_before
        ]
        assert rows_after[0].id == before.id

    async def test_a_member_calls_the_repetition_read(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """The read is membership-only: a MEMBER reads it, the gate is on the mutations."""
        owner = await _create_user(db_session, "repetition-owner@test.com")
        member = await _create_user(db_session, "repetition-member@test.com")
        seeded = await seed_workspace(user=owner)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id, user_id=member.id, role=WorkspaceRole.MEMBER
            )
        )
        task = await seed_task(db_session, seeded.story_id, "Implement login")

        response = await authed_client.get(
            f"/api/v1/tasks/{task.id}/invalidations/repetition",
            headers=_auth_headers(str(member.id)),
        )

        assert response.status_code == 200
        assert response.json() == {"matches": []}


class TestMemberSurface:
    """The version-mutating gate is the only gate (task 4.2, member-surfaces clause).

    A workspace ``MEMBER`` — neither the owner nor an ``ADMIN`` — keeps every
    non-gated task surface: reading the board, moving a card, editing ``labels``
    and calling the repetition read. Only extract, mark, unmark and story
    deletion demand the owner or an admin.
    """

    async def _seed_member_scene(
        self, db_session: AsyncSession, seed_workspace
    ) -> tuple[object, object, User]:
        owner = await _create_user(db_session, "surface-owner@test.com")
        member = await _create_user(db_session, "surface-member@test.com")
        seeded = await seed_workspace(user=owner)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id, user_id=member.id, role=WorkspaceRole.MEMBER
            )
        )
        task = await seed_task(db_session, seeded.story_id, "Implement login")
        return seeded, task, member

    async def test_a_member_still_reads_the_board(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        seeded, _, member = await self._seed_member_scene(db_session, seed_workspace)
        response = await authed_client.get(
            f"/api/v1/tasks/?workspace_id={seeded.workspace_id}",
            headers=_auth_headers(str(member.id)),
        )
        assert response.status_code == 200
        assert response.json()["total"] == 1

    async def test_a_member_still_moves_a_card(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        _, task, member = await self._seed_member_scene(db_session, seed_workspace)
        response = await authed_client.put(
            f"/api/v1/tasks/{task.id}",
            json={"status": "todo"},
            headers=_auth_headers(str(member.id)),
        )
        assert response.status_code == 200

    async def test_a_member_still_edits_labels(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        _, task, member = await self._seed_member_scene(db_session, seed_workspace)
        response = await authed_client.put(
            f"/api/v1/tasks/{task.id}",
            json={"labels": ["backend"]},
            headers=_auth_headers(str(member.id)),
        )
        assert response.status_code == 200
        assert response.json()["labels"] == ["backend"]


class _RefreshingVectorStore(VectorStorePort):
    """A configured store that records every refresh it is asked for.

    ``calls`` is the list the test passes in, shared with the invalidation
    repository's recording override (``_override_invalidation_repo``): one list
    carries the order of the calls across the two boundaries — the vector
    refresh and the relational write — so the handlers' ordering is witnessed,
    not merely each call's presence. A fake that only counted calls could not
    answer an order assertion.

    With ``fail_refresh`` the refresh raises ``VectorStoreError`` before
    recording anything, which is the shape slice (b)'s 503 handler answers.
    """

    def __init__(self, calls: list[tuple], *, fail_refresh: bool = False) -> None:
        self._calls = calls
        self._fail_refresh = fail_refresh

    async def search_similar(  # noqa: ARG002
        self,
        text: str,
        limit: int = 3,
        threshold: float = 0.85,
        *,
        workspace_id: UUID,
        exclude_story_id: str,
    ) -> list:
        return []

    async def store_extraction(self, **kwargs: object) -> bool:  # noqa: ARG002
        return True

    async def set_has_invalid_tasks(self, *, extraction_id: str, has_invalid_tasks: bool) -> None:
        if self._fail_refresh:
            raise VectorStoreError("Qdrant unreachable")
        self._calls.append(("set_has_invalid_tasks", extraction_id, has_invalid_tasks))

    async def delete_by_story(  # noqa: ARG002
        self, *, workspace_id: UUID, user_story_id: str
    ) -> None:
        return None


def _override_invalidation_repo(app, calls: list[tuple]) -> None:
    """Route the mark endpoints' repository through a recording wrapper.

    The wrapper subclasses the real SQLAlchemy repository — the rows are
    written for real — and appends the write it just performed to ``calls``,
    the list the vector fake shares. The dependency object replaced is taken
    from the route module's own ``InvalidationRepoDep`` alias, so the override
    substitutes exactly the closure the handlers were declared with.
    """
    (depends_param,) = task_routes.InvalidationRepoDep.__metadata__
    inner_dependency = depends_param.dependency

    class _Recording(SQLAlchemyTaskInvalidationRepository):
        async def create(self, mark: TaskInvalidation) -> TaskInvalidation:
            created = await super().create(mark)
            calls.append(("invalidation_repo.create", str(created.id)))
            return created

        async def revoke(  # type: ignore[override]
            self, mark_id: UUID, *, revoked_by: UUID, revoked_at: datetime
        ) -> None:
            await super().revoke(mark_id, revoked_by=revoked_by, revoked_at=revoked_at)
            calls.append(("invalidation_repo.revoke", str(mark_id)))

    async def _recording_factory(
        session: Annotated[AsyncSession, Depends(get_session)],
    ) -> _Recording:
        return _Recording(session)

    app.dependency_overrides[inner_dependency] = _recording_factory


class TestInvalidationRefreshesTheVectorFlag:
    """The mark's vector consequence: the flag tracks the marks (WU3 part iii).

    Slice (b) made marks creatable and revocable but nothing moved the vector
    flag, so every mark excluded nothing from few-shot retrieval and nothing
    went red — D10's silent failure. These cases pin the two handlers' order:
    the refresh sits **before** the relational write, so a failing refresh
    leaves no mark persisted (create) or the mark still active (revoke), and a
    mark that exists while the flag still says valid cannot happen.

    Every case goes through the ``get_vector_store`` injection point; with no
    store configured the whole refresh block is skipped and both operations
    proceed.
    """

    async def test_marking_refreshes_the_flag_before_the_mark_row_is_created(
        self, app, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """201, and the refresh is recorded before the ``create`` — in that order."""
        calls: list[tuple] = []
        app.dependency_overrides[get_vector_store] = lambda: _RefreshingVectorStore(calls)
        _override_invalidation_repo(app, calls)
        story_id = (await seed_workspace()).story_id
        extraction = await seed_extraction(
            db_session,
            story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        task = await seed_task(db_session, story_id, "Implement login", extraction=extraction)

        response = await authed_client.post(
            f"/api/v1/tasks/{task.id}/invalidations", json={"reason": "Duplicates the export task"}
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert calls == [
            ("set_has_invalid_tasks", str(extraction.id), True),
            ("invalidation_repo.create", body["id"]),
        ]
        assert len(await _mark_rows(db_session, task.id)) == 1

    async def test_a_second_active_mark_on_the_extraction_leaves_the_flag_true(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Revoking one mark while another stands on the same version refreshes with ``True``.

        Two tasks of one extraction, each carrying an active mark: revoking one
        leaves the other standing, so the extraction still has at least one
        active mark and the flag must stay ``True``.
        """
        calls: list[tuple] = []
        app.dependency_overrides[get_vector_store] = lambda: _RefreshingVectorStore(calls)
        _override_invalidation_repo(app, calls)
        story_id = (await seed_workspace()).story_id
        extraction = await seed_extraction(
            db_session,
            story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        marked = await seed_task(db_session, story_id, "Marked task", extraction=extraction)
        other = await seed_task(db_session, story_id, "Still-marked task", extraction=extraction)
        marked_mark = await _seed_mark(db_session, marked.id, authed_user.id)
        await _seed_mark(db_session, other.id, authed_user.id)

        response = await authed_client.delete(f"/api/v1/tasks/{marked.id}/invalidations/current")

        assert response.status_code == 204, response.text
        assert calls == [
            ("set_has_invalid_tasks", str(extraction.id), True),
            ("invalidation_repo.revoke", str(marked_mark.id)),
        ]

    async def test_revoking_the_last_active_mark_clears_the_flag(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The last active mark revoked calls with ``False`` — before the revoke."""
        calls: list[tuple] = []
        app.dependency_overrides[get_vector_store] = lambda: _RefreshingVectorStore(calls)
        _override_invalidation_repo(app, calls)
        story_id = (await seed_workspace()).story_id
        extraction = await seed_extraction(
            db_session,
            story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        task = await seed_task(db_session, story_id, "Implement login", extraction=extraction)
        mark = await _seed_mark(db_session, task.id, authed_user.id)

        response = await authed_client.delete(f"/api/v1/tasks/{task.id}/invalidations/current")

        assert response.status_code == 204, response.text
        assert calls == [
            ("set_has_invalid_tasks", str(extraction.id), False),
            ("invalidation_repo.revoke", str(mark.id)),
        ]

    async def test_a_failing_refresh_on_mark_answers_503_and_persists_no_row(
        self, app, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """503 VECTOR_STORE_UNAVAILABLE, and no mark row exists to retry against.

        The refresh runs before the relational write on purpose: a mark that
        exists while the vector flag still says valid is D10's silent failure.
        """
        calls: list[tuple] = []
        app.dependency_overrides[get_vector_store] = lambda: _RefreshingVectorStore(
            calls, fail_refresh=True
        )
        _override_invalidation_repo(app, calls)
        story_id = (await seed_workspace()).story_id
        extraction = await seed_extraction(
            db_session,
            story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        task = await seed_task(db_session, story_id, "Implement login", extraction=extraction)

        response = await authed_client.post(
            f"/api/v1/tasks/{task.id}/invalidations", json={"reason": "Duplicates the export task"}
        )

        assert response.status_code == 503, response.text
        assert response.json()["error_code"] == "VECTOR_STORE_UNAVAILABLE"
        assert await _mark_rows(db_session, task.id) == []
        assert calls == []

    async def test_a_failing_refresh_on_revoke_answers_503_and_the_mark_stays_active(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ) -> None:
        """503 on the revoke path, and the mark row is unchanged and still active."""
        calls: list[tuple] = []
        app.dependency_overrides[get_vector_store] = lambda: _RefreshingVectorStore(
            calls, fail_refresh=True
        )
        _override_invalidation_repo(app, calls)
        story_id = (await seed_workspace()).story_id
        extraction = await seed_extraction(
            db_session,
            story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        task = await seed_task(db_session, story_id, "Implement login", extraction=extraction)
        await _seed_mark(db_session, task.id, authed_user.id)

        response = await authed_client.delete(f"/api/v1/tasks/{task.id}/invalidations/current")

        assert response.status_code == 503, response.text
        assert response.json()["error_code"] == "VECTOR_STORE_UNAVAILABLE"
        rows = await _mark_rows(db_session, task.id)
        assert len(rows) == 1
        assert rows[0].revoked_at is None
        assert calls == []

    async def test_without_a_vector_store_both_operations_proceed_and_no_refresh_is_made(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ) -> None:
        """``None`` means no points exist to flag: 201 then 204, refresh skipped.

        The recording repository is still wired, so the absence of any
        ``set_has_invalid_tasks`` entry in the shared list is directly
        witnessed — the only calls are the two relational writes.
        """
        calls: list[tuple] = []
        app.dependency_overrides[get_vector_store] = lambda: None
        _override_invalidation_repo(app, calls)
        story_id = (await seed_workspace()).story_id
        extraction = await seed_extraction(
            db_session,
            story_id,
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        task = await seed_task(db_session, story_id, "Implement login", extraction=extraction)

        marked = await authed_client.post(
            f"/api/v1/tasks/{task.id}/invalidations", json={"reason": "Duplicates the export task"}
        )
        revoked = await authed_client.delete(f"/api/v1/tasks/{task.id}/invalidations/current")

        assert marked.status_code == 201, marked.text
        assert revoked.status_code == 204, revoked.text
        assert calls == [
            ("invalidation_repo.create", marked.json()["id"]),
            ("invalidation_repo.revoke", marked.json()["id"]),
        ]
