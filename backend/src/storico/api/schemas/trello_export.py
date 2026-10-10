"""Trello export Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from storico.domain.entities.trello_board import TrelloBoardPlan


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


class TrelloBoardCardResponse(BaseModel):
    """One card of the preview's plan — everything resolved already.

    ``labels`` are label names and ``dependency_titles`` are already-resolved
    dependency titles: the same values the adapter turns into Trello objects,
    serialized so the UI can show what would be created.
    """

    title: str
    description: str = ""
    labels: list[str] = []
    dependency_titles: list[str] = []


class TrelloBoardColumnResponse(BaseModel):
    """One board list of the preview's plan, with its cards in order."""

    name: str
    cards: list[TrelloBoardCardResponse] = []


class TrelloBoardPlanResponse(BaseModel):
    """The board plan the trigger would send — decision E4's preview shape.

    The board's name, its lists in Kanban order, and each card with its title,
    description, labels and resolved dependency titles. Serialized from the
    domain's ``TrelloBoardPlan`` via :meth:`from_plan` — the same value the
    adapter receives — so the preview and the export cannot disagree.
    """

    name: str
    columns: list[TrelloBoardColumnResponse] = []

    @classmethod
    def from_plan(cls, plan: TrelloBoardPlan) -> "TrelloBoardPlanResponse":
        """Serialize the domain plan field by field — no re-derivation here."""
        return cls(
            name=plan.name,
            columns=[
                TrelloBoardColumnResponse(
                    name=column.name,
                    cards=[
                        TrelloBoardCardResponse(
                            title=card.title,
                            description=card.description,
                            labels=list(card.labels),
                            dependency_titles=list(card.dependency_titles),
                        )
                        for card in column.cards
                    ],
                )
                for column in plan.columns
            ],
        )


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
