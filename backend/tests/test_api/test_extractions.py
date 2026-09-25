"""Integration tests for the Extraction read-only API endpoints.

Every case here must seed the full ``workspace → project → story`` chain plus
the caller's membership: the routes resolve an extraction's workspace by
walking that chain and then require membership in it.
"""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import Extraction
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
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
