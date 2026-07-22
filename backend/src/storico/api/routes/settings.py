"""Settings API routes — user preferences CRUD + LLM test + account deletion."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends

from storico.api.dependencies import get_current_user, get_repository
from storico.api.schemas.settings import (
    AppSettings,
    DeleteAccountResponse,
    LLMTestRequest,
    LLMTestResponse,
    UserPreferencesResponse,
    UserPreferencesUpdate,
)
from storico.config.settings import Settings
from storico.domain.entities import User
from storico.infrastructure.database.repositories import (
    SQLAlchemyUserPreferencesRepository,
    SQLAlchemyUserRepository,
)

# ── User Settings Router ──────────────────────────────────────────────────────

settings_router = APIRouter(
    prefix="/api/v1/users/me",
    tags=["settings"],
)

CurrentUserDep = Annotated[User, Depends(get_current_user)]
PrefRepoDep = Annotated[
    SQLAlchemyUserPreferencesRepository,
    Depends(get_repository(SQLAlchemyUserPreferencesRepository)),
]
UserRepoDep = Annotated[
    SQLAlchemyUserRepository,
    Depends(get_repository(SQLAlchemyUserRepository)),
]


@settings_router.get(
    "/settings",
    response_model=UserPreferencesResponse,
    response_model_by_alias=True,
)
async def get_settings(
    current_user: CurrentUserDep,
    repo: PrefRepoDep,
) -> UserPreferencesResponse:
    """Return the current user's application preferences.

    Returns defaults (from pydantic schema) when no preferences exist yet.
    """
    existing = await repo.get(current_user.id)
    if existing is None:
        return UserPreferencesResponse(
            preferences=AppSettings(),
            updated_at=current_user.created_at,
        )
    return UserPreferencesResponse(
        preferences=AppSettings(**existing.preferences),
        updated_at=existing.updated_at,
    )


@settings_router.put(
    "/settings",
    response_model=UserPreferencesResponse,
    response_model_by_alias=True,
)
async def update_settings(
    body: UserPreferencesUpdate,
    current_user: CurrentUserDep,
    repo: PrefRepoDep,
) -> UserPreferencesResponse:
    """Create or replace the current user's application preferences."""
    prefs = await repo.upsert(
        current_user.id,
        body.preferences.model_dump(),
    )
    return UserPreferencesResponse(
        preferences=AppSettings(**prefs.preferences),
        updated_at=prefs.updated_at,
    )


# ── LLM Test Router ───────────────────────────────────────────────────────────

test_router = APIRouter(
    prefix="/api/v1/llm",
    tags=["llm"],
)


@test_router.post("/test", response_model=LLMTestResponse)
async def test_llm_connection(
    body: LLMTestRequest,
    _current_user: CurrentUserDep,
) -> LLMTestResponse:
    """Test a connection to the specified LLM provider.

    Sends a minimal prompt (\"Hello\") and returns the result.
    For Ollama, uses the ``OllamaAdapter`` directly.
    For OpenAI and Anthropic, returns a descriptive error until those
    adapters are implemented.
    """
    from storico.domain.ports import LLMConfig

    start = time.monotonic()

    if body.provider == "ollama":
        base_url = body.base_url or Settings.load().ollama_host
        from storico.infrastructure.llm import OllamaAdapter

        adapter = OllamaAdapter(base_url=base_url)
        config = LLMConfig(
            model=body.model,
            temperature=0.1,
            max_tokens=10,
            timeout=30,
        )

        try:
            response = await adapter.generate("Hello", config)
            elapsed = int((time.monotonic() - start) * 1000)
            return LLMTestResponse(
                success=True,
                message=f"Ollama responded: {response[:100]}",
                model=body.model,
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return LLMTestResponse(
                success=False,
                message=f"Ollama connection failed: {e}",
                latency_ms=elapsed,
            )

    if body.provider == "gemini":
        if not body.api_key:
            return LLMTestResponse(
                success=False,
                message="Gemini API key is required. Set it in workspace settings.",
            )
        api_key = body.api_key
        from storico.infrastructure.llm import GeminiAdapter

        adapter = GeminiAdapter(api_key=api_key)
        config = LLMConfig(
            model=body.model,
            temperature=0.1,
            max_tokens=10,
            timeout=30,
        )

        try:
            response = await adapter.generate("Hello", config)
            elapsed = int((time.monotonic() - start) * 1000)
            return LLMTestResponse(
                success=True,
                message=f"Gemini responded: {response[:100]}",
                model=body.model,
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return LLMTestResponse(
                success=False,
                message=f"Gemini connection failed: {e}",
                latency_ms=elapsed,
            )

    msg = (
        f"{body.provider.title()} adapter not yet implemented. "
        "Only Ollama and Gemini are supported for connection testing at this time."
    )
    return LLMTestResponse(success=False, message=msg)


# ── Account Deletion ──────────────────────────────────────────────────────────


@settings_router.delete("", response_model=DeleteAccountResponse)
async def delete_account(
    current_user: CurrentUserDep,
    repo: UserRepoDep,
) -> DeleteAccountResponse:
    """Permanently delete the current user's account and ALL associated data.

    This action cannot be undone. All projects, stories, tasks, extractions,
    and linked accounts are cascade-deleted.
    """
    await repo.delete(current_user.id)
    return DeleteAccountResponse()
