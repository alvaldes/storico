"""Extraction Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ExtractionResponse(BaseModel):
    """Response body representing an LLM extraction result."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_story_id: UUID
    model_used: str
    status: str = "pending"
    error_info: str | None = None
    prompt_config: dict | None = None
    raw_response: str
    confidence_score: float | None = None
    created_at: datetime


class ExtractRequest(BaseModel):
    """Request body for task extraction from a user story."""

    user_story_id: UUID
    model: str | None = None
    temperature: float | None = None
    run_validation: bool = False


class TaskSchema(BaseModel):
    """A single task returned in an extraction response."""

    title: str
    description: str
    labels: list[str] = []
    dependencies: list[str] = []


class ExtractResponse(BaseModel):
    """Response body for a task extraction request."""

    extraction_id: UUID
    status: str
    error_info: str | None = None
    tasks: list[TaskSchema] = []
    model_used: str
    confidence_score: float | None = None
