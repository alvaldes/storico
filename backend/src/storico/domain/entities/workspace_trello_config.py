"""WorkspaceTrelloConfig domain entity — Trello credentials for a workspace.

Each workspace can store the Trello API key and token an admin pastes, which the
Trello export uses to create boards on the workspace's behalf. The credentials are
encrypted at rest; this entity always holds plaintext, because the repository is the
only layer that sees ciphertext.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


@dataclass(frozen=True, slots=True)
class WorkspaceTrelloConfig:
    """Trello credentials scoped to a workspace.

    One row per workspace (``workspace_id`` is unique): the pair an admin stores in
    the workspace settings, encrypted at rest by the repository that persists it.
    """

    workspace_id: UUID
    api_key: str | None = None
    token: str | None = None
    id: UUID = field(default_factory=uuid7)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
