"""Integration tests for the Extraction read-only API endpoints.

Every case here must seed the full ``workspace → project → story`` chain plus
the caller's membership: the routes resolve an extraction's workspace by
walking that chain and then require membership in it.
"""

from datetime import datetime
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import Extraction, UserStory
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyUserStoryRepository,
)


class TestListExtractions:
    """GET /api/v1/extractions/"""

    async def test_list_extractions_by_story(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """Save an extraction for a seeded story, then GET by user_story_id.

        The filter branch resolves the story's project and workspace and then
        checks the caller's membership, so the seeded chain is part of the
        contract under test — not just the extraction row.
        """
        story_id = (await seed_workspace()).story_id
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="llama3.2",
            raw_response="1. summary: Task one\ndescription: Do it",
        )
        await repo.save(extraction)

        response = await authed_client.get(f"/api/v1/extractions/?user_story_id={story_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["model_used"] == "llama3.2"
        assert data["items"][0]["user_story_id"] == str(story_id)
        assert data["page"] == 1

    async def test_list_extractions_empty(self, authed_client, seed_workspace):
        """GET filtered by a seeded story that has no extractions returns empty.

        The contract is "a user with access but no rows sees an empty page": the
        story must exist and the caller must be a member, otherwise the route
        answers 404 (story not found) or 403 (not a member) instead of an empty
        result.
        """
        story_id = (await seed_workspace()).story_id
        response = await authed_client.get(f"/api/v1/extractions/?user_story_id={story_id}")
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_all_extractions_without_filter(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """GET without user_story_id returns all extractions in the user's workspaces.

        This is the "no filter" branch: it reads the caller's memberships
        (``member_repo.list_by_user``) and then, in **one** statement, the extractions joined
        to their story and project across those workspaces. Both halves are needed — a
        membership with no extractions returns 0, and an extraction whose story is not in one
        of those workspaces is dropped by the join. The fold is asserted in
        ``test_unfiltered_list_queries.py``; here it is only the setup for the filtering.
        """
        seeded = await seed_workspace(stories=3)
        repo = SQLAlchemyExtractionRepository(db_session)
        for index, story_id in enumerate(seeded.story_ids):
            await repo.save(
                Extraction(
                    user_story_id=story_id,
                    model_used="test",
                    raw_response=f"summary: Task {index}",
                )
            )

        response = await authed_client.get("/api/v1/extractions/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3


class TestListExtractionsPagination:
    """GET /api/v1/extractions/ with paging params — every authorization branch.

    Each branch must report ``total`` as the full count of matching extractions,
    not the page size, and a page past the end must return 0 items with the
    real total. Extractions are saved through the repository with explicit
    ``created_at`` values so assertions pin the SQL ordering rule rather than
    wall-clock insertion order.
    """

    async def _seed_extractions(self, db_session: AsyncSession, seed_workspace, count: int):
        """Seed an accessible workspace with ``count`` extractions on one story, one day apart.

        Returns ``(workspace_id, story_id, models)`` where ``models`` is the
        creation order (oldest first), so tests can name rows by model name.
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
        repo = SQLAlchemyExtractionRepository(db_session)
        models = [f"model {day}" for day in range(1, count + 1)]
        for day, model in enumerate(models, start=1):
            await repo.save(
                Extraction(
                    user_story_id=story.id,
                    model_used=model,
                    raw_response="1. summary: s",
                    created_at=datetime(2026, 1, day),
                )
            )
        return seeded.workspace_id, story.id, models

    async def test_no_filter_returns_the_full_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?page=1&size=2 with no filter returns 2 of 3 extractions and total 3."""
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
        extraction_repo = SQLAlchemyExtractionRepository(db_session)
        await extraction_repo.save(
            Extraction(user_story_id=story_a.id, model_used="model 1", raw_response="r")
        )
        await extraction_repo.save(
            Extraction(user_story_id=story_a.id, model_used="model 2", raw_response="r")
        )
        await extraction_repo.save(
            Extraction(user_story_id=story_b.id, model_used="model 3", raw_response="r")
        )

        response = await authed_client.get("/api/v1/extractions/?page=1&size=2")

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
        still render '3 extractions' while showing no rows.
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
        extraction_repo = SQLAlchemyExtractionRepository(db_session)
        await extraction_repo.save(
            Extraction(user_story_id=story_a.id, model_used="model 1", raw_response="r")
        )
        await extraction_repo.save(
            Extraction(user_story_id=story_a.id, model_used="model 2", raw_response="r")
        )
        await extraction_repo.save(
            Extraction(user_story_id=story_b.id, model_used="model 3", raw_response="r")
        )

        response = await authed_client.get("/api/v1/extractions/?page=9&size=2")

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3

    async def test_workspace_filter_returns_the_full_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?workspace_id=&page=1&size=2 returns 2 of 3 extractions and total 3."""
        ws_id, _story_id, _models = await self._seed_extractions(db_session, seed_workspace, 3)

        response = await authed_client.get(
            f"/api/v1/extractions/?workspace_id={ws_id}&page=1&size=2"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

    async def test_workspace_filter_past_the_end_returns_no_items_and_the_real_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?workspace_id=&page=9&size=2 returns 0 items but total 3."""
        ws_id, _story_id, _models = await self._seed_extractions(db_session, seed_workspace, 3)

        response = await authed_client.get(
            f"/api/v1/extractions/?workspace_id={ws_id}&page=9&size=2"
        )

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
        ws_id, _story_id, models = await self._seed_extractions(db_session, seed_workspace, 3)

        response = await authed_client.get(f"/api/v1/extractions/?workspace_id={ws_id}")

        assert response.status_code == 200
        returned = [item["model_used"] for item in response.json()["items"]]
        assert returned == list(reversed(models))

    async def test_story_filter_returns_the_full_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?user_story_id=&page=1&size=2 returns 2 of 3 extractions and total 3."""
        _ws_id, story_id, _models = await self._seed_extractions(db_session, seed_workspace, 3)

        response = await authed_client.get(
            f"/api/v1/extractions/?user_story_id={story_id}&page=1&size=2"
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["items"]) == 2
        assert data["total"] == 3

    async def test_story_filter_past_the_end_returns_no_items_and_the_real_total(
        self, authed_client, db_session: AsyncSession, seed_workspace
    ):
        """?user_story_id=&page=9&size=2 returns 0 items but total 3."""
        _ws_id, story_id, _models = await self._seed_extractions(db_session, seed_workspace, 3)

        response = await authed_client.get(
            f"/api/v1/extractions/?user_story_id={story_id}&page=9&size=2"
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 3


class TestGetExtraction:
    """GET /api/v1/extractions/{extraction_id}"""

    async def test_get_extraction(self, authed_client, db_session: AsyncSession, seed_workspace):
        """Save an extraction for a seeded story, then GET by id."""
        story_id = (await seed_workspace()).story_id
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="mistral",
            raw_response="1. summary: Task A\ndescription: Desc A",
            confidence_score=0.92,
            prompt_config={"temperature": 0.1},
        )
        saved = await repo.save(extraction)

        response = await authed_client.get(f"/api/v1/extractions/{saved.id}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(saved.id)
        assert data["user_story_id"] == str(story_id)
        assert data["model_used"] == "mistral"
        assert data["confidence_score"] == 0.92
        assert data["prompt_config"] == {"temperature": 0.1}
        assert data["raw_response"] == "1. summary: Task A\ndescription: Desc A"
        assert "created_at" in data

    async def test_get_extraction_not_found(self, authed_client):
        """GET with a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await authed_client.get(f"/api/v1/extractions/{fake_id}")
        assert response.status_code == 404
        data = response.json()
        assert data["type"] == "entity_not_found"
        assert "detail" in data
