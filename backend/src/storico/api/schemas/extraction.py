"""Extraction Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from storico.domain.entities.extraction import ExtractionStatus
from storico.domain.entities.user_story import UserStoryStatus
from storico.domain.entities.task import TaskStatus


class UserStorySchema(BaseModel):
    """User story info included in extraction response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    status: UserStoryStatus
    workspace_id: UUID


class TaskSchema(BaseModel):
    """A single task returned in an extraction response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    summary: str
    description: str
    status: TaskStatus
    order_index: int


class ExtractionResponse(BaseModel):
    """Response body representing an LLM extraction result."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_story_id: UUID
    model_used: str
    status: ExtractionStatus
    user_story_status: UserStoryStatus
    error_info: str | None = None
    prompt_config: dict | None = None
    raw_response: str
    confidence_score: float | None = None
    created_at: datetime
    completed_at: datetime | None = None
    tasks: list[TaskSchema] = []


class ExtractRequest(BaseModel):
    """Request body for task extraction from a user story."""

    user_story_id: UUID
    model: str | None = None
    temperature: float | None = None
    run_validation: bool = False


class ExtractResponse(BaseModel):
    """Response body for a task extraction request."""

    extraction_id: UUID
    status: ExtractionStatus
    user_story_id: UUID
    message: str