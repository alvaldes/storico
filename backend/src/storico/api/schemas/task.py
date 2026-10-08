"""Task Pydantic schemas for Storico API."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from storico.domain.entities.task import TaskStatus


class UpdateTaskRequest(BaseModel):
    """Request body for updating an existing task.

    The D5/D21 field matrix: only ``status``, ``labels`` and ``dependencies``
    are writable. ``title``, ``description`` and ``priority`` are deleted, not
    ignored — ``extra="forbid"`` refuses them with 422 during body validation,
    and ``dependencies`` is only accepted while the task's version is the
    story's current one (the route refuses the write with 409 otherwise).
    """

    model_config = ConfigDict(extra="forbid")

    status: TaskStatus | None = None
    labels: list[str] | None = None
    dependencies: list[str] | None = None


class CreateInvalidationRequest(BaseModel):
    """Request body for the invalidation mark.

    The reason rule is the Pydantic validator, not the database ``CHECK``:
    Python whitespace is wider than ``length(trim(reason)) > 0`` — a
    ``"\t\n"`` reason passes the column and is still blank to a human — so the
    blank shapes are refused here, at body validation, where they answer 422
    ``REQUEST_VALIDATION_FAILED`` and no route or insert is ever reached.
    The 500 bound mirrors the column's ``String(500)`` so an over-long reason
    refuses as a 422 too, never as an ``IntegrityError`` 500.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_must_not_be_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reason must not be blank")
        return value


class InvalidationResponse(BaseModel):
    """One invalidation mark: the mark's fields plus its optional revoke attribution.

    No ``task_id``: the route path is the task, so echoing it back would say
    nothing the caller did not already have.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    reason: str
    marked_by: UUID | None
    marked_at: datetime
    revoked_by: UUID | None
    revoked_at: datetime | None


class StoryInvalidationResponse(InvalidationResponse):
    """One active mark of a story's tasks: the mark plus the task it belongs to.

    ``task_id`` is the one field the per-task read deliberately omits — its
    route path is the task. A story-scoped read answers many tasks, so the id
    is the answer's whole point. Revoked marks are not part of this read; the
    history belongs to the task-scoped read.
    """

    task_id: UUID


class RepetitionMatch(BaseModel):
    """One D16 match: a mark on another version whose normalized title equals the task's.

    No title: the title is the matching *input*, resolved server-side from the
    task id — it is never an output of the read.
    """

    model_config = ConfigDict(from_attributes=True)

    version_number: int
    reason: str
    marked_at: datetime


class RepetitionResponse(BaseModel):
    """The D16 read's answer — a bare list inside an envelope, so a future
    warning field can join without breaking the client."""

    matches: list[RepetitionMatch]


class TaskResponse(BaseModel):
    """Response body representing a task.

    ``extraction_id`` and ``version_number`` are the version chip's data
    (decision D8 of feature ``versioning-visibility``): every construction
    site in the tasks route resolves them, so a board card can say which
    version it belongs to and a ``PUT`` response merged into a moved card
    cannot erase that with a ``null``. Both default to ``None`` so the export
    route (decision D9) keeps its current shape untouched.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_story_id: UUID
    title: str
    description: str
    status: TaskStatus
    priority: str
    labels: list[str]
    dependencies: list[str]
    created_at: datetime
    updated_at: datetime
    extraction_id: UUID | None = None
    version_number: int | None = None
