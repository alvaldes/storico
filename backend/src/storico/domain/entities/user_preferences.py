"""UserPreferences — per-user application preferences stored as JSON."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID


@dataclass(frozen=True, slots=True)
class UserPreferences:
    """Serializable user preferences for the Storico application.

    The ``preferences`` dict maps directly to the frontend ``AppSettings``
    JSON structure and is stored as a JSONB column in PostgreSQL.
    """

    user_id: UUID
    preferences: dict = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
