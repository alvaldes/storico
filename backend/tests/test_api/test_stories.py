"""Integration tests for the UserStory CRUD API endpoints.

Tests must seed a workspace and project because the API validates that the
story's project exists and the authenticated user is a member of its workspace.
The chain comes from the shared ``seed_workspace`` factory; only the foreign
owner, which is a user rather than part of the chain, is built locally.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import User, UserStory
from storico.infrastructure.database.repositories import (
    SQLAlchemyUserRepository,
    SQLAlchemyUserStoryRepository,
)

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
        assert response.json()["type"] == "entity_not_found"


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


class TestDeleteStory:
    """DELETE /api/v1/stories/{story_id}"""

    async def test_delete_story(self, authed_client, seed_workspace):
        """POST then DELETE returns 204."""
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

    async def test_delete_story_not_found(self, authed_client):
        """DELETE on a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await authed_client.delete(f"/api/v1/stories/{fake_id}")
        assert response.status_code == 404
        assert response.json()["type"] == "entity_not_found"


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
        assert response.json()["detail"] == FORBIDDEN_NOT_A_MEMBER

    async def test_list_stories_by_a_foreign_project_is_forbidden(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """GET ``?project_id=`` for a project in a foreign workspace returns the shared 403."""
        project_id = await _seed_foreign_project(db_session, seed_workspace)

        response = await authed_client.get(f"/api/v1/stories/?project_id={project_id}")

        assert response.status_code == 403
        assert response.json()["detail"] == FORBIDDEN_NOT_A_MEMBER
