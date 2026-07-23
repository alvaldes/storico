"""UserAccount — linked OAuth provider account belonging to a User."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


@dataclass(frozen=True, slots=True)
class UserAccount:
    """A linked OAuth provider account associated with a user."""

    user_id: UUID
    provider: str
    provider_id: str
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
