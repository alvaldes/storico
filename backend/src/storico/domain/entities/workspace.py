"""Workspace domain entity — represents a collaborative workspace.

A workspace groups projects, user stories, and tasks under a shared
context, with members assigned to specific roles.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


@dataclass(frozen=True, slots=True)
class Workspace:
    """A collaborative workspace that groups projects and members."""

    name: str
    slug: str
    owner_id: UUID
    icon: str | None = None
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True, slots=True)
class WorkspaceWithRoleAndCount:
    """Result of listing workspaces with the user's role and total member count."""

    workspace: Workspace
    role: str
    member_count: int
