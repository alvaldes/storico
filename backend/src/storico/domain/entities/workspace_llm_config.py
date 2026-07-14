"""WorkspaceLLMConfig domain entity — LLM configuration for a workspace.

Each workspace can have its own LLM settings, including the provider,
model, temperature, max tokens, and base URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class WorkspaceLLMConfig:
    """LLM configuration scoped to a workspace.

    Allows each workspace to independently configure which LLM provider
    and model to use for task extraction.
    """

    workspace_id: UUID
    provider: str = "ollama"
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    base_url: str | None = None
    id: UUID = field(default_factory=uuid4)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
