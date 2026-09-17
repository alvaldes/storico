"""Custom provider API schemas — the workspace's registry of provider names.

A custom provider is a name a workspace registered for an LLM endpoint that is
not one of the four first-class providers. The name reaches the adapter selector
and the workspace config's ``String(50)`` column, so it is validated as a slug
here rather than stored as free text.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

# The four first-class providers have dedicated adapter branches and
# model-discovery endpoints, so registering one of them as "custom" would only
# produce a duplicate entry in the select. Mirrored by ``KNOWN_PROVIDERS`` in
# ``frontend/src/components/react/LLMConfigEditor.tsx``; the frozen copy in
# migration 0021 is deliberately separate, because a migration must not follow a
# constant that can still change.
KNOWN_PROVIDERS: tuple[str, ...] = ("ollama", "openai", "anthropic", "gemini")

# Matches the ``String(50)`` bound on ``workspace_llm_configs.provider``: a name
# the registry accepts must also fit the column the selection is stored in.
NAME_MAX_LENGTH = 50

# Lowercase slug, starting with a letter or digit. Everything the adapter selector
# can compare unambiguously, and nothing that needs quoting or normalising later.
NAME_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,49}$")

NAME_RULE_MESSAGE = (
    "Use a provider name of up to 50 characters: lowercase letters, digits, "
    "dots, dashes or underscores, starting with a letter or digit."
)


def normalize_provider_name(raw: str) -> str:
    """Trim and lowercase a submitted provider name.

    Normalising on the way in is what keeps ``Groq`` and ``groq`` from becoming
    two rows in the same workspace.
    """
    return raw.strip().lower()


class CustomProviderRequest(BaseModel):
    """Request body for creating or renaming a custom provider."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(max_length=NAME_MAX_LENGTH)

    @field_validator("name")
    @classmethod
    def _normalize_and_validate(cls, value: str) -> str:
        normalized = normalize_provider_name(value)
        if not NAME_PATTERN.match(normalized):
            raise ValueError(NAME_RULE_MESSAGE)
        return normalized


class CustomProviderResponse(BaseModel):
    """Response body representing one registered custom provider."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    workspace_id: UUID
    name: str
    created_at: datetime
    updated_at: datetime
