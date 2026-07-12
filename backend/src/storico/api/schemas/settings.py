"""Pydantic schemas for user preferences and LLM test endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider — shared shape for all providers."""

    model_config = ConfigDict(extra="forbid")

    model: str = "llama3.2"
    temperature: float = 0.1
    max_tokens: int = 2048
    base_url: str | None = None
    api_key: str | None = None


class LLMSettings(BaseModel):
    """LLM provider selection and per-provider configs."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama", "openai", "anthropic"] = "ollama"
    ollama: LLMProviderConfig = LLMProviderConfig(
        model="llama3.2",
        base_url="http://localhost:11434",
    )
    openai: LLMProviderConfig = LLMProviderConfig(
        model="gpt-4o-mini",
        api_key="",
    )
    anthropic: LLMProviderConfig = LLMProviderConfig(
        model="claude-3-haiku",
        api_key="",
    )


class ExportSettings(BaseModel):
    """Default export format preferences."""

    model_config = ConfigDict(extra="forbid")

    default_format: Literal["trello", "json", "markdown"] = "json"


class AppSettings(BaseModel):
    """Top-level user application settings — mirrors frontend AppSettings."""

    model_config = ConfigDict(extra="forbid")

    llm: LLMSettings = LLMSettings()
    export: ExportSettings = ExportSettings()


class UserPreferencesResponse(BaseModel):
    """Response returned by GET /users/me/settings."""

    preferences: AppSettings
    updated_at: datetime


class UserPreferencesUpdate(BaseModel):
    """Request body for PUT /users/me/settings."""

    model_config = ConfigDict(extra="forbid")

    preferences: AppSettings


class LLMTestRequest(BaseModel):
    """Request body for POST /llm/test."""

    model_config = ConfigDict(extra="forbid")

    provider: Literal["ollama", "openai", "anthropic"]
    base_url: str | None = None
    api_key: str | None = None
    model: str = "llama3.2"


class LLMTestResponse(BaseModel):
    """Response returned by POST /llm/test."""

    success: bool
    message: str
    model: str | None = None
    latency_ms: int | None = None


class DeleteAccountResponse(BaseModel):
    """Response returned by DELETE /users/me."""

    message: str = "Account deleted successfully"
