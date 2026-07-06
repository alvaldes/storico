"""Integration tests for the Extraction read-only API endpoints."""

from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import Extraction
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
)


class TestListExtractions:
    """GET /api/v1/extractions/"""

    async def test_list_extractions_by_story(
        self, async_client, db_session: AsyncSession
    ):
        """Save an extraction via the repository, then GET by user_story_id."""
        story_id = uuid4()
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="llama3.2",
            raw_response="1. summary: Task one\ndescription: Do it",
        )
        await repo.save(extraction)

        response = await async_client.get(
            f"/api/v1/extractions/?user_story_id={story_id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["model_used"] == "llama3.2"
        assert data["items"][0]["user_story_id"] == str(story_id)
        assert data["page"] == 1

    async def test_list_extractions_empty(self, async_client):
        """GET with a story_id that has no extractions returns empty."""
        fake_story = str(uuid4())
        response = await async_client.get(
            f"/api/v1/extractions/?user_story_id={fake_story}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0

    async def test_list_all_extractions_without_filter(
        self, async_client, db_session: AsyncSession
    ):
        """GET without user_story_id returns all extractions."""
        repo = SQLAlchemyExtractionRepository(db_session)
        for i in range(3):
            await repo.save(
                Extraction(
                    user_story_id=uuid4(),
                    model_used="test",
                    raw_response=f"summary: Task {i}",
                )
            )

        response = await async_client.get("/api/v1/extractions/")
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3


class TestGetExtraction:
    """GET /api/v1/extractions/{extraction_id}"""

    async def test_get_extraction(
        self, async_client, db_session: AsyncSession
    ):
        """Save an extraction via the repository, then GET by id."""
        story_id = uuid4()
        repo = SQLAlchemyExtractionRepository(db_session)

        extraction = Extraction(
            user_story_id=story_id,
            model_used="mistral",
            raw_response="1. summary: Task A\ndescription: Desc A",
            confidence_score=0.92,
            prompt_config={"temperature": 0.1},
        )
        saved = await repo.save(extraction)

        response = await async_client.get(
            f"/api/v1/extractions/{saved.id}"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == str(saved.id)
        assert data["user_story_id"] == str(story_id)
        assert data["model_used"] == "mistral"
        assert data["confidence_score"] == 0.92
        assert data["prompt_config"] == {"temperature": 0.1}
        assert data["raw_response"] == "1. summary: Task A\ndescription: Desc A"
        assert "created_at" in data

    async def test_get_extraction_not_found(self, async_client):
        """GET with a non-existent UUID returns 404."""
        fake_id = str(uuid4())
        response = await async_client.get(f"/api/v1/extractions/{fake_id}")
        assert response.status_code == 404
        data = response.json()
        assert data["type"] == "entity_not_found"
        assert "detail" in data
