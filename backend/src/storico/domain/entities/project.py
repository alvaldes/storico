from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


@dataclass(frozen=True, slots=True)
class Project:
    name: str
    workspace_id: UUID
    description: str = ""
    icon: str | None = None
    created_by: UUID | None = None
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class ProjectWithCount:
    """Project projected alongside the count of its user stories.

    Returned by repository methods that fold the story count into a single
    query (e.g. ``list_by_workspace_with_counts`` and
    ``find_by_id_with_count``) to avoid N+1 round-trips to the database.

    The domain layer does NOT import SQLAlchemy — this dataclass is a pure
    domain projection. Repositories are responsible for converting the
    raw joined SQLAlchemy rows into instances of this class.
    """

    project: Project
    story_count: int
