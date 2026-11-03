"""WorkspaceLLMConfig domain entity — LLM configuration for a workspace.

Each workspace can have its own LLM settings, including the provider,
model, temperature, max tokens, and base URL.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


@dataclass(frozen=True, slots=True)
class WorkspaceLLMConfig:
    """LLM configuration scoped to a workspace.

    Allows each workspace to independently configure which LLM provider
    and model to use for task extraction.
    """

    workspace_id: UUID
    provider: str = "ollama"
    model: str | None = None
    # The model the workspace's LLM-as-a-Judge runs with (D7), plus the judge's own
    # connection (D9/S10): provider, credential and endpoint. Each judge field falls
    # back independently to the extraction value, so any subset is a legitimate
    # configuration. When the resolved judge provider differs from the extraction
    # provider, the extraction credential and endpoint are never reused — a key issued
    # for one provider must never be sent to another.
    judge_model: str | None = None
    judge_provider: str | None = None
    judge_api_key: str | None = None
    judge_base_url: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    base_url: str | None = None
    api_key: str | None = None
    id: UUID = field(default_factory=uuid7)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
