"""Workspace prompt resolution — DB-first with default seed on read.

The extraction pipeline always reads the prompt configuration from
``workspace_prompts``. Workspaces created before the prompt table existed
have no row, so resolution falls back to the shared defaults
(``SYSTEM_PROMPT_TASK_GENERATION`` constant + the raw ``task_generation.j2``
source) and seeds the row so it is populated for subsequent reads.
"""

from __future__ import annotations

from uuid import UUID

from storico.domain.entities import WorkspacePrompt
from storico.domain.ports import WorkspacePromptRepository
from storico.infrastructure.llm.prompt_manager import (
    SYSTEM_PROMPT_TASK_GENERATION,
    PromptManager,
)

DEFAULT_INSTRUCTION_TEMPLATE_NAME = "task_generation.j2"


def build_default_prompt(
    workspace_id: UUID,
    prompt_manager: PromptManager | None = None,
) -> WorkspacePrompt:
    """Build a ``WorkspacePrompt`` populated with the shared defaults.

    The system prompt is the ``SYSTEM_PROMPT_TASK_GENERATION`` constant and
    the instruction template is the raw source of ``task_generation.j2`` —
    both single-sourced, never duplicated as string literals.
    """
    manager = prompt_manager or PromptManager()
    return WorkspacePrompt(
        workspace_id=workspace_id,
        system_prompt=SYSTEM_PROMPT_TASK_GENERATION,
        instruction_template=manager.get_template_source(DEFAULT_INSTRUCTION_TEMPLATE_NAME),
        few_shot_examples=None,
    )


async def resolve_workspace_prompt(
    workspace_id: UUID,
    prompt_repo: WorkspacePromptRepository,
    prompt_manager: PromptManager | None = None,
) -> WorkspacePrompt:
    """Resolve the workspace prompt config, seeding defaults when missing.

    Existing workspace overrides are returned as-is. When no row exists,
    the shared defaults are persisted (seed on read) and returned so the
    pipeline always works against a populated row.
    """
    existing = await prompt_repo.get(workspace_id)
    if existing is not None:
        return existing

    default_prompt = build_default_prompt(workspace_id, prompt_manager)
    return await prompt_repo.upsert(default_prompt)
