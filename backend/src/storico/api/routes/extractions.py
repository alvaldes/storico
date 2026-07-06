"""Extraction read-only API routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends

from storico.api.dependencies import get_repository
from storico.api.schemas.common import PaginatedResponse, PaginationParams
from storico.api.schemas.extraction import ExtractionResponse
from storico.domain.entities import EntityNotFound
from storico.infrastructure.database.repositories import SQLAlchemyExtractionRepository

router = APIRouter(prefix="/api/v1/extractions", tags=["extractions"])

ExtractionRepoDep = Annotated[
    SQLAlchemyExtractionRepository,
    Depends(get_repository(SQLAlchemyExtractionRepository)),
]


@router.get("/")
async def list_extractions(
    params: Annotated[PaginationParams, Depends()],
    repo: ExtractionRepoDep,
    user_story_id: UUID | None = None,
) -> PaginatedResponse[ExtractionResponse]:
    """List extractions for a user story with pagination."""
    all_extractions = (
        await repo.list_by_story(user_story_id)
        if user_story_id is not None
        else await repo.list()
    )
    total = len(all_extractions)
    start = (params.page - 1) * params.size
    items = [
        ExtractionResponse(
            id=e.id,
            user_story_id=e.user_story_id,
            model_used=e.model_used,
            status=e.status,
            error_info=e.error_info,
            prompt_config=e.prompt_config,
            raw_response=e.raw_response,
            confidence_score=e.confidence_score,
            created_at=e.created_at,
        )
        for e in all_extractions[start : start + params.size]
    ]
    return PaginatedResponse(
        items=items,
        total=total,
        page=params.page,
        size=params.size,
    )


@router.get("/{extraction_id}")
async def get_extraction(
    extraction_id: UUID,
    repo: ExtractionRepoDep,
) -> ExtractionResponse:
    """Get an extraction by its ID."""
    extraction = await repo.find_by_id(extraction_id)
    if extraction is None:
        raise EntityNotFound("Extraction", str(extraction_id))
    return ExtractionResponse(
        id=extraction.id,
        user_story_id=extraction.user_story_id,
        model_used=extraction.model_used,
        status=extraction.status,
        error_info=extraction.error_info,
        prompt_config=extraction.prompt_config,
        raw_response=extraction.raw_response,
        confidence_score=extraction.confidence_score,
        created_at=extraction.created_at,
    )
