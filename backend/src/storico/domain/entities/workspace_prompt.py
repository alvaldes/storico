"""WorkspacePrompt domain entity — prompt configuration for a workspace.

Each workspace can customise its system prompt, instruction template,
and few-shot examples to tailor the LLM extraction behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID

from uuid_utils.compat import uuid7

from storico.domain.entities.few_shot import FewShotExample


@dataclass(frozen=True, slots=True)
class WorkspacePrompt:
    """Prompt configuration scoped to a workspace.

    Allows each workspace to define custom system prompts, instruction
    templates, and automatic few-shot retrieval configuration.
    """

    workspace_id: UUID
    system_prompt: str | None = None
    instruction_template: str | None = None
    # Automatic few-shot retrieval config (replaces manual examples).
    few_shot_enabled: bool = True
    few_shot_limit: int = 3
    few_shot_threshold: float = 0.85
    # Deprecated: legacy manual examples, retained read-only for the seed
    # job. Will be dropped in a follow-up migration.
    few_shot_examples: list[FewShotExample] | None = None
    id: UUID = field(default_factory=uuid7)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
