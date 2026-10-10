"""Trello export Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class TrelloExportCreateRequest(BaseModel):
    """Request body for triggering a Trello export — the optional scope targets.

    Both omitted exports the whole workspace; each one present narrows the
    export to that project or story; both present is refused with 422
    ``REQUEST_VALIDATION_FAILED`` — the Kanban cascade's never-two rule, applied
    by ``resolve_export_scope`` (``domain/services/export_scope.py``).
    """

    model_config = ConfigDict(extra="forbid")

    project_id: UUID | None = None
    user_story_id: UUID | None = None


class TrelloExportResponse(BaseModel):
    """The persisted export job — everything a polling client needs.

    ``board_url`` is the board link the moment the board exists, including on a
    failed job whose error carried a ``board_ref``: a half-built board must stay
    reachable. ``error_code`` is set only on failure, with a value from the
    backend's error-code registry.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    scope: str
    project_id: UUID | None = None
    user_story_id: UUID | None = None
    status: str
    error_code: str | None = None
    board_id: str | None = None
    board_url: str | None = None
    cards_created: int | None = None
    created_at: datetime
    completed_at: datetime | None = None
