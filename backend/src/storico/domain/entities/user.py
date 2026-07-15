from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class User:
    email: str
    name: str
    id: UUID = field(default_factory=uuid4)
    avatar_url: str = ""
    is_first_login: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
