"""Settings API routes — user preferences CRUD + LLM test + account deletion."""

from __future__ import annotations

import time
from typing import Annotated

from fastapi import APIRouter, Depends

from storico.api.dependencies import get_current_user, get_repository
from storico.api.schemas.settings import (
    REMOVED_PREFERENCE_KEYS,
    RETIRED_EXPORT_FORMATS,
    AppSettings,
    DeleteAccountResponse,
    LLMTestRequest,
    LLMTestResponse,
    UserPreferencesResponse,
    UserPreferencesUpdate,
)
from storico.config.settings import Settings
from storico.domain.entities import User
from storico.domain.services.llm_config_readiness import normalize_optional
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

    A stored document is read through the schema with the removed keys dropped: ``AppSettings``
    forbids extras, so a row written before the per-user LLM block was removed would otherwise
    fail validation and answer 500. Revision ``0022`` cleaned storage; this covers a row it did
    not reach.
    """
    existing = await repo.get(current_user.id)
    if existing is None:
        return UserPreferencesResponse(
            preferences=AppSettings(),
            updated_at=current_user.created_at,
        )
    return UserPreferencesResponse(
        preferences=AppSettings(**_for_schema(existing.preferences)),
        updated_at=existing.updated_at,
    )


def _for_schema(stored: dict) -> dict:
    """A stored document the schema can accept: removed keys dropped, retired values rewritten.

    Applied on both directions of the contract, not only where it is needed today. The read
    needs it (a row written before the removal must not 500 the endpoint); the write response
    does not, because ``PUT`` validates the body against ``AppSettings`` and both a removed key
    and a retired value are refused there. Going through the same helper anyway is what keeps
    the invariant "anything this endpoint hands to ``AppSettings`` from storage has been
    through this reconciliation" true by construction, rather than by one call site
    remembering it.

    The two halves have to differ, and the difference is the schema's: ``extra="forbid"``
    refuses a removed *key*, so dropping it is enough, while a retired *value* is invisible to
    it and fails the ``Literal`` instead — so the value is rewritten, not dropped.

    Both spellings the store can hold are rewritten: ``model_dump()`` writes ``default_format``
    and a client on the old contract wrote ``defaultFormat``, and ``populate_by_name`` makes
    either validate. Nothing else in the document is touched.
    """
    reconciled = {key: value for key, value in stored.items() if key not in REMOVED_PREFERENCE_KEYS}
    export = reconciled.get("export")
    if isinstance(export, dict):
        export = dict(export)
        for spelling in ("default_format", "defaultFormat"):
            stored_value = export.get(spelling)
            # ``isinstance`` before the membership test: a JSON document can hold any scalar,
            # and ``in`` on a dict hashes the value.
            if isinstance(stored_value, str) and stored_value in RETIRED_EXPORT_FORMATS:
                export[spelling] = RETIRED_EXPORT_FORMATS[stored_value]
        reconciled["export"] = export
    return reconciled


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
        preferences=AppSettings(**_for_schema(prefs.preferences)),
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
    Each of the four built-in providers constructs its own adapter (Ollama, Gemini, OpenAI,
    or Anthropic) and returns the raw response or a connection error message. Any other name
    is a workspace-registered custom provider, tested against its OpenAI-compatible endpoint
    the same way ``_build_llm_port`` routes extraction.
    """
    from storico.domain.ports import LLMConfig

    start = time.monotonic()

    # This route takes the endpoint and the credential from the request body, so a blank one
    # has to mean "absent" here too — otherwise a string of spaces is handed to an adapter,
    # which is the disagreement the workspace row used to have (see ``normalize_optional``).
    base_url = normalize_optional(body.base_url)
    api_key = normalize_optional(body.api_key)

    if body.provider == "ollama":
        base_url = base_url or Settings.load().ollama_host
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
        if not api_key:
            return LLMTestResponse(
                success=False,
                message="Gemini API key is required. Set it in workspace settings.",
            )
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

    if body.provider == "openai":
        if not api_key:
            return LLMTestResponse(
                success=False,
                message="OpenAI API key is required. Set it in workspace settings.",
            )
        from storico.infrastructure.llm import OpenAIAdapter

        adapter = OpenAIAdapter(api_key=api_key, base_url=base_url)
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
                message=f"OpenAI responded: {response[:100]}",
                model=body.model,
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return LLMTestResponse(
                success=False,
                message=f"OpenAI connection failed: {e}",
                latency_ms=elapsed,
            )

    if body.provider == "anthropic":
        if not api_key:
            return LLMTestResponse(
                success=False,
                message="Anthropic API key is required. Set it in workspace settings.",
            )
        from storico.infrastructure.llm import AnthropicAdapter

        adapter = AnthropicAdapter(api_key=api_key, base_url=base_url)
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
                message=f"Anthropic responded: {response[:100]}",
                model=body.model,
                latency_ms=elapsed,
            )
        except Exception as e:
            elapsed = int((time.monotonic() - start) * 1000)
            return LLMTestResponse(
                success=False,
                message=f"Anthropic connection failed: {e}",
                latency_ms=elapsed,
            )

    # Anything outside the four built-in names is a workspace-registered custom provider,
    # which ``_build_llm_port`` already sends to the OpenAI-compatible adapter. Refusing it
    # here as "not yet implemented" made this endpoint disagree with extraction about a
    # provider extraction supports; the endpoint requirement is the same rule as there, and
    # stated as a refused test rather than an exception because this is a probe, not a run.
    if not base_url:
        return LLMTestResponse(
            success=False,
            message=(
                f"Base URL is required for the custom provider '{body.provider}'. "
                "Set it in workspace settings."
            ),
        )

    from storico.infrastructure.llm import CUSTOM_PROVIDER_PLACEHOLDER_KEY, OpenAIAdapter

    adapter = OpenAIAdapter(api_key=api_key or CUSTOM_PROVIDER_PLACEHOLDER_KEY, base_url=base_url)
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
            message=f"{body.provider} responded: {response[:100]}",
            model=body.model,
            latency_ms=elapsed,
        )
    except Exception as e:
        elapsed = int((time.monotonic() - start) * 1000)
        return LLMTestResponse(
            success=False,
            message=f"{body.provider} connection failed: {e}",
            latency_ms=elapsed,
        )


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
