"""Tests for SQLAlchemyExtractionRepository."""

from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities import EntityNotFound, Extraction
from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.infrastructure.database.repositories import SQLAlchemyExtractionRepository


@pytest.fixture
def story_id() -> UUID:
    return uuid4()


@pytest.mark.asyncio
async def test_save_with_nullable_fields(db_session: AsyncSession, story_id: UUID) -> None:
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
async def test_save_with_null_fields(db_session: AsyncSession, story_id: UUID) -> None:
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


@pytest.mark.asyncio
async def test_a_completed_extraction_round_trips_its_end_time(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """``completed_at`` is stored and read back, which is the whole point of the column."""
    repo = SQLAlchemyExtractionRepository(db_session)
    finished = datetime(2026, 9, 19, 12, 30, tzinfo=UTC)
    extraction = Extraction(
        user_story_id=story_id,
        model_used="llama3.2",
        raw_response="r",
        status=ExtractionStatus.COMPLETED,
        user_story_status=UserStoryStatus.EXTRACTED,
        completed_at=finished,
    )

    await repo.save(extraction)

    found = await repo.find_by_id(extraction.id)
    assert found is not None
    # The test database is SQLite, which drops ``tzinfo`` on a ``DateTime(timezone=True)`` column,
    # so the read-back value is naive while the written one was aware — the same note as in
    # ``test_custom_provider_repo.py``. The instant is what the column carries; Postgres, which is
    # what production runs, keeps the offset.
    assert found.completed_at is not None
    assert found.completed_at.replace(tzinfo=None) == finished.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_a_pending_extraction_has_no_end_time(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """The invariant is "non-null exactly when terminal", not "not null"."""
    repo = SQLAlchemyExtractionRepository(db_session)
    extraction = Extraction(user_story_id=story_id, model_used="m", raw_response="r")

    await repo.save(extraction)

    found = await repo.find_by_id(extraction.id)
    assert found is not None
    assert found.status is ExtractionStatus.PENDING
    assert found.completed_at is None


@pytest.mark.asyncio
async def test_reading_a_terminal_row_invents_no_end_time(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """A row that finished before the column existed keeps its null, forever.

    This is the decision the design turns on. Deriving ``completed_at`` inside the entity would
    have been tidier at the write sites and wrong here: the repository rebuilds an entity from
    every row it loads, so a derived value would hand this historical row a fresh timestamp on
    each read — a completion time that changes every time it is fetched, and the explicit
    decision not to backfill silently undone.
    """
    repo = SQLAlchemyExtractionRepository(db_session)
    historical = Extraction(
        user_story_id=story_id,
        model_used="m",
        raw_response="r",
        status=ExtractionStatus.COMPLETED,
        user_story_status=UserStoryStatus.EXTRACTED,
        completed_at=None,
    )
    await repo.save(historical)

    first = await repo.find_by_id(historical.id)
    second = await repo.find_by_id(historical.id)

    assert first is not None and second is not None
    assert first.completed_at is None
    assert second.completed_at is None


@pytest.mark.asyncio
async def test_delete_removes_a_row_and_reports_an_absent_one(
    db_session: AsyncSession, story_id: UUID
) -> None:
    """The delete path answers both questions: it removes, and it says when there is nothing."""
    repo = SQLAlchemyExtractionRepository(db_session)
    extraction = Extraction(user_story_id=story_id, model_used="m", raw_response="r")
    await repo.save(extraction)

    await repo.delete(extraction.id)
    assert await repo.find_by_id(extraction.id) is None

    with pytest.raises(EntityNotFound):
        await repo.delete(extraction.id)
