"""Extraction API routes — real LLM-based task extraction."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from storico.api.dependencies import (
    get_current_user,
    get_extract_use_case,
    get_repository,
)
from storico.api.schemas.extraction import (
    ExtractRequest,
    ExtractResponse,
    ExtractionResponse,
    TaskSchema,
)
from storico.application.extraction import ExtractFromStoryUseCase
from storico.domain.entities import EntityNotFound, User
from storico.infrastructure.database.repositories import (
    SQLAlchemyExtractionRepository,
    SQLAlchemyTaskRepository,
)

router = APIRouter(prefix="/api/v1/extract", tags=["extract"])

ExtractionRepoDep = Annotated[
    SQLAlchemyExtractionRepository,
    Depends(get_repository(SQLAlchemyExtractionRepository)),
]

TaskRepoDep = Annotated[
    SQLAlchemyTaskRepository,
    Depends(get_repository(SQLAlchemyTaskRepository)),
]


@router.post("/", status_code=status.HTTP_201_CREATED)
async def extract_tasks(
    body: ExtractRequest,
    use_case: ExtractFromStoryUseCase = Depends(get_extract_use_case),
    extraction_repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    task_repo: TaskRepoDep = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> ExtractResponse:
    """Extract tasks from a user story using an LLM.

    The extraction runs synchronously. On success, the response contains
    the generated tasks. On failure, ``status`` will be ``"failed"`` with
    an ``error_info`` message.
    """
    # 1. Run extraction
    result = await use_case.execute(
        story_id=body.user_story_id,
        model=body.model,
        temperature=body.temperature,
        validate=body.run_validation,
    )

    # 2. Load tasks if extraction completed
    tasks: list[TaskSchema] = []
    if result["status"] == "completed" and extraction_repo is not None:
        extraction = await extraction_repo.find_by_id(result["extraction_id"])
        if extraction is not None:
            persisted_tasks = await task_repo.list_by_story(extraction.user_story_id)
            tasks = [
                TaskSchema(
                    title=t.title,
                    description=t.description,
                    labels=t.labels,
                    dependencies=t.dependencies,
                )
                for t in persisted_tasks
            ]

    return ExtractResponse(
        extraction_id=result["extraction_id"],
        status=result["status"],
        error_info=result.get("error_info"),
        tasks=tasks,
        model_used=result["model_used"],
        confidence_score=result.get("confidence_score"),
    )


@router.get("/status/{extraction_id}")
async def extraction_status(
    extraction_id: UUID,
    repo: ExtractionRepoDep = None,  # type: ignore[assignment]
    current_user: User = Depends(get_current_user),  # noqa: ARG001
) -> ExtractionResponse:
    """Get the status and details of an extraction by its ID."""
    extraction = await repo.find_by_id(extraction_id)
    if extraction is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Extraction '{extraction_id}' not found",
        )
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
