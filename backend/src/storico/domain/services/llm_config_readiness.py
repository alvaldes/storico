"""Workspace LLM configuration completeness — the rule, declared once.

Extraction cannot run against an incomplete configuration, and the settings form has
to name *which* field is missing instead of only reporting that something is. Both
consumers read the two declarations below, and both speak the same vocabulary: the
missing *fields*, never a prose sentence. The API answers codes and the UI owns the
copy, which is why these constants are wire vocabulary and not labels.

This restates, as data, what ``_build_llm_port``
(:mod:`storico.infrastructure.tasks.extraction_task`) already enforces at runtime. The
four known cloud providers cannot call anything without a key, a custom
OpenAI-compatible provider cannot be called without an endpoint, and Ollama's host
falls back to the configured default (``resolve_llm_config``,
:mod:`storico.api.routes.workspace_settings`) so its base URL is never required.
Keeping the rule here — pure, no settings, no I/O — is what lets the API refuse before
it creates an extraction, and lets the frontend mirror it under a guard test.
"""

from __future__ import annotations

from typing import Literal

#: Every field a workspace configuration can be missing, in the order the API reports
#: them. The frontend mirrors this list by hand, guarded by
#: ``frontend/src/lib/__tests__/llm-config-readiness-mirror.test.ts``.
READINESS_FIELDS: tuple[str, ...] = ("model", "api_key", "base_url")

type ReadinessField = Literal["model", "api_key", "base_url"]

#: The structured error code an incomplete configuration is reported under. The
#: frontend maps it to translated copy, so the two sides must agree on the exact
#: spelling; the mirror guard fails when they do not.
LLM_CONFIG_INCOMPLETE_CODE = "LLM_CONFIG_INCOMPLETE"

#: Fields each known provider cannot be called without.
#:
#: A provider outside this mapping is a custom, OpenAI-compatible endpoint, which is
#: what ``_build_llm_port`` already assumes: it sends every unrecognised name to
#: ``OpenAIAdapter``.
REQUIRED_FIELDS_BY_PROVIDER: dict[str, tuple[ReadinessField, ...]] = {
    "ollama": ("model",),
    "openai": ("model", "api_key"),
    "anthropic": ("model", "api_key"),
    "gemini": ("model", "api_key"),
}

#: Fields a custom provider cannot be called without. ``api_key`` stays optional
#: because a self-hosted gateway commonly accepts unauthenticated requests.
CUSTOM_PROVIDER_REQUIRED_FIELDS: tuple[ReadinessField, ...] = ("model", "base_url")


def required_fields_for(provider: str) -> tuple[ReadinessField, ...]:
    """Return the fields ``provider`` cannot be called without.

    An unknown name is not an error here. Routing already treats anything outside the
    four known names as a custom OpenAI-compatible provider, so the rule does too.
    """
    return REQUIRED_FIELDS_BY_PROVIDER.get(provider, CUSTOM_PROVIDER_REQUIRED_FIELDS)


def normalize_optional(value: str | None) -> str | None:
    """Return a configured value, or ``None`` when it is blank.

    The one definition of "blank means absent". That comparison used to exist three times
    with three different meanings: :func:`missing_llm_config_fields` read a
    whitespace-only value as unset, while the API routes and ``_build_llm_port`` read it as
    a value and handed it to a provider — where an endpoint made of spaces fails inside the
    background task, after the extraction record has already been created.

    A value with content keeps it, minus its surrounding whitespace. Nothing else is
    touched: a credential is returned exactly as it was configured, internal characters
    included.
    """
    if value is None:
        return None
    return value.strip() or None


def missing_llm_config_fields(
    provider: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> tuple[ReadinessField, ...]:
    """Return which required fields are unset, in :data:`READINESS_FIELDS` order.

    A blank or whitespace-only value counts as unset: the settings form can leave an
    empty string behind where ``None`` would otherwise be stored, and an endpoint or a
    key made of spaces would fail the call just as loudly.

    Args:
        provider: Workspace provider name, known or custom.
        model: Configured model id, if any.
        api_key: Configured credential, if any.
        base_url: Configured endpoint, if any.

    Returns:
        The missing field codes, empty when the configuration is complete.
    """
    configured = {"model": model, "api_key": api_key, "base_url": base_url}
    required = required_fields_for(provider)
    return tuple(
        field for field in READINESS_FIELDS if field in required and not _is_set(configured[field])
    )


def llm_config_is_complete(
    provider: str,
    *,
    model: str | None = None,
    api_key: str | None = None,
    base_url: str | None = None,
) -> bool:
    """Whether the configuration holds everything ``provider`` needs to be called."""
    return not missing_llm_config_fields(provider, model=model, api_key=api_key, base_url=base_url)


def _is_set(value: str | None) -> bool:
    """Whether a configured value is actually present, by the one definition there is."""
    return normalize_optional(value) is not None
