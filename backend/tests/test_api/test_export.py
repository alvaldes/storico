"""Integration tests for the Export API endpoint — GET /api/v1/workspaces/{id}/export/tasks.

Tests content-type, filename header, content shape for JSON and Markdown,
and error handling for unknown format.
"""

from datetime import UTC, datetime
from uuid import uuid4

import jwt as pyjwt
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import Task, User
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.task import TaskStatus
from storico.domain.entities.user_story import UserStory
from storico.infrastructure.database.repositories import (
    SQLAlchemyTaskRepository,
    SQLAlchemyUserRepository,
)
from storico.infrastructure.database.repositories.user_story_repository import (
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import seed_extraction, seed_task


def _get_jwt_secret() -> str:
    """Load the JWT secret from Settings (respects env overrides)."""
    from storico.config.settings import Settings

    return Settings.load().auth_jwt_secret


def _auth_headers(user_id: str) -> dict:
    secret = _get_jwt_secret()
    token = pyjwt.encode({"sub": user_id}, secret, algorithm="HS256")
    return {"Authorization": f"Bearer {token}"}


async def _create_user(db_session: AsyncSession) -> User:
    repo = SQLAlchemyUserRepository(db_session)
    user = User(email="export@test.com", name="Export Test")
    saved = await repo.save(user)
    await repo.link_account(saved.id, "google", "g-export-test")
    return saved


async def _create_story(db_session: AsyncSession, project_id) -> UserStory:
    """Create the story this file's export assertions embed, in a seeded project.

    Only the story row is built here. The workspace -> project -> membership
    chain comes from the shared ``seed_workspace`` factory, so the project must
    already exist. The story's ``raw_text`` is pinned here because the Markdown
    export renders it verbatim as a section header.
    """
    story = UserStory(
        project_id=project_id,
        actor="user",
        feature="log in",
        benefit="access account",
        raw_text="As a user, I want to log in so that I can access my account",
    )
    return await SQLAlchemyUserStoryRepository(db_session).save(story)


async def _create_tasks(db_session: AsyncSession, story_id, count=3) -> list[Task]:
    """Create ``count`` tasks with the label shape this file asserts on.

    Local on purpose: the first task carries ``["backend", "api"]`` and the rest
    ``["frontend"]`` because the export assertions pin exactly that, so it is a
    fixture for these tests rather than a knob on the shared seeding factory. The
    tasks share one extraction allocated through the birth path (``0028`` made
    ``tasks.extraction_id`` ``NOT NULL``), and that extraction is ``completed``
    on purpose: the export serializes each story's current-version tasks only,
    so tasks hanging off a pending run would be invisible to every case here.
    """
    extraction = await seed_extraction(
        db_session, story_id, status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC)
    )
    repo = SQLAlchemyTaskRepository(db_session)
    tasks = []
    for i in range(count):
        task = Task(
            user_story_id=story_id,
            extraction_id=extraction.id,
            title=f"Task {i + 1}",
            description=f"Description for task {i + 1}",
            status=TaskStatus.TODO,
            priority="medium",
            labels=["backend", "api"] if i == 0 else ["frontend"],
            dependencies=[],
        )
        saved = await repo.save(task)
        tasks.append(saved)
    return tasks


class TestExportTasks:
    """GET /api/v1/workspaces/{workspace_id}/export/tasks"""

    @pytest.mark.asyncio
    async def test_export_json(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET ?format=json returns JSON with correct content-type and filename."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user, stories=0)
        story = await _create_story(db_session, seeded.project_id)
        ws_id = seeded.workspace_id
        await _create_tasks(db_session, story.id, count=2)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json; charset=utf-8"
        assert (
            response.headers["content-disposition"]
            == f'attachment; filename="tasks-export-{ws_id}.json"'
        )

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["title"] == "Task 1"
        assert data[0]["description"] == "Description for task 1"
        assert data[0]["labels"] == ["backend", "api"]
        assert "created_at" in data[0]
        assert "updated_at" in data[0]

    @pytest.mark.asyncio
    async def test_export_markdown(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET ?format=markdown returns Markdown with correct headers."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user, stories=0)
        story = await _create_story(db_session, seeded.project_id)
        ws_id = seeded.workspace_id
        await _create_tasks(db_session, story.id, count=1)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/export/tasks?format=markdown",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        assert response.headers["content-type"] == "text/markdown; charset=utf-8"
        assert (
            response.headers["content-disposition"]
            == f'attachment; filename="tasks-export-{ws_id}.md"'
        )

        content = response.text
        assert "# Tasks Export" in content
        assert "## As a user, I want to log in so that I can access my account" in content
        assert "- **Task 1** — Description for task 1" in content
        assert "#backend #api" in content

    @pytest.mark.asyncio
    async def test_export_json_empty(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET with no tasks returns empty JSON array."""
        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_export_markdown_empty(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET with no tasks returns Markdown with zero count."""
        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/export/tasks?format=markdown",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        assert "# Tasks Export" in response.text

    @pytest.mark.asyncio
    async def test_export_json_tasks_have_all_fields(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET ?format=json returns all expected task fields."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user, stories=0)
        story = await _create_story(db_session, seeded.project_id)
        ws_id = seeded.workspace_id
        await _create_tasks(db_session, story.id, count=1)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        task = response.json()[0]
        assert "id" in task
        assert "user_story_id" in task
        assert "title" in task
        assert "description" in task
        assert "status" in task
        assert "priority" in task
        assert "labels" in task
        assert "dependencies" in task
        assert "created_at" in task
        assert "updated_at" in task

    @pytest.mark.asyncio
    async def test_export_markdown_labels_and_deps(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET ?format=markdown renders labels and resolves dependencies to titles."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user, stories=0)
        story_id = (await _create_story(db_session, seeded.project_id)).id
        ws_id = seeded.workspace_id
        task_repo = SQLAlchemyTaskRepository(db_session)
        # The shared version is completed on purpose: the export serializes
        # each story's current-version tasks only (same reconciliation as
        # ``_create_tasks``).
        extraction = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC)
        )
        predecessor = await task_repo.save(
            Task(
                user_story_id=story_id,
                extraction_id=extraction.id,
                title="Predecessor task",
                description="Comes first",
                status=TaskStatus.DONE,
                priority="high",
                labels=[],
                dependencies=[],
            )
        )
        task = Task(
            user_story_id=story_id,
            extraction_id=extraction.id,
            title="Task with meta",
            description="Has labels and deps",
            status=TaskStatus.TODO,
            priority="high",
            labels=["db", "backend"],
            dependencies=[str(predecessor.id)],
        )
        await task_repo.save(task)

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/export/tasks?format=markdown",
            headers=_auth_headers(str(user.id)),
        )
        assert "#db #backend" in response.text
        # The dependency reference is resolved to the referenced task's title.
        assert "→ Predecessor task" in response.text

    @pytest.mark.asyncio
    async def test_export_unknown_format(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """GET with unsupported format returns 400."""
        user = await _create_user(db_session)
        ws_id = (await seed_workspace(user=user, stories=0)).workspace_id

        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/export/tasks?format=csv",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 400
        assert response.json()["error_code"] == "UNSUPPORTED_EXPORT_FORMAT"
        assert "Unsupported format" in response.text

    @pytest.mark.asyncio
    async def test_export_unauthorized(self, async_client, db_session: AsyncSession) -> None:
        """GET without auth headers returns 401."""
        ws_id = uuid4()
        response = await async_client.get(
            f"/api/v1/workspaces/{ws_id}/export/tasks?format=json",
            headers={},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_workspace_not_found(self, async_client, db_session: AsyncSession) -> None:
        """GET with non-existent workspace returns 404."""
        user = await _create_user(db_session)
        fake_id = uuid4()

        response = await async_client.get(
            f"/api/v1/workspaces/{fake_id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 404


class TestExportCurrentVersionFilter:
    """GET /api/v1/workspaces/{id}/export/tasks — the current-version filter.

    The export rides the filtered statement: only the tasks of each story's
    current (highest-numbered ``completed``) version are serialized, in both
    formats. A story whose only run is ``failed`` has no current version and
    contributes nothing, while the file itself stays valid for the stories
    that do.
    """

    async def _seed_two_versions(self, db_session: AsyncSession, story_id) -> None:
        """Give ``story_id`` a superseded v1 (2 tasks) and a current v2 (4 tasks)."""
        v1 = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC)
        )
        await seed_task(db_session, story_id, "v1 task one", extraction=v1)
        await seed_task(db_session, story_id, "v1 task two", extraction=v1)
        v2 = await seed_extraction(
            db_session, story_id, status=ExtractionStatus.COMPLETED, completed_at=datetime.now(UTC)
        )
        for i in range(1, 5):
            await seed_task(db_session, story_id, f"v2 task {i}", extraction=v2)

    @pytest.mark.asyncio
    async def test_json_export_of_a_superseded_story_contains_exactly_the_current_tasks(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """JSON export of a story with v1 and v2 both completed carries exactly v2's 4 tasks."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user, stories=0)
        story = await _create_story(db_session, seeded.project_id)
        await self._seed_two_versions(db_session, story.id)

        response = await async_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        data = response.json()
        titles = [item["title"] for item in data]
        assert titles == ["v2 task 1", "v2 task 2", "v2 task 3", "v2 task 4"]
        assert not any("v1 task" in title for title in titles)

    @pytest.mark.asyncio
    async def test_markdown_export_of_a_superseded_story_contains_exactly_the_current_tasks(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """Markdown export of a story with v1 and v2 both completed renders exactly v2's 4 tasks."""
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user, stories=0)
        story = await _create_story(db_session, seeded.project_id)
        await self._seed_two_versions(db_session, story.id)

        response = await async_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/tasks?format=markdown",
            headers=_auth_headers(str(user.id)),
        )
        assert response.status_code == 200
        content = response.text
        assert "# Tasks Export" in content
        for i in range(1, 5):
            assert f"v2 task {i}" in content
        assert "v1 task" not in content

    @pytest.mark.asyncio
    async def test_a_story_whose_only_run_is_failed_contributes_nothing(
        self, async_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A failed-only story appears in neither format; the file stays valid.

        The workspace also carries a healthy story so the export has content:
        the assertion is that the failed story is absent, not that the file is
        empty — a story with no current version must not break the export for
        the stories that have one.
        """
        user = await _create_user(db_session)
        seeded = await seed_workspace(user=user, stories=0)
        story_repo = SQLAlchemyUserStoryRepository(db_session)
        healthy_story = await story_repo.save(
            UserStory(
                project_id=seeded.project_id,
                actor="user",
                feature="ship the release",
                benefit="value",
                raw_text="As a user, I want to ship the release so that value",
            )
        )
        failed_story = await story_repo.save(
            UserStory(
                project_id=seeded.project_id,
                actor="user",
                feature="fail quietly",
                benefit="nothing",
                raw_text="As a user, I want to fail quietly so that nothing",
            )
        )
        await seed_task(db_session, healthy_story.id, "Healthy task")
        failed_version = await seed_extraction(
            db_session, failed_story.id, status=ExtractionStatus.FAILED
        )
        await seed_task(db_session, failed_story.id, "Failed story task", extraction=failed_version)

        json_response = await async_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/tasks?format=json",
            headers=_auth_headers(str(user.id)),
        )
        assert json_response.status_code == 200
        data = json_response.json()  # the file parses: it stays valid
        assert [item["title"] for item in data] == ["Healthy task"]
        assert not any(item["user_story_id"] == str(failed_story.id) for item in data)

        markdown_response = await async_client.get(
            f"/api/v1/workspaces/{seeded.workspace_id}/export/tasks?format=markdown",
            headers=_auth_headers(str(user.id)),
        )
        assert markdown_response.status_code == 200
        content = markdown_response.text
        assert "# Tasks Export" in content
        assert "Healthy task" in content
        assert "fail quietly" not in content
        assert "Failed story task" not in content
