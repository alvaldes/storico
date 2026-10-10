"""TrelloExport domain entity — one persisted export job, pollable like an extraction.

The job is the member's answer: ``POST`` creates it pending, the background run
moves it to ``completed`` (with the board identity) or ``failed`` (with the
error code and, when the board got built, its URL), and ``GET`` reads it. It is
persisted rather than held in process memory because a restart must not lose
the answer someone is polling for — the extraction precedent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from uuid_utils.compat import uuid7


class TrelloExportStatus(StrEnum):
    """Lifecycle of one export job.

    ``running`` exists because an export spends minutes inside Trello's rate
    window — a client polling between ``pending`` and the terminal states
    deserves to see that the work is underway, which the extraction flow
    reports through the story's ``EXTRACTING`` status instead.
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrelloExportScope(StrEnum):
    """What the export covers — exactly one of the three, never two (D1)."""

    WORKSPACE = "workspace"
    PROJECT = "project"
    STORY = "story"


@dataclass(frozen=True, slots=True)
class TrelloExport:
    """One export request and everything a poll needs to answer.

    ``project_id`` and ``user_story_id`` are recorded as values, deliberately
    without foreign keys: deleting the story mid-run must not destroy — via a
    cascading delete — the job row the member is polling for. The job outlives
    its target precisely so it can report what happened to it.
    """

    workspace_id: UUID
    scope: TrelloExportScope = field(default=TrelloExportScope.WORKSPACE)
    project_id: UUID | None = None
    user_story_id: UUID | None = None
    status: TrelloExportStatus = field(default=TrelloExportStatus.PENDING)
    error_code: str | None = None
    board_id: str | None = None
    board_url: str | None = None
    cards_created: int | None = None
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    # Non-null exactly when the status is terminal. Stamped by the terminal-path
    # call sites rather than derived, for the same reason the extraction entity
    # gives: the repository rebuilds an entity from every row it loads, and a
    # derived timestamp would hand a historical job a completion time that
    # changes on each read.
    completed_at: datetime | None = None
