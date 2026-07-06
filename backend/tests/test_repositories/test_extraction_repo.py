"""Tests for SQLAlchemyExtractionRepository."""

from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import Extraction
from storico.infrastructure.database.repositories import SQLAlchemyExtractionRepository


@pytest.fixture
def story_id() -> UUID:
    return uuid4()


@pytest.mark.asyncio
async def test_save_with_nullable_fields(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """Save an extraction with nullable confidence_score and prompt_config."""
    repo = SQLAlchemyExtractionRepository(db_session)
    extraction = Extraction(
        user_story_id=story_id,
        model_used="llama3.2",
        raw_response="1. summary: Task one\ndescription: Do something",
        prompt_config={"temperature": 0.1, "max_tokens": 2048},
        confidence_score=0.85,
    )

    saved = await repo.save(extraction)
    assert saved == extraction

    found = await repo.find_by_id(extraction.id)
    assert found is not None
    assert found.model_used == "llama3.2"
    assert found.prompt_config == {"temperature": 0.1, "max_tokens": 2048}
    assert found.confidence_score == 0.85
    assert found.raw_response.startswith("1. summary")


@pytest.mark.asyncio
async def test_save_with_null_fields(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """Save an extraction without optional fields (prompt_config, confidence_score)."""
    repo = SQLAlchemyExtractionRepository(db_session)
    extraction = Extraction(
        user_story_id=story_id,
        model_used="mistral",
        raw_response="1. summary: Task one\ndescription: Do something",
    )

    await repo.save(extraction)
    found = await repo.find_by_id(extraction.id)
    assert found is not None
    assert found.prompt_config is None
    assert found.confidence_score is None


@pytest.mark.asyncio
async def test_find_by_id_returns_none(db_session: AsyncSession) -> None:
    """find_by_id returns None for a non-existent extraction."""
    repo = SQLAlchemyExtractionRepository(db_session)
    result = await repo.find_by_id(uuid4())
    assert result is None


@pytest.mark.asyncio
async def test_list_by_story(db_session: AsyncSession, story_id: UUID) -> None:
    """list_by_story returns only extractions for the given user story."""
    repo = SQLAlchemyExtractionRepository(db_session)
    other_id = uuid4()

    e1 = Extraction(user_story_id=story_id, model_used="m1", raw_response="r1")
    e2 = Extraction(user_story_id=story_id, model_used="m2", raw_response="r2")
    e3 = Extraction(user_story_id=other_id, model_used="m3", raw_response="r3")
    await repo.save(e1)
    await repo.save(e2)
    await repo.save(e3)

    story_extractions = await repo.list_by_story(story_id)
    assert len(story_extractions) == 2
    models = {e.model_used for e in story_extractions}
    assert models == {"m1", "m2"}


@pytest.mark.asyncio
async def test_list_by_story_empty(db_session: AsyncSession) -> None:
    """list_by_story returns empty list when no extractions match."""
    repo = SQLAlchemyExtractionRepository(db_session)
    result = await repo.list_by_story(uuid4())
    assert result == []


@pytest.mark.asyncio
async def test_list_all(db_session: AsyncSession, story_id: UUID) -> None:
    """list returns all extractions."""
    repo = SQLAlchemyExtractionRepository(db_session)
    e1 = Extraction(user_story_id=story_id, model_used="m1", raw_response="r1")
    e2 = Extraction(user_story_id=story_id, model_used="m2", raw_response="r2")
    await repo.save(e1)
    await repo.save(e2)

    extractions = await repo.list()
    assert len(extractions) == 2
