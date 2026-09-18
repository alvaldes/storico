"""Pydantic schemas for user preferences and LLM test endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AliasGenerator, BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class CamelCaseModel(BaseModel):
    """Base model that accepts camelCase from API and uses snake_case internally."""

    model_config = ConfigDict(
        alias_generator=AliasGenerator(
            serialization_alias=to_camel,
            validation_alias=to_camel,
        ),
        populate_by_name=True,
    )


class ExportSettings(CamelCaseModel):
    """Default export format preferences."""

    model_config = ConfigDict(extra="forbid")

    default_format: Literal["trello", "json", "markdown"] = "json"


#: Keys a previous schema version stored and this one deliberately does not declare.
#:
#: The preferences route drops exactly these on read, so a document written before the
#: removal still validates. Revision ``0022`` removes them from storage; this is the shim for
#: a row it did not reach — a restore, or a client still on the old contract. It is
#: deliberately narrow: ``extra="forbid"`` stays, so a genuinely unexpected field still fails
#: loudly instead of being swallowed.
REMOVED_PREFERENCE_KEYS: frozenset[str] = frozenset({"llm"})


class AppSettings(CamelCaseModel):
    """Top-level user application settings — mirrors frontend AppSettings.

    Deliberately holds no LLM configuration. It used to carry an ``llm`` block with a
    ``model``/``api_key``/``base_url`` per provider, which this endpoint round-tripped into
    ``user_preferences.preferences``; nothing ever read it, because the live configuration is
    per *workspace* (``workspace_llm_configs``), and a credential store no code reads is a
    liability rather than a feature. Revision ``0022`` removes the stored key, and
    ``extra="forbid"`` is what keeps it from coming back through this endpoint.
    """

    model_config = ConfigDict(extra="forbid")

    export: ExportSettings = ExportSettings()


class UserPreferencesResponse(CamelCaseModel):
    """Response returned by GET /users/me/settings."""

    preferences: AppSettings
    updated_at: datetime


class UserPreferencesUpdate(CamelCaseModel):
    """Request body for PUT /users/me/settings."""

    model_config = ConfigDict(extra="forbid")

    preferences: AppSettings


class LLMTestRequest(CamelCaseModel):
    """Request body for POST /llm/test."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama", "openai", "anthropic", "gemini"]
    base_url: str | None = None
    api_key: str | None = None
    model: str = "llama3.2"


class LLMTestResponse(CamelCaseModel):
    """Response returned by POST /llm/test."""

    success: bool
    message: str
    model: str | None = None
    latency_ms: int | None = None


class DeleteAccountResponse(CamelCaseModel):
    """Response returned by DELETE /users/me."""

    message: str = "Account deleted successfully"
