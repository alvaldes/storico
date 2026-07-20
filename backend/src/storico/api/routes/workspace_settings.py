"""Workspace settings API routes — LLM config and prompt management.

All routes under ``/api/v1/workspaces/{workspace_id}/settings`` require
admin role for the target workspace.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, status

from storico.api.dependencies import get_repository, require_admin
from storico.api.schemas.workspace_llm_config import (
    LLMConfigRequest,
    LLMConfigResponse,
    ModelInfo,
)
from storico.api.schemas.workspace_prompt import PromptRequest, PromptResponse
from storico.config.settings import Settings
from storico.domain.entities.workspace import Workspace
from storico.domain.entities.workspace_member import WorkspaceRole
from storico.domain.entities.workspace_llm_config import WorkspaceLLMConfig
from storico.domain.entities.workspace_prompt import WorkspacePrompt
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

LLMConfigRepoDep = Annotated[
    SQLAlchemyWorkspaceLLMConfigRepository,
    Depends(get_repository(SQLAlchemyWorkspaceLLMConfigRepository)),
]

PromptRepoDep = Annotated[
    SQLAlchemyWorkspacePromptRepository,
    Depends(get_repository(SQLAlchemyWorkspacePromptRepository)),
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
        temperature=ws_config.temperature
        if ws_config.temperature is not None
        else 0.1,
        max_tokens=ws_config.max_tokens or 2048,
        base_url=ws_config.base_url or settings.ollama_host,
        api_key=ws_config.api_key,
    )


async def resolve_prompt(
    workspace_id: UUID,
    prompt_repo: SQLAlchemyWorkspacePromptRepository,
) -> PromptResponse:
    """Resolve workspace prompts with read-time fallback to global defaults.

    If no workspace-specific prompts exist, returns the hardcoded defaults
    from the thesis extraction pipeline.
    """
    ws_prompt = await prompt_repo.get(workspace_id)
    if ws_prompt is None:
        return PromptResponse(
            system_prompt=(
                "You are an expert software development lead who excels at "
                "breaking down user stories into clear, actionable development "
                "tasks."
            ),
            instruction_template=(
                "Break this user story into smaller development tasks to help "
                "the developers implement it efficiently. You can divide this "
                "user story into as many tasks as needed, depending on its "
                "complexity. Each task must be unique, actionable, and "
                "non-overlapping.\n\n"
                "Use EXACTLY this format — each numbered task starts on its "
                "own line with `N. summary:` followed by the summary text, "
                "then a new line with `description:` and the description "
                "text:\n\n"
                "1. summary: Set up database schema for transactions\n"
                "description: Create the necessary database tables and "
                "indexes...\n\n"
                "CRITICAL: Use ONLY plain text. Do NOT use markdown.\n\n"
                "User story:\n{{user_story}}"
            ),
            few_shot_examples=None,
        )
    return PromptResponse(
        system_prompt=ws_prompt.system_prompt,
        instruction_template=ws_prompt.instruction_template,
        few_shot_examples=ws_prompt.few_shot_examples,
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

    merged = WorkspaceLLMConfig(
        workspace_id=workspace.id,
        provider=body.provider
        if body.provider is not None
        else (existing.provider if existing else "ollama"),
        model=body.model
        if body.model is not None
        else (existing.model if existing else None),
        temperature=body.temperature
        if body.temperature is not None
        else (existing.temperature if existing else None),
        max_tokens=body.max_tokens
        if body.max_tokens is not None
        else (existing.max_tokens if existing else None),
        base_url=body.base_url
        if body.base_url is not None
        else (existing.base_url if existing else None),
        api_key=body.api_key
        if body.api_key is not None
        else (existing.api_key if existing else None),
    )

    await config_repo.upsert(merged)
    return await resolve_llm_config(workspace.id, config_repo, settings)


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
        few_shot_examples=body.few_shot_examples
        if body.few_shot_examples is not None
        else (existing.few_shot_examples if existing else None),
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
    return [
        ModelInfo(id=m["name"], name=m["name"])
        for m in data.get("models", [])
    ]


async def fetch_openai_models(api_key: str, base_url: str | None) -> list[ModelInfo]:
    """Fetch available models from the OpenAI API."""
    url = f"{base_url.rstrip('/')}/models" if base_url else f"{OPENAI_API_BASE}/models"
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
    return [
        ModelInfo(id=m["id"], name=m["id"])
        for m in data.get("data", [])
    ]


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
        ModelInfo(id=m["id"], name=m.get("display_name", m["id"]))
        for m in data.get("data", [])
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
        ModelInfo(id=m["name"], name=m.get("displayName", m["name"]))
        for m in data.get("models", [])
        if "generateContent" in m.get("supportedGenerationMethods", [])
    ]


@router.get("/llm/models")
async def list_available_models(
    config_repo: LLMConfigRepoDep,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> list[ModelInfo]:
    """List available models from the workspace's configured LLM provider.

    Proxies the request to the provider's model list API. Requires the
    workspace LLM config to have the necessary credentials saved first.
    """
    workspace, _ = ctx
    config = await config_repo.get(workspace.id)

    if config is None:
        return []

    try:
        if config.provider == "ollama":
            base_url = config.base_url or "http://localhost:11434"
            return await fetch_ollama_models(base_url)

        if config.provider == "openai":
            if not config.api_key:
                return []
            return await fetch_openai_models(config.api_key, config.base_url)

        if config.provider == "anthropic":
            if not config.api_key:
                return []
            return await fetch_anthropic_models(config.api_key)

        if config.provider == "gemini":
            if not config.api_key:
                return []
            return await fetch_gemini_models(config.api_key)

        return []
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to fetch models from {config.provider}: {e}",
        )
