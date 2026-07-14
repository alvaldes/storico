"""WorkspaceMember domain entity — represents a member of a workspace.

A workspace member has a specific role (admin or member) that governs
what actions they can perform within the workspace.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum, auto
from uuid import UUID, uuid4


class WorkspaceRole(StrEnum):
    """Defines the role a user has within a workspace."""

    ADMIN = auto()
    MEMBER = auto()


@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    """A user that belongs to a workspace with a specific role."""

    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
