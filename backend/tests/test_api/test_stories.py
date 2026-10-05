"""Integration tests for the UserStory CRUD API endpoints.

Tests must seed a workspace and project because the API validates that the
story's project exists and the authenticated user is a member of its workspace.
The chain comes from the shared ``seed_workspace`` factory; only the foreign
owner, which is a user rather than part of the chain, is built locally.
"""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from storico.api.dependencies import get_vector_store
from storico.domain.entities import User, UserStory
from storico.domain.entities.exceptions import RepositoryError, VectorStoreError
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.ports.vector_store_port import VectorStorePort
from storico.infrastructure.database.models import (
    ExtractionModel,
    StoryDeletionModel,
    TaskModel,
)
from storico.infrastructure.database.repositories import (
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
)
from tests._helpers import seed_extraction, seed_task

RAW_TEXT = "As a user, I want to log in so that I can access my account"

FORBIDDEN_NOT_A_MEMBER = "Not a member of this workspace"


class TestCreateStory:
    """POST /api/v1/stories/"""

    async def test_create_story(self, authed_client, seed_workspace):
        """POST with valid data returns 201 and a UserStoryResponse body."""
        seeded = await seed_workspace(stories=0)
        payload = {
            "project_id": str(seeded.project_id),
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
        assert data["project_id"] == str(seeded.project_id)
        assert "id" in data
        assert "created_at" in data

    async def test_create_duplicate_story_fails(self, authed_client, seed_workspace):
        """POST with same actor, feature, benefit in same project returns 409 conflict."""
        seeded = await seed_workspace(stories=0)
        payload = {
            "project_id": str(seeded.project_id),
            "actor": "user",
            "feature": "log in",
            "benefit": "access my account",
            "raw_text": RAW_TEXT,
        }
        # First creation succeeds
        response1 = await authed_client.post("/api/v1/stories/", json=payload)
        assert response1.status_code == 201

        # Second creation with same actor, feature, benefit fails (even with different raw_text)
        response2 = await authed_client.post("/api/v1/stories/", json=payload)
        assert response2.status_code == 409
        data = response2.json()
        assert data["error_code"] == "DUPLICATE_USER_STORY"
        assert "already exists" in data["detail"].lower()
        assert "existing story id" in data["detail"].lower()
        # Verify the existing story ID is in the response
        existing_id = response1.json()["id"]
        assert existing_id in data["detail"]

    async def test_create_duplicate_story_with_different_raw_text_fails(
        self, authed_client, seed_workspace
    ):
        """POST with same parts but different raw_text format fails."""
        seeded = await seed_workspace(stories=0)
        payload1 = {
            "project_id": str(seeded.project_id),
            "actor": "user",
            "feature": "log in",
            "benefit": "access my account",
            "raw_text": "As a user, I want to log in, so that I can access my account",
        }
        # First creation succeeds
        response1 = await authed_client.post("/api/v1/stories/", json=payload1)
        assert response1.status_code == 201

        # Second creation with same parts but different raw_text format
        payload2 = {
            "project_id": str(seeded.project_id),
            "actor": "user",
            "feature": "log in",
            "benefit": "access my account",
            "raw_text": "As a(n) user, I want to log in, so that I can access my account",
        }
        response2 = await authed_client.post("/api/v1/stories/", json=payload2)
        assert response2.status_code == 409
        data = response2.json()
        assert data["error_code"] == "DUPLICATE_USER_STORY"
        assert "already exists" in data["detail"].lower()
        existing_id = response1.json()["id"]
        assert existing_id in data["detail"]


class TestListStories:
    """GET /api/v1/stories/"""

    async def test_list_stories(self, authed_client, seed_workspace):
        """POST one story, GET returns it in the items list."""
        seeded = await seed_workspace(stories=0)
        await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(seeded.project_id),
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

    async def test_list_stories_by_project(self, authed_client, seed_workspace):
        """GET ?project_id= filters stories by project."""
        project_a = (await seed_workspace(stories=0)).project_id
        project_b = (await seed_workspace(stories=0)).project_id

        await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project_a),
                "actor": "user",
                "feature": "feature A",
                "benefit": "benefit",
                "raw_text": RAW_TEXT,
            },
        )
        await authed_client.post(
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
        response = await authed_client.get(f"/api/v1/stories/?project_id={project_b}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["feature"] == "feature B"


class TestListStoriesPagination:
    """GET /api/v1/stories/ with paging params — every authorization branch.

    Each branch must report ``total`` as the full count of matching stories,
    not the page size, and a page past the end must return 0 items with the
    real total. Stories are saved through the repository with explicit
    ``created_at`` values so assertions pin the SQL ordering rule rather than
    wall-clock insertion order.
    """

    async def _seed_stories(self, db_session: AsyncSession, seed_workspace, count: int):
        """Seed an accessible workspace with ``count`` stories, one day apart.

        Returns ``(workspace_id, project_id, features)`` where ``features`` is
        the creation order (oldest first), so tests can name rows.
        """
        seeded = await seed_workspace(stories=0)
        features = [f"feature {day}" for day in range(1, count + 1)]
        for day, feature in enumerate(features, start=1):
            await SQLAlchemyUserStoryRepository(db_session).save(
                UserStory(
                    project_id=seeded.project_id,
                    actor="user",
                    feature=feature,
                    benefit="value",
                    raw_text=f"As a user, I want {feature} so that value",
                    created_at=datetime(2026, 1, day),
                )
            )
        return seeded.workspace_id, seeded.project_id, features

    async def test_no_filter_returns_the_full_total(self, authed_client, seed_workspace):
        """?page=1&size=2 with no filter returns 2 of 3 stories and total 3."""
        await seed_workspace(stories=2)
        await seed_workspace(stories=1)

        response = await authed_client.get("/api/v1/stories/?page=1&size=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3
        assert data["page"] == 1
        assert data["size"] == 2

    async def test_no_filter_past_the_end_returns_no_items_and_the_real_total(
        self, authed_client, seed_workspace
    ):
        """?page=9&size=2 with no filter returns 0 items but total 3.

        The fallback path: an empty page carries the real total so clients can
        still render '3 stories' while showing no rows.
        """
        await seed_workspace(stories=2)
        await seed_workspace(stories=1)

        response = await authed_client.get("/api/v1/stories/?page=9&size=2")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3

    async def test_workspace_filter_returns_the_full_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?workspace_id=&page=1&size=2 returns 2 of 3 stories and total 3."""
        ws_id, _project_id, _features = await self._seed_stories(db_session, seed_workspace, 3)

        response = await authed_client.get(f"/api/v1/stories/?workspace_id={ws_id}&page=1&size=2")

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

    async def test_workspace_filter_past_the_end_returns_no_items_and_the_real_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?workspace_id=&page=9&size=2 returns 0 items but total 3."""
        ws_id, _project_id, _features = await self._seed_stories(db_session, seed_workspace, 3)

        response = await authed_client.get(f"/api/v1/stories/?workspace_id={ws_id}&page=9&size=2")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3

    async def test_workspace_filter_orders_by_created_at_desc(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?workspace_id= orders the page by created_at DESC, the shared SQL rule."""
        ws_id, _project_id, features = await self._seed_stories(db_session, seed_workspace, 3)

        response = await authed_client.get(f"/api/v1/stories/?workspace_id={ws_id}")

        assert response.status_code == 200
        returned = [item["feature"] for item in response.json()["items"]]
        assert returned == list(reversed(features))

    async def test_project_filter_returns_the_full_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?project_id=&page=1&size=2 returns 2 of 3 stories and total 3."""
        _ws_id, project_id, _features = await self._seed_stories(db_session, seed_workspace, 3)

        response = await authed_client.get(
            f"/api/v1/stories/?project_id={project_id}&page=1&size=2"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

    async def test_project_filter_past_the_end_returns_no_items_and_the_real_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?project_id=&page=9&size=2 returns 0 items but total 3."""
        _ws_id, project_id, _features = await self._seed_stories(db_session, seed_workspace, 3)

        response = await authed_client.get(
            f"/api/v1/stories/?project_id={project_id}&page=9&size=2"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3


class TestGetStory:
    """GET /api/v1/stories/{story_id}"""

    async def test_get_story(self, authed_client, seed_workspace):
        """POST then GET by id returns the story."""
        seeded = await seed_workspace(stories=0)
        create_resp = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(seeded.project_id),
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
        assert response.json()["error_code"] == "ENTITY_NOT_FOUND"


class TestUpdateStory:
    """PUT /api/v1/stories/{story_id}"""

    async def test_update_story(self, authed_client, seed_workspace):
        """POST then PUT updates the story fields."""
        seeded = await seed_workspace(stories=0)
        create_resp = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(seeded.project_id),
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

    async def test_a_member_edits_all_four_story_fields(
        self, authed_client, authed_user, db_session: AsyncSession, seed_workspace
    ):
        """A plain MEMBER edits actor, feature, benefit and raw_text in one PUT (4.2).

        The story-edit surface is member-accessible by design (R14): the gate
        belongs to version-mutating operations, not to the story's own fields.
        The foreign-owner chain plus a MEMBER membership is what makes the
        caller a plain member rather than the workspace's owner.
        """
        from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
        from storico.infrastructure.database.repositories.workspace_member_repository import (
            SQLAlchemyWorkspaceMemberRepository,
        )

        owner = await SQLAlchemyUserRepository(db_session).save(
            User(email="member-edit-owner@test.com", name="Member Edit Owner")
        )
        seeded = await seed_workspace(user=owner, stories=0)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id,
                user_id=authed_user.id,
                role=WorkspaceRole.MEMBER,
            )
        )
        create_resp = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(seeded.project_id),
                "actor": "user",
                "feature": "old feature",
                "benefit": "old benefit",
                "raw_text": RAW_TEXT,
            },
        )
        story_id = create_resp.json()["id"]

        response = await authed_client.put(
            f"/api/v1/stories/{story_id}",
            json={
                "actor": "editor",
                "feature": "edited feature",
                "benefit": "edited benefit",
                "raw_text": "As an editor, I want an edited feature so that I get the edited benefit",
            },
        )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["actor"] == "editor"
        assert data["feature"] == "edited feature"
        assert data["benefit"] == "edited benefit"
        assert (
            data["raw_text"]
            == "As an editor, I want an edited feature so that I get the edited benefit"
        )


class _RecordingDeletionStore(VectorStorePort):
    """The deletion-recording fake: records every ``delete_by_story`` call."""

    def __init__(self) -> None:
        self.deletions: list[dict] = []

    async def search_similar(  # noqa: ARG002
        self,
        text: str,
        limit: int = 3,
        threshold: float = 0.85,
        *,
        workspace_id: UUID,  # noqa: ARG002
        exclude_story_id: str,  # noqa: ARG002
    ) -> list:
        return []

    async def store_extraction(self, **kwargs: object) -> bool:  # noqa: ARG002
        return True

    async def set_has_invalid_tasks(self, *, extraction_id: str, has_invalid_tasks: bool) -> None:
        # Deliberately inert no-op: task 3.6 replaces this stub with a recording
        # fake once the mark handlers call it.
        return None

    async def delete_by_story(self, *, workspace_id: UUID, user_story_id: str) -> None:
        self.deletions.append({"workspace_id": workspace_id, "user_story_id": user_story_id})


class _RaisingVectorStore(VectorStorePort):
    """A configured store that cannot be reached when its cleanup is asked for."""

    async def search_similar(  # noqa: ARG002
        self,
        text: str,
        limit: int = 3,
        threshold: float = 0.85,
        *,
        workspace_id: UUID,  # noqa: ARG002
        exclude_story_id: str,  # noqa: ARG002
    ) -> list:
        return []

    async def store_extraction(self, **kwargs: object) -> bool:  # noqa: ARG002
        return True

    async def set_has_invalid_tasks(self, *, extraction_id: str, has_invalid_tasks: bool) -> None:
        # Deliberately inert no-op: task 3.6 replaces this stub with a recording
        # fake once the mark handlers call it.
        return None

    async def delete_by_story(  # noqa: ARG002
        self,
        *,
        workspace_id: UUID,
        user_story_id: str,
    ) -> None:
        raise VectorStoreError("Qdrant unreachable")


async def _seed_two_completed_versions(db_session: AsyncSession, story_id: UUID) -> None:
    """Seed completed v1 and v2 through the birth path, each with one task row."""
    v1 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    v2 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    await seed_task(db_session, story_id, "V1 task", extraction=v1)
    await seed_task(db_session, story_id, "V2 task", extraction=v2)


async def _enforce_sqlite_cascades(db_session: AsyncSession) -> None:
    """Turn SQLite FK enforcement on for the shared in-memory connection.

    The unit schema carries the same ``ON DELETE CASCADE`` DDL as Postgres
    (``0014``), but SQLite only honours it with ``PRAGMA foreign_keys=ON``,
    which the suite does not set (see the note in
    ``test_repositories/test_custom_provider_repo.py``). The in-memory engine
    is a StaticPool — one shared DBAPI connection per test — so a pragma set
    here holds for the route's own session too, and the cascade witness below
    is behavioural, not declarative. The Postgres-only suite (task 4.16)
    re-proves it against the real engine.
    """
    await db_session.execute(text("PRAGMA foreign_keys=ON"))


async def _record_rows(db_session: AsyncSession) -> list[StoryDeletionModel]:
    """Every story_deletions row, read straight off the table."""
    result = await db_session.execute(select(StoryDeletionModel))
    return list(result.scalars().all())


async def _extraction_rows(db_session: AsyncSession, story_id: UUID) -> list[ExtractionModel]:
    """The story's extraction rows — the source rows of its vector points."""
    result = await db_session.execute(
        select(ExtractionModel).where(ExtractionModel.user_story_id == story_id)
    )
    return list(result.scalars().all())


async def _task_rows(db_session: AsyncSession, story_id: UUID) -> list[TaskModel]:
    """The story's task rows, read straight off the table."""
    result = await db_session.execute(select(TaskModel).where(TaskModel.user_story_id == story_id))
    return list(result.scalars().all())


class TestDeleteStory:
    """DELETE /api/v1/stories/{story_id}

    The owner-or-admin gate (D13) answers every refusal before the handler
    body; the body then runs the sanctioned ordering — snapshot, vector
    cleanup, delete-with-record. Every case pins the vector boundary with a
    ``get_vector_store`` dependency override: without one the route resolves a
    real ``QdrantAdapter`` and the suite's autouse guard fails the test.
    """

    async def test_delete_story(self, app, authed_client, seed_workspace):
        """POST then DELETE returns 204."""
        app.dependency_overrides[get_vector_store] = lambda: None
        seeded = await seed_workspace(stories=0)
        create_resp = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(seeded.project_id),
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

    async def test_delete_story_not_found(self, app, authed_client):
        """DELETE on a non-existent UUID returns 404."""
        app.dependency_overrides[get_vector_store] = lambda: None
        fake_id = str(uuid4())
        response = await authed_client.delete(f"/api/v1/stories/{fake_id}")
        assert response.status_code == 404
        assert response.json()["error_code"] == "ENTITY_NOT_FOUND"

    async def test_the_owner_deletes_a_story_with_versions_and_leaves_the_record(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The owner deletes a story with completed v1 and v2 (spec, 4.3's letter).

        The story, its extraction versions and their tasks are gone, and exactly
        one record row survives carrying the acting user, a timestamp and the
        destroyed version numbers ``[1, 2]`` in ascending order.
        """
        app.dependency_overrides[get_vector_store] = lambda: _RecordingDeletionStore()
        seeded = await seed_workspace(stories=1)
        await _seed_two_completed_versions(db_session, seeded.story_id)
        await _enforce_sqlite_cascades(db_session)

        response = await authed_client.delete(f"/api/v1/stories/{seeded.story_id}")

        assert response.status_code == 204, response.text
        get_resp = await authed_client.get(f"/api/v1/stories/{seeded.story_id}")
        assert get_resp.status_code == 404
        assert await _extraction_rows(db_session, seeded.story_id) == []
        assert await _task_rows(db_session, seeded.story_id) == []

        records = await _record_rows(db_session)
        assert len(records) == 1
        record = records[0]
        assert record.story_id == seeded.story_id
        assert record.project_id == seeded.project_id
        assert record.workspace_id == seeded.workspace_id
        assert record.actor == "user"
        assert record.feature == "use seeded feature 0"
        assert record.benefit == "the seeded chain is addressable"
        assert record.deleted_by == authed_user.id
        assert record.deleted_at is not None
        assert record.version_numbers == [1, 2]

    async def test_the_recording_store_receives_exactly_one_delete_by_story(
        self, app, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """The cleanup runs inside the deletion: one call, scoped to the story.

        The call carries the story's workspace id and the string form of its id
        — the same keys ``store_extraction`` writes into the point payloads.
        """
        store = _RecordingDeletionStore()
        app.dependency_overrides[get_vector_store] = lambda: store
        seeded = await seed_workspace(stories=1)
        await _seed_two_completed_versions(db_session, seeded.story_id)

        response = await authed_client.delete(f"/api/v1/stories/{seeded.story_id}")

        assert response.status_code == 204, response.text
        assert store.deletions == [
            {"workspace_id": seeded.workspace_id, "user_story_id": str(seeded.story_id)}
        ]

    async def test_a_raising_store_aborts_with_503_and_preserves_everything(
        self, app, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A vector-store failure aborts the whole operation with 503.

        The four-part witness: the story, its versions, its tasks and the
        vector points' source rows all still exist, and no record row was
        written — nothing to retry against a half-deleted story.
        """
        app.dependency_overrides[get_vector_store] = lambda: _RaisingVectorStore()
        seeded = await seed_workspace(stories=1)
        await _seed_two_completed_versions(db_session, seeded.story_id)
        await _enforce_sqlite_cascades(db_session)

        response = await authed_client.delete(f"/api/v1/stories/{seeded.story_id}")

        assert response.status_code == 503
        assert response.json()["error_code"] == "VECTOR_STORE_UNAVAILABLE"
        get_resp = await authed_client.get(f"/api/v1/stories/{seeded.story_id}")
        assert get_resp.status_code == 200
        assert len(await _extraction_rows(db_session, seeded.story_id)) == 2
        assert len(await _task_rows(db_session, seeded.story_id)) == 2
        assert await _record_rows(db_session) == []

    async def test_no_vector_store_configured_still_deletes_with_a_record(
        self, app, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """``None`` means no points exist to clean: the deletion completes.

        With no store configured the record is still written — the audit trail
        does not depend on the vector store existing.
        """
        app.dependency_overrides[get_vector_store] = lambda: None
        seeded = await seed_workspace(stories=1)
        await _seed_two_completed_versions(db_session, seeded.story_id)

        response = await authed_client.delete(f"/api/v1/stories/{seeded.story_id}")

        assert response.status_code == 204, response.text
        get_resp = await authed_client.get(f"/api/v1/stories/{seeded.story_id}")
        assert get_resp.status_code == 404
        assert len(await _record_rows(db_session)) == 1

    async def test_a_non_member_keeps_the_not_a_workspace_member_code(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A user with no membership row keeps the unchanged 403, not the gate code."""
        owner = await SQLAlchemyUserRepository(db_session).save(
            User(email="delete-owner@test.com", name="Delete Owner")
        )
        seeded = await seed_workspace(user=owner, stories=1)

        response = await authed_client.delete(f"/api/v1/stories/{seeded.story_id}")

        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
        story = await SQLAlchemyUserStoryRepository(db_session).find_by_id(seeded.story_id)
        assert story is not None
        assert await _record_rows(db_session) == []

    async def test_a_member_who_is_neither_owner_nor_admin_is_refused(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A plain MEMBER gets 403 with the story, its versions and tasks intact.

        No record row may exist either: a refusal must not leave an audit row
        for a deletion that never happened.
        """
        from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
        from storico.infrastructure.database.repositories.workspace_member_repository import (
            SQLAlchemyWorkspaceMemberRepository,
        )

        app.dependency_overrides[get_vector_store] = lambda: _RecordingDeletionStore()
        owner = await SQLAlchemyUserRepository(db_session).save(
            User(email="member-refusal-owner@test.com", name="Member Refusal Owner")
        )
        seeded = await seed_workspace(user=owner, stories=1)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id,
                user_id=authed_user.id,
                role=WorkspaceRole.MEMBER,
            )
        )
        await _seed_two_completed_versions(db_session, seeded.story_id)

        response = await authed_client.delete(f"/api/v1/stories/{seeded.story_id}")

        assert response.status_code == 403
        assert response.json()["error_code"] == "WORKSPACE_OWNER_OR_ADMIN_REQUIRED"
        story = await SQLAlchemyUserStoryRepository(db_session).find_by_id(seeded.story_id)
        assert story is not None
        assert len(await _extraction_rows(db_session, seeded.story_id)) == 2
        assert len(await _task_rows(db_session, seeded.story_id)) == 2
        assert await _record_rows(db_session) == []

    async def test_a_non_owner_admin_member_deletes_the_story(
        self, app, authed_client, authed_user: User, db_session: AsyncSession, seed_workspace
    ) -> None:
        """A member with role ADMIN who is not the owner passes the delete gate (4.2).

        The MEMBER refusal above pins the negative; the same chain with the
        membership raised to ADMIN answers 204, leaves the story gone and
        writes the record — the gate is the owner-or-admin rule, not
        ownership alone.
        """
        from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
        from storico.infrastructure.database.repositories.workspace_member_repository import (
            SQLAlchemyWorkspaceMemberRepository,
        )

        app.dependency_overrides[get_vector_store] = lambda: _RecordingDeletionStore()
        owner = await SQLAlchemyUserRepository(db_session).save(
            User(email="admin-delete-owner@test.com", name="Admin Delete Owner")
        )
        seeded = await seed_workspace(user=owner, stories=1)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id,
                user_id=authed_user.id,
                role=WorkspaceRole.ADMIN,
            )
        )
        await _seed_two_completed_versions(db_session, seeded.story_id)

        response = await authed_client.delete(f"/api/v1/stories/{seeded.story_id}")

        assert response.status_code == 204, response.text
        story = await SQLAlchemyUserStoryRepository(db_session).find_by_id(seeded.story_id)
        assert story is None
        assert len(await _record_rows(db_session)) == 1

    async def test_a_repository_error_in_the_record_insert_answers_5xx(
        self,
        app,
        authed_client,
        db_session: AsyncSession,
        seed_workspace,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """A failing record insert answers 500 and leaves the story present.

        The repository-level half of this case (rollback semantics) lives in
        ``tests/test_repositories/test_user_story_repo.py``; this pins only the
        API surface: the repository error escapes the route as a 5xx, and the
        story survives for a retry.
        """
        app.dependency_overrides[get_vector_store] = lambda: None
        seeded = await seed_workspace(stories=1)

        async def _boom(self: object, user_story_id: object, record: object) -> None:  # noqa: ARG001
            raise RepositoryError("Database error deleting user story")

        monkeypatch.setattr(SQLAlchemyUserStoryRepository, "delete_with_record", _boom)

        response = await authed_client.delete(f"/api/v1/stories/{seeded.story_id}")

        assert response.status_code == 500
        story = await SQLAlchemyUserStoryRepository(db_session).find_by_id(seeded.story_id)
        assert story is not None


async def _seed_foreign_project(db_session: AsyncSession, seed_workspace) -> UUID:
    """Seed a workspace+project whose workspace ``authed_user`` is not in.

    The chain is fully consistent — the other user really is the workspace's
    admin — so the caller's own membership is the only thing between the request
    and a 201/200, and the foreign key on ``projects.workspace_id`` stays intact.
    """
    other = await SQLAlchemyUserRepository(db_session).save(
        User(email="other-story-owner@test.com", name="Other Story Owner")
    )
    return (await seed_workspace(user=other, stories=0)).project_id


class TestStoryMembership:
    """The 403 meaning "not a member of the workspace that owns this project".

    ``create_story`` and the ``?project_id=`` branch of ``list_stories`` resolve
    the project's workspace and check membership inline rather than delegating to
    ``require_story_workspace_access``, so the shared payload is pinned here too:
    one fact about one check, one string, in every route that reports it. The
    sibling ``require_story_workspace_access`` file pins the walk's own copy.
    """

    async def test_create_story_is_forbidden_for_a_non_member(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """POST into a workspace the caller is not a member of returns the shared 403."""
        project_id = await _seed_foreign_project(db_session, seed_workspace)

        response = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(project_id),
                "actor": "user",
                "feature": "write into a foreign workspace",
                "benefit": "this must be refused",
                "raw_text": RAW_TEXT,
            },
        )

        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
        assert response.json()["detail"] == FORBIDDEN_NOT_A_MEMBER

    async def test_list_stories_by_a_foreign_project_is_forbidden(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """GET ``?project_id=`` for a project in a foreign workspace returns the shared 403."""
        project_id = await _seed_foreign_project(db_session, seed_workspace)

        response = await authed_client.get(f"/api/v1/stories/?project_id={project_id}")

        assert response.status_code == 403
        assert response.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
        assert response.json()["detail"] == FORBIDDEN_NOT_A_MEMBER

    @pytest.mark.unit
    async def test_request_without_a_token_is_unauthorized_with_a_coded_envelope(
        self, async_client
    ):
        """A request with no bearer token gets 401 with code and prose together.

        The pair is the point (WU3): ``error_code`` is the contract clients
        branch on, while the prose ``detail`` stays byte-identical as the
        human-readable fallback that reaches the raw panel.
        """
        response = await async_client.get("/api/v1/stories/")
        body = response.json()

        assert response.status_code == 401
        assert body["error_code"] == "AUTH_TOKEN_INVALID"
        assert body["detail"] == "Invalid or missing authentication token"


class TestStoryVersionsEndpoint:
    """GET /api/v1/stories/{story_id}/versions — the version selector's read.

    WU3 task 3.9's own GREEN proof: the bare unpaginated array ordered
    ``version_number DESC`` with the two derived decorators — ``is_current`` is
    the first ``completed`` entry of the ordered list (never merely the highest
    entry), ``has_output`` is ``status == completed``. The triangulation edges
    (25 versions in one payload, the 404/403 posture, the failed entry's full
    field disclosure) belong to task 3.10 and are deliberately not here.
    """

    async def _create_story(self, authed_client, seeded) -> str:
        """Create one story through the API and return its id as a string."""
        response = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(seeded.project_id),
                "actor": "user",
                "feature": "log in",
                "benefit": "access my account",
                "raw_text": RAW_TEXT,
            },
        )
        assert response.status_code == 201
        return response.json()["id"]

    async def test_lists_every_version_newest_first_and_derives_the_flags(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """Three versions (v1/v2 completed, v3 pending) come back newest first,
        with exactly v2 marked current and the selector's exact field set."""
        seeded = await seed_workspace(stories=0)
        story_id = await self._create_story(authed_client, seeded)
        await seed_extraction(
            db_session,
            UUID(story_id),
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_extraction(
            db_session,
            UUID(story_id),
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )
        await seed_extraction(db_session, UUID(story_id))  # pending

        response = await authed_client.get(f"/api/v1/stories/{story_id}/versions")

        assert response.status_code == 200
        data = response.json()
        # A bare array, not a pagination envelope: the list is the selector's
        # input and must arrive whole.
        assert isinstance(data, list)
        assert [entry["version_number"] for entry in data] == [3, 2, 1]
        # ``is_current`` is the first completed entry of the DESC list — v2, not
        # v3 (the highest-numbered entry, but pending) and not both completed ones.
        current = [entry for entry in data if entry["is_current"]]
        assert [entry["version_number"] for entry in current] == [2]
        assert [entry["has_output"] for entry in data] == [False, True, True]
        for entry in data:
            assert set(entry.keys()) == {
                "id",
                "version_number",
                "status",
                "model_used",
                "provider",
                "temperature",
                "created_at",
                "completed_at",
                "error_info",
                "is_current",
                "has_output",
            }
        assert data[0]["status"] == "pending"
        assert data[0]["completed_at"] is None
        assert data[1]["completed_at"] is not None

    async def test_a_story_with_no_completed_version_has_no_current_entry(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A story whose only run failed answers 200 with the array and no
        ``is_current`` anywhere — the legal state the frozen semantics already
        treat as frozen. The failed entry's field disclosure is task 3.10's edge.
        """
        seeded = await seed_workspace(stories=0)
        story_id = await self._create_story(authed_client, seeded)
        await seed_extraction(
            db_session,
            UUID(story_id),
            status=ExtractionStatus.FAILED,
            error_info="model unreachable",
        )

        response = await authed_client.get(f"/api/v1/stories/{story_id}/versions")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["is_current"] is False
        assert data[0]["has_output"] is False

    async def test_three_completed_versions_mark_exactly_the_highest_current(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """v1, v2 and v3 all completed: exactly v3 — the highest-numbered
        completed run — is current, and every completed entry has output."""
        seeded = await seed_workspace(stories=0)
        story_id = await self._create_story(authed_client, seeded)
        for _ in range(3):
            await seed_extraction(
                db_session,
                UUID(story_id),
                status=ExtractionStatus.COMPLETED,
                completed_at=datetime.now(UTC),
            )

        response = await authed_client.get(f"/api/v1/stories/{story_id}/versions")

        assert response.status_code == 200
        data = response.json()
        assert [entry["version_number"] for entry in data] == [3, 2, 1]
        current = [entry for entry in data if entry["is_current"]]
        assert [entry["version_number"] for entry in current] == [3]
        assert [entry["has_output"] for entry in data] == [True, True, True]

    async def test_twenty_five_versions_arrive_in_one_untruncated_payload(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """25 versions come back in one payload — the unbounded proof at the HTTP edge.

        ``list_versions`` is deliberately unpaginated: a 20-row window would
        silently drop five entries of this exact story's history. The assertion
        counts the whole ordered list and derives both flags across all of it
        (v25 pending, v1-v24 completed), so truncation could not hide behind a
        passing ``is_current`` either.
        """
        seeded = await seed_workspace(stories=0)
        story_id = await self._create_story(authed_client, seeded)
        for number in range(1, 26):
            if number < 25:
                await seed_extraction(
                    db_session,
                    UUID(story_id),
                    status=ExtractionStatus.COMPLETED,
                    completed_at=datetime.now(UTC),
                )
            else:
                await seed_extraction(db_session, UUID(story_id))  # pending

        response = await authed_client.get(f"/api/v1/stories/{story_id}/versions")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 25
        assert [entry["version_number"] for entry in data] == list(range(25, 0, -1))
        current = [entry for entry in data if entry["is_current"]]
        assert [entry["version_number"] for entry in current] == [24]
        assert [entry["has_output"] for entry in data] == [False] + [True] * 24

    async def test_a_missing_story_is_404_and_a_non_member_is_403(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """The versions read refuses exactly like GET /{story_id}: a missing
        story is 404 and a non-member is 403 — never a silent empty 200."""
        missing = await authed_client.get(f"/api/v1/stories/{uuid4()}/versions")

        assert missing.status_code == 404
        assert missing.json()["error_code"] == "ENTITY_NOT_FOUND"

        other = await SQLAlchemyUserRepository(db_session).save(
            User(email="other-versions-owner@test.com", name="Other Versions Owner")
        )
        foreign = await seed_workspace(user=other, stories=0)
        foreign_story = await SQLAlchemyUserStoryRepository(db_session).save(
            UserStory(
                project_id=foreign.project_id,
                actor="user",
                feature="read my versions",
                benefit="see the history",
                raw_text=RAW_TEXT,
            )
        )

        forbidden = await authed_client.get(f"/api/v1/stories/{foreign_story.id}/versions")

        assert forbidden.status_code == 403
        assert forbidden.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
        assert forbidden.json()["detail"] == FORBIDDEN_NOT_A_MEMBER

    async def test_a_failed_version_discloses_its_run_metadata_and_has_no_output(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """A failed version is surfaced honestly: the run's status, error,
        model, provider and temperature all arrive, and ``has_output`` is false."""
        seeded = await seed_workspace(stories=0)
        story_id = await self._create_story(authed_client, seeded)
        await seed_extraction(
            db_session,
            UUID(story_id),
            status=ExtractionStatus.FAILED,
            error_info="model unreachable",
            model_used="mistral",
            provider="ollama",
            temperature=0.2,
        )

        response = await authed_client.get(f"/api/v1/stories/{story_id}/versions")

        assert response.status_code == 200
        entry = response.json()[0]
        assert entry["status"] == "failed"
        assert entry["error_info"] == "model unreachable"
        assert entry["model_used"] == "mistral"
        assert entry["provider"] == "ollama"
        assert entry["temperature"] == 0.2
        assert entry["has_output"] is False
        assert entry["is_current"] is False

    async def test_a_member_reads_the_versions(
        self, authed_client, authed_user, db_session: AsyncSession, seed_workspace
    ):
        """A plain MEMBER gets 200 and the story's versions (4.2).

        The versions read is member-accessible by design (R14): the 403 gate
        above is for a non-member, not for a member who is neither owner nor
        admin — the selector must work for the whole team.
        """
        from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
        from storico.infrastructure.database.repositories.workspace_member_repository import (
            SQLAlchemyWorkspaceMemberRepository,
        )

        owner = await SQLAlchemyUserRepository(db_session).save(
            User(email="member-versions-owner@test.com", name="Member Versions Owner")
        )
        seeded = await seed_workspace(user=owner, stories=0)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id,
                user_id=authed_user.id,
                role=WorkspaceRole.MEMBER,
            )
        )
        story_id = await self._create_story(authed_client, seeded)
        await seed_extraction(
            db_session,
            UUID(story_id),
            status=ExtractionStatus.COMPLETED,
            completed_at=datetime.now(UTC),
        )

        response = await authed_client.get(f"/api/v1/stories/{story_id}/versions")

        assert response.status_code == 200, response.text
        data = response.json()
        assert [entry["version_number"] for entry in data] == [1]
        assert data[0]["is_current"] is True


class TestStoryInvalidationsEndpoint:
    """GET /api/v1/stories/{story_id}/invalidations — the card flag's read.

    The story-detail card renders a ``Flag`` control per task, so the page needs
    to know which of the story's tasks carry an active mark. This read answers
    exactly that, in the versions read's shape (a bare unpaginated array) and
    under the marks reads' gate (membership only: every member may read the
    record, the mutations are the gated half).
    """

    async def _create_story(self, authed_client, seeded, feature: str = "log in") -> str:
        """Create one story through the API and return its id as a string.

        ``feature`` is a knob because the duplicate-story guard rejects two
        stories of one project with the same text, and the scope case below
        needs two distinct stories in one project.
        """
        response = await authed_client.post(
            "/api/v1/stories/",
            json={
                "project_id": str(seeded.project_id),
                "actor": "user",
                "feature": feature,
                "benefit": "access my account",
                "raw_text": (f"As a user, I want to {feature} so that I can access my account"),
            },
        )
        assert response.status_code == 201
        return response.json()["id"]

    async def _seed_mark(self, db_session: AsyncSession, task_id: UUID, *, reason: str, marked_at):
        """Seed one active mark through the repository's own birth path."""
        from storico.domain.entities.task_invalidation import TaskInvalidation
        from storico.infrastructure.database.repositories import (
            SQLAlchemyTaskInvalidationRepository,
        )

        return await SQLAlchemyTaskInvalidationRepository(db_session).create(
            TaskInvalidation(task_id=task_id, reason=reason, marked_at=marked_at)
        )

    async def test_lists_exactly_the_storys_active_marks_newest_first(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """Two active marks of this story come back; a revoked one and another
        story's active one do not. The payload is the mark plus its ``task_id``,
        which is the only fact the card needs to turn a flag on."""
        seeded = await seed_workspace(stories=0)
        story_id = await self._create_story(authed_client, seeded)
        other_story_id = await self._create_story(authed_client, seeded, feature="reset password")
        first = await seed_task(db_session, UUID(story_id), "First task")
        second = await seed_task(db_session, UUID(story_id), "Second task")
        revoked_task = await seed_task(db_session, UUID(story_id), "Revoked task")
        foreign_task = await seed_task(db_session, UUID(other_story_id), "Other story task")

        newer = await self._seed_mark(
            db_session,
            first.id,
            reason="Newer mark",
            marked_at=datetime(2026, 10, 5, 12, 0, tzinfo=UTC),
        )
        older = await self._seed_mark(
            db_session,
            second.id,
            reason="Older mark",
            marked_at=datetime(2026, 10, 5, 10, 0, tzinfo=UTC),
        )
        to_revoke = await self._seed_mark(
            db_session,
            revoked_task.id,
            reason="Revoked mark",
            marked_at=datetime(2026, 10, 5, 11, 0, tzinfo=UTC),
        )
        await self._seed_mark(
            db_session,
            foreign_task.id,
            reason="Other story's mark",
            marked_at=datetime(2026, 10, 5, 13, 0, tzinfo=UTC),
        )
        from storico.infrastructure.database.repositories import (
            SQLAlchemyTaskInvalidationRepository,
        )

        await SQLAlchemyTaskInvalidationRepository(db_session).revoke(
            to_revoke.id,
            revoked_by=uuid4(),
            revoked_at=datetime(2026, 10, 5, 14, 0, tzinfo=UTC),
        )

        response = await authed_client.get(f"/api/v1/stories/{story_id}/invalidations")

        assert response.status_code == 200, response.text
        data = response.json()
        assert isinstance(data, list)
        assert [entry["id"] for entry in data] == [str(newer.id), str(older.id)]
        assert [entry["task_id"] for entry in data] == [str(first.id), str(second.id)]
        for entry in data:
            assert set(entry.keys()) == {
                "id",
                "task_id",
                "reason",
                "marked_by",
                "marked_at",
                "revoked_by",
                "revoked_at",
            }
            assert entry["revoked_at"] is None

    async def test_a_member_reads_the_storys_marks(
        self, authed_client, authed_user, db_session: AsyncSession, seed_workspace
    ):
        """A plain MEMBER gets 200: the gate is membership, not ownership."""
        from storico.domain.entities.workspace_member import WorkspaceMember, WorkspaceRole
        from storico.infrastructure.database.repositories.workspace_member_repository import (
            SQLAlchemyWorkspaceMemberRepository,
        )

        owner = await SQLAlchemyUserRepository(db_session).save(
            User(email="member-marks-owner@test.com", name="Member Marks Owner")
        )
        seeded = await seed_workspace(user=owner, stories=0)
        await SQLAlchemyWorkspaceMemberRepository(db_session).add(
            WorkspaceMember(
                workspace_id=seeded.workspace_id,
                user_id=authed_user.id,
                role=WorkspaceRole.MEMBER,
            )
        )
        story_id = await self._create_story(authed_client, seeded)
        task = await seed_task(db_session, UUID(story_id), "Member-visible task")
        await self._seed_mark(
            db_session,
            task.id,
            reason="Visible to every member",
            marked_at=datetime(2026, 10, 5, 12, 0, tzinfo=UTC),
        )

        response = await authed_client.get(f"/api/v1/stories/{story_id}/invalidations")

        assert response.status_code == 200, response.text
        assert [entry["task_id"] for entry in response.json()] == [str(task.id)]

    async def test_a_missing_story_is_404_and_a_non_member_is_403(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """The unchanged access walk's two refusals, with nothing leaked."""
        from storico.infrastructure.database.repositories import (
            SQLAlchemyUserStoryRepository,
        )

        foreign_owner = await SQLAlchemyUserRepository(db_session).save(
            User(email="foreign-marks-owner@test.com", name="Foreign Marks Owner")
        )
        foreign_seeded = await seed_workspace(user=foreign_owner, stories=0)
        foreign_story = await SQLAlchemyUserStoryRepository(db_session).save(
            UserStory(
                project_id=foreign_seeded.project_id,
                actor="user",
                feature="stay private",
                benefit="the gate holds",
                raw_text=RAW_TEXT,
            )
        )

        missing = await authed_client.get(f"/api/v1/stories/{uuid4()}/invalidations")
        forbidden = await authed_client.get(f"/api/v1/stories/{foreign_story.id}/invalidations")

        assert missing.status_code == 404
        assert forbidden.status_code == 403
        assert forbidden.json()["error_code"] == "NOT_A_WORKSPACE_MEMBER"
