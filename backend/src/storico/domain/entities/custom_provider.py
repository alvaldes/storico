"""CustomProvider domain entity — a workspace-scoped provider name.

A custom provider is a name a workspace registered for an LLM endpoint that is
not one of the four first-class providers (``ollama``, ``openai``,
``anthropic``, ``gemini``). The name is what :func:`_build_llm_port` matches on,
so it is the provider slug and nothing else: model, API key and base URL stay on
the workspace LLM config row.

Rows are scoped by ``workspace_id`` so two workspaces can register the same name
without sharing, listing, or overwriting each other's entry.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7


@dataclass(frozen=True, slots=True)
class CustomProvider:
    """A provider name registered by a single workspace."""

    workspace_id: UUID
    name: str
    id: UUID = field(default_factory=uuid7)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
