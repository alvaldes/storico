"""Workspace settings API routes — LLM config and prompt management.

Every route under ``/api/v1/workspaces/{workspace_id}/settings`` requires the admin
role for the target workspace, with one deliberate exception: ``GET /llm/status`` is
member-readable. A member has no business reading the credential or the endpoint, but
they are the ones who attempt the extraction that depends on them, so they need to
learn the workspace is not ready *before* the attempt fails. That route answers with
the missing field names and never with a value.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from storico.api.dependencies import (
    get_llm_config_repository,
    get_repository,
    get_workspace_for_user,
    require_admin,
)
from storico.api.schemas.custom_provider import (
    KNOWN_PROVIDERS,
    SELECT_CONTROL_VALUE,
    CustomProviderRequest,
    CustomProviderResponse,
)
from storico.api.schemas.workspace_llm_config import (
    LLMConfigRequest,
    LLMConfigResponse,
    LLMConfigStatusResponse,
    LLMModelProbeRequest,
    ModelInfo,
)
from storico.api.schemas.workspace_prompt import PromptRequest, PromptResponse
from storico.application.prompts.resolve_workspace_prompt import build_default_prompt
from storico.config.settings import Settings
from storico.domain.entities.custom_provider import CustomProvider
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig
from storico.domain.entities.workspace_member import WorkspaceRole
from storico.domain.entities.workspace_prompt import WorkspacePrompt
from storico.domain.services.llm_config_readiness import (
    missing_llm_config_fields,
    normalize_optional,
)
from storico.infrastructure.database.repositories.custom_provider_repository import (
    SQLAlchemyCustomProviderRepository,
)
from storico.infrastructure.database.repositories.workspace_llm_config_repository import (
    SQLAlchemyWorkspaceLLMConfigRepository,
)
from storico.infrastructure.database.repositories.workspace_prompt_repository import (
    SQLAlchemyWorkspacePromptRepository,
)

router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/settings",
    tags=["workspace-settings"],
)

# ``type`` rather than a plain assignment: these are type aliases, and PEP 695
# declares that to the type checker instead of leaving it to infer an alias from an
# assignment. FastAPI resolves them through ``get_type_hints`` like any other
# ``Annotated`` dependency.
type LLMConfigRepoDep = Annotated[
    SQLAlchemyWorkspaceLLMConfigRepository,
    Depends(get_llm_config_repository),
]

type PromptRepoDep = Annotated[
    SQLAlchemyWorkspacePromptRepository,
    Depends(get_repository(SQLAlchemyWorkspacePromptRepository)),
]

type CustomProviderRepoDep = Annotated[
    SQLAlchemyCustomProviderRepository,
    Depends(get_repository(SQLAlchemyCustomProviderRepository)),
]


# ── Resolver helpers ──────────────────────────────────────────────


async def resolve_llm_config(
    workspace_id: UUID,
    config_repo: SQLAlchemyWorkspaceLLMConfigRepository,
    settings: Settings,
) -> LLMConfigResponse:
    """Resolve LLM config with read-time fallback to global defaults.

    If no workspace-specific config exists, returns the global defaults
    from ``Settings``. Otherwise merges workspace overrides on top of
    sensible defaults (workspace ``None`` fields fall back to defaults).

    The Ollama host is the default endpoint for Ollama alone. It is *not* a
    universal fallback, because this response is what the settings form loads into
    its fields and posts back as the pending selection: handing a cloud provider
    the Ollama host would point its model probe and its extraction at a local
    Ollama. A cloud provider with no configured ``base_url`` therefore resolves to
    ``None``, which every consumer already reads as "use this provider's own
    default".
    """
    ws_config = await config_repo.get(workspace_id)
    if ws_config is None:
        return LLMConfigResponse(
            provider="ollama",
            model=None,
            temperature=0.1,
            max_tokens=2048,
            base_url=settings.ollama_host,
        )
    return LLMConfigResponse(
        provider=ws_config.provider,
        model=ws_config.model,
        temperature=ws_config.temperature if ws_config.temperature is not None else 0.1,
        max_tokens=ws_config.max_tokens or 2048,
        # Normalized on the way out: a stored value made of spaces is "not configured",
        # which is what the completeness rule already says about it. Handing the spaces on
        # would put a URL of spaces in the form, in the probe and in the extraction.
        base_url=normalize_optional(ws_config.base_url)
        or (settings.ollama_host if ws_config.provider == "ollama" else None),
        api_key=normalize_optional(ws_config.api_key),
    )


async def resolve_prompt(
    workspace_id: UUID,
    prompt_repo: SQLAlchemyWorkspacePromptRepository,
) -> PromptResponse:
    """Resolve workspace prompts with read-time fallback to global defaults.

    If no workspace-specific prompts exist, returns the shared defaults
    (``SYSTEM_PROMPT_TASK_GENERATION`` constant + ``task_generation.j2``
    source) without persisting — the seed-on-read happens at extraction
    time. Defaults are single-sourced, never duplicated as string literals.
    """
    ws_prompt = await prompt_repo.get(workspace_id)
    if ws_prompt is None:
        ws_prompt = build_default_prompt(workspace_id)
    return PromptResponse(
        system_prompt=ws_prompt.system_prompt,
        instruction_template=ws_prompt.instruction_template,
        few_shot_enabled=getattr(ws_prompt, "few_shot_enabled", True),
        few_shot_limit=getattr(ws_prompt, "few_shot_limit", 3),
        few_shot_threshold=getattr(ws_prompt, "few_shot_threshold", 0.85),
    )


# ── LLM Config endpoints ──────────────────────────────────────────


@router.get("/llm")
async def get_llm_config(
    config_repo: LLMConfigRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> LLMConfigResponse:
    """Get the workspace LLM configuration.

    Returns resolved config: workspace overrides merged on top of global
    defaults. Admin only.
    """
    workspace, _ = ctx
    settings = Settings.load()
    return await resolve_llm_config(workspace.id, config_repo, settings)


@router.get("/llm/status")
async def get_llm_config_status(
    config_repo: LLMConfigRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
) -> LLMConfigStatusResponse:
    """Report whether this workspace can extract, and what it is still missing.

    Readable by any member, unlike every other route in this module. The member who
    cannot read the configuration is exactly the one who meets the failed extraction,
    so this is the one piece of it they are entitled to: the missing field names,
    never the key or the endpoint those fields hold.

    An unconfigured workspace resolves to Ollama, so its single gap is the model.
    """
    workspace, _ = ctx
    resolved = await resolve_llm_config(workspace.id, config_repo, Settings.load())
    missing = missing_llm_config_fields(
        resolved.provider,
        model=resolved.model,
        api_key=resolved.api_key,
        base_url=resolved.base_url,
    )
    return LLMConfigStatusResponse(
        configured=not missing,
        provider=resolved.provider,
        missing=list(missing),
    )


@router.put("/llm")
async def upsert_llm_config(
    body: LLMConfigRequest,
    config_repo: LLMConfigRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> LLMConfigResponse:
    """Upsert workspace LLM configuration.

    Only the fields provided in the request body are updated. Returns the
    resolved config after the update. Admin only.
    """
    workspace, _ = ctx
    settings = Settings.load()

    # Read existing config — if present, merge; otherwise start fresh
    existing = await config_repo.get(workspace.id)

    # A blank endpoint or credential is stored as ``None``, never as a string of spaces.
    # "Not configured" then has one representation in the table, and it is the one every
    # reader already understands — the completeness rule reads a whitespace-only value as
    # absent, so storing the spaces was a value only the consumers could disagree about.
    # The value carried over from the existing row is normalized too, so any save also
    # cleans a legacy blank instead of preserving it.
    merged = WorkspaceLLMConfig(
        workspace_id=workspace.id,
        provider=body.provider
        if body.provider is not None
        else (existing.provider if existing else "ollama"),
        model=body.model if body.model is not None else (existing.model if existing else None),
        temperature=body.temperature
        if body.temperature is not None
        else (existing.temperature if existing else None),
        max_tokens=body.max_tokens
        if body.max_tokens is not None
        else (existing.max_tokens if existing else None),
        base_url=normalize_optional(body.base_url)
        if body.base_url is not None
        else (normalize_optional(existing.base_url) if existing else None),
        api_key=normalize_optional(body.api_key)
        if body.api_key is not None
        else (normalize_optional(existing.api_key) if existing else None),
    )

    await config_repo.upsert(merged)
    return await resolve_llm_config(workspace.id, config_repo, settings)


# ── Custom provider endpoints ─────────────────────────────────────


def _reject_reserved_provider_name(name: str) -> None:
    """Refuse a name the registry cannot own.

    Two names already mean something else. A built-in provider has its own adapter
    branch and model-discovery endpoint, so a registry row for it would only
    duplicate an entry the select already offers — and the comparison is
    case-insensitive, because a name is free-form text now: ``OpenAI`` sits beside
    ``openai`` in the select while routing to the custom branch, which is worse than
    refusing it. The select's own control value is refused for the same reason: a
    provider registered under it would occupy the "Add custom provider…" slot and
    could never be selected.
    """
    if name.lower() in KNOWN_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{name}' is a built-in provider and cannot be registered as a custom one",
        )
    if name == SELECT_CONTROL_VALUE:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"'{name}' is reserved by the provider selector",
        )


async def _repoint_selected_provider(
    config_repo: SQLAlchemyWorkspaceLLMConfigRepository,
    workspace_id: UUID,
    old_name: str,
    new_name: str,
) -> None:
    """Follow a rename into the workspace's selected provider, if it is that one.

    The selection is stored as the provider *name*, so renaming the selected
    provider without rewriting the config would leave the workspace pointing at a
    name the registry no longer holds. A rename of any other provider leaves the
    config untouched, along with the model, key and endpoint it owns.
    """
    config = await config_repo.get(workspace_id)
    if config is None or config.provider != old_name:
        return
    await config_repo.upsert(replace(config, provider=new_name, updated_at=datetime.now(UTC)))


@router.get("/providers")
async def list_custom_providers(
    provider_repo: CustomProviderRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> list[CustomProviderResponse]:
    """List the workspace's registered custom providers, ordered by name.

    Scoped to the workspace: no other workspace's providers are reachable here.
    Admin only.
    """
    workspace, _ = ctx
    providers = await provider_repo.list_by_workspace(workspace.id)
    return [CustomProviderResponse.model_validate(provider) for provider in providers]


@router.post("/providers", status_code=status.HTTP_201_CREATED)
async def create_custom_provider(
    body: CustomProviderRequest,
    provider_repo: CustomProviderRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> CustomProviderResponse:
    """Register a custom provider name for this workspace. Admin only.

    The name is normalized by the request schema (trimmed, keeping its casing), so
    surrounding whitespace cannot produce a second row for a name the workspace
    already has.
    """
    workspace, _ = ctx
    _reject_reserved_provider_name(body.name)

    existing = await provider_repo.find_by_workspace_and_name(workspace.id, body.name)
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Custom provider '{body.name}' already exists in this workspace",
        )

    created = await provider_repo.create(CustomProvider(workspace_id=workspace.id, name=body.name))
    return CustomProviderResponse.model_validate(created)


@router.patch("/providers/{provider_id}")
async def rename_custom_provider(
    provider_id: UUID,
    body: CustomProviderRequest,
    provider_repo: CustomProviderRepoDep,
    config_repo: LLMConfigRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> CustomProviderResponse:
    """Rename a custom provider, and the selection that names it. Admin only.

    A provider id belonging to another workspace reads as absent rather than as
    a cross-workspace write. Renaming the provider this workspace has selected
    also rewrites the selection, so the two cannot drift apart.
    """
    workspace, _ = ctx

    existing = await provider_repo.get(provider_id)
    if existing is None or existing.workspace_id != workspace.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom provider not found",
        )

    # A rename to the name it already has is a no-op, not a duplicate: reporting a
    # conflict here would make the pencil fail on an unchanged submit. It is also
    # checked *before* the reserved-name guard, for the same reason: migration 0021
    # backfilled a row per existing config whose provider was not one of the four
    # names — by exact match, so a stored `Ollama` became a row named `Ollama` — and
    # such a row has to be able to submit its own name back.
    if existing.name == body.name:
        return CustomProviderResponse.model_validate(existing)

    _reject_reserved_provider_name(body.name)

    duplicate = await provider_repo.find_by_workspace_and_name(workspace.id, body.name)
    if duplicate is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Custom provider '{body.name}' already exists in this workspace",
        )

    renamed = await provider_repo.rename(provider_id, body.name)
    if renamed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Custom provider not found",
        )

    await _repoint_selected_provider(config_repo, workspace.id, existing.name, renamed.name)
    return CustomProviderResponse.model_validate(renamed)


# ── Prompt endpoints ──────────────────────────────────────────────


@router.get("/prompts")
async def get_prompts(
    prompt_repo: PromptRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> PromptResponse:
    """Get the workspace prompt configuration.

    Returns resolved prompts: workspace overrides merged on top of global
    defaults. Admin only.
    """
    workspace, _ = ctx
    return await resolve_prompt(workspace.id, prompt_repo)


@router.put("/prompts")
async def upsert_prompts(
    body: PromptRequest,
    prompt_repo: PromptRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> PromptResponse:
    """Upsert workspace prompt configuration.

    Only the fields provided in the request body are updated. Returns the
    resolved prompt config after the update. Admin only.
    """
    workspace, _ = ctx

    existing = await prompt_repo.get(workspace.id)

    merged = WorkspacePrompt(
        workspace_id=workspace.id,
        system_prompt=body.system_prompt
        if body.system_prompt is not None
        else (existing.system_prompt if existing else None),
        instruction_template=body.instruction_template
        if body.instruction_template is not None
        else (existing.instruction_template if existing else None),
        few_shot_enabled=body.few_shot_enabled
        if body.few_shot_enabled is not None
        else (existing.few_shot_enabled if existing else True),
        few_shot_limit=body.few_shot_limit
        if body.few_shot_limit is not None
        else (existing.few_shot_limit if existing else 3),
        few_shot_threshold=body.few_shot_threshold
        if body.few_shot_threshold is not None
        else (existing.few_shot_threshold if existing else 0.85),
    )

    await prompt_repo.upsert(merged)
    return await resolve_prompt(workspace.id, prompt_repo)


# ── Available models endpoint ────────────────────────────────────


# Default API endpoints for cloud providers
OPENAI_API_BASE = "https://api.openai.com/v1"
ANTHROPIC_API_BASE = "https://api.anthropic.com"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"


async def fetch_ollama_models(base_url: str) -> list[ModelInfo]:
    """Fetch available models from Ollama's /api/tags endpoint."""
    url = f"{base_url.rstrip('/')}/api/tags"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return [ModelInfo(id=m["name"], name=m["name"]) for m in data.get("models", [])]


async def fetch_openai_compatible_models(
    base_url: str,
    api_key: str | None,
    client: httpx.AsyncClient | None = None,
) -> list[ModelInfo]:
    """Fetch available models from any OpenAI-compatible ``/models`` endpoint.

    Servers disagree on whether the configured base URL already carries the
    ``/v1`` segment, so both spellings are probed and the first one answering
    with a ``data`` list wins. The key stays optional because self-hosted
    gateways commonly accept unauthenticated requests.
    """
    stripped = base_url.rstrip("/")
    candidates = [f"{stripped}/models"]
    if not stripped.endswith("/v1"):
        candidates.append(f"{stripped}/v1/models")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)

    last_error: httpx.HTTPError | None = None
    try:
        for url in candidates:
            try:
                resp = await client.get(url, headers=headers)
                resp.raise_for_status()
                payload = resp.json()
            except httpx.HTTPError as e:
                last_error = e
                continue
            except ValueError:
                continue

            entries = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(entries, list):
                continue
            return [
                ModelInfo(id=entry["id"], name=entry["id"])
                for entry in entries
                if isinstance(entry, dict) and "id" in entry
            ]
    finally:
        if owns_client:
            await client.aclose()

    if last_error is not None:
        raise last_error
    raise httpx.HTTPError(f"No OpenAI-compatible model list found at {base_url}")


async def fetch_openai_models(api_key: str, base_url: str | None) -> list[ModelInfo]:
    """Fetch available models from OpenAI, or from a configured compatible base URL."""
    return await fetch_openai_compatible_models(base_url or OPENAI_API_BASE, api_key)


async def fetch_anthropic_models(api_key: str) -> list[ModelInfo]:
    """Fetch available models from the Anthropic API."""
    url = f"{ANTHROPIC_API_BASE}/v1/models"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            url,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
            },
        )
        resp.raise_for_status()
        data = resp.json()
    return [
        ModelInfo(id=m["id"], name=m.get("display_name", m["id"])) for m in data.get("data", [])
    ]


async def fetch_gemini_models(api_key: str) -> list[ModelInfo]:
    """Fetch available models from the Gemini API.

    Returns only models that support content generation (``generateContent``).
    """
    url = f"{GEMINI_API_BASE}/models?key={api_key}"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        data = resp.json()
    return [
        ModelInfo(id=m["name"].removeprefix("models/"), name=m.get("displayName", m["name"]))
        for m in data.get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]


@dataclass(frozen=True)
class _ProbeInputs:
    """Fully resolved inputs for one model-list probe.

    Holds the provider name and *its own* endpoint and credential, kept together so
    no call can pair one provider with another's fields halfway through.
    """

    provider: str
    base_url: str | None
    api_key: str | None


def _resolve_probe(
    body: LLMModelProbeRequest | None,
    saved: WorkspaceLLMConfig | None,
) -> _ProbeInputs | None:
    """Decide which provider the model list must describe.

    A body that names a provider describes the probe entirely: the key and base URL
    come from the body alone, and one left out is *missing* rather than borrowed
    from the saved row. Borrowing would send the saved workspace credential to
    whichever endpoint the pending provider names.

    A body without a provider carries no selection, so it falls back to the saved
    row and the endpoint keeps answering for the persisted state. Nothing saved and
    nothing posted leaves no provider to ask, which is ``None``.
    """
    if body is not None and body.provider is not None:
        return _ProbeInputs(
            provider=body.provider,
            base_url=body.base_url,
            api_key=body.api_key,
        )

    if saved is None:
        return None

    return _ProbeInputs(
        provider=saved.provider,
        base_url=saved.base_url,
        api_key=saved.api_key,
    )


async def _probe_models(probe: _ProbeInputs) -> list[ModelInfo]:
    """Ask the resolved provider for its model list.

    Kept separate from the route so the per-provider routing rule is testable
    without a request, and so the 502 mapping names the provider that was actually
    asked rather than the one that happened to be saved.
    """
    # Read once, normalized: a blank endpoint or credential means "not configured" here
    # exactly as it does for the completeness rule. Before this, the spaces were truthy, so
    # Ollama's branch skipped its default host and httpx raised ``UnsupportedProtocol``,
    # which the route mapped to a 502 that reads as "the provider is unreachable".
    base_url = normalize_optional(probe.base_url)
    api_key = normalize_optional(probe.api_key)

    if probe.provider == "ollama":
        return await fetch_ollama_models(base_url or "http://localhost:11434")

    if probe.provider == "openai":
        if not api_key:
            return []
        return await fetch_openai_models(api_key, base_url)

    if probe.provider == "anthropic":
        if not api_key:
            return []
        return await fetch_anthropic_models(api_key)

    if probe.provider == "gemini":
        if not api_key:
            return []
        return await fetch_gemini_models(api_key)

    # Anything else is a custom provider assumed to speak the OpenAI wire format.
    if not base_url:
        return []
    return await fetch_openai_compatible_models(base_url, api_key)


@router.post("/llm/models")
async def list_available_models(
    config_repo: LLMConfigRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
    body: LLMModelProbeRequest | None = None,
) -> list[ModelInfo]:
    """List available models from an LLM provider.

    Proxies the request to the provider's model list API. The body optionally
    carries the selection the settings form has in hand so the answer describes
    the provider the user just picked; without one the saved workspace config is
    probed, which is what keeps the persisted state observable.

    ``POST`` rather than ``GET`` with query parameters because the pending
    selection carries an API key, and a query string writes it into access logs.
    The sibling ``POST /api/v1/llm/test`` carries pending credentials the same way.
    """
    workspace, _ = ctx
    probe = _resolve_probe(body, await config_repo.get(workspace.id))

    if probe is None:
        return []

    try:
        return await _probe_models(probe)
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch models from {probe.provider}: {e}",
        )
