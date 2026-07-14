"""Workspace domain entity — represents a collaborative workspace.

A workspace groups projects, user stories, and tasks under a shared
context, with members assigned to specific roles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class Workspace:
    """A collaborative workspace that groups projects and members."""

    name: str
    slug: str
    owner_id: UUID
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
