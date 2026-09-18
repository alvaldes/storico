"""Custom provider API schemas — the workspace's registry of provider names.

A custom provider is a name a workspace registered for an LLM endpoint that is
not one of the four first-class providers. The name is free-form text, stored
verbatim: it only has to fit the workspace config's ``String(50)`` column, so it
is trimmed and capped here and left otherwise alone.

Nothing downstream needs a slug. ``_build_llm_port`` compares a name against the
four built-in names by exact equality and sends every other name to the
OpenAI-compatible adapter, so casing, spaces and accents route exactly like
``deepseek`` does. Two names are refused anyway, because they already mean
something: a built-in provider's name in any casing, and the provider select's
control value — both handled by the providers API route, not here.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

# The four first-class providers have dedicated adapter branches and
# model-discovery endpoints, so registering one of them as "custom" would only
# produce a duplicate entry in the select. They are reserved **case-insensitively**
# (``OpenAI`` is refused like ``openai``): the guard has to survive the removal of
# the old lower-casing normalization, and a custom entry whose name differs from a
# built-in only by casing would confuse the select without changing the routing.
# Mirrored by ``KNOWN_PROVIDERS`` in ``frontend/src/lib/llm-providers.ts``; the
# frozen copy in migration 0021 is deliberately separate, because a migration must
# not follow a constant that can still change.
KNOWN_PROVIDERS: tuple[str, ...] = ("ollama", "openai", "anthropic", "gemini")

# The value the provider ``<Select>`` in ``LLMConfigEditor.tsx`` uses for its
# "Add custom provider…" option. It travels through the select's value, so a
# provider registered under it would take the control's slot and be unselectable.
# Mirrored from ``ADD_CUSTOM_PROVIDER_VALUE`` in ``frontend/src/lib/llm-providers.ts``.
SELECT_CONTROL_VALUE = "__add_custom_provider__"

# Matches the ``String(50)`` bound on ``workspace_llm_configs.provider``: a name
# the registry accepts must also fit the column the selection is stored in. The
# cap applies to the name that is stored, so it is measured after trimming — a
# ``Field(max_length=...)`` on the raw value would refuse a padded name that fits.
NAME_MAX_LENGTH = 50

NAME_RULE_MESSAGE = (
    f"Use a provider name of 1 to {NAME_MAX_LENGTH} characters. Surrounding whitespace is ignored."
)


def normalize_provider_name(raw: str) -> str:
    """Trim a submitted provider name, and change nothing else.

    Casing is kept on purpose: the name is the user's label for the provider and
    is stored as typed. ``Groq`` and ``groq`` are therefore two rows in the same
    workspace, which is what the user chose, and what the case-sensitive
    ``UNIQUE (workspace_id, name)`` constraint already models.
    """
    return raw.strip()


class CustomProviderRequest(BaseModel):
    """Request body for creating or renaming a custom provider."""

    model_config = ConfigDict(extra="forbid")

    name: str

    @field_validator("name")
    @classmethod
    def _trim_and_validate(cls, value: str) -> str:
        normalized = normalize_provider_name(value)
        if not normalized or len(normalized) > NAME_MAX_LENGTH:
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
