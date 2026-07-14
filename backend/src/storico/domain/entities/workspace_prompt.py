"""WorkspacePrompt domain entity — prompt configuration for a workspace.

Each workspace can customise its system prompt, instruction template,
and few-shot examples to tailor the LLM extraction behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4


@dataclass(frozen=True, slots=True)
class WorkspacePrompt:
    """Prompt configuration scoped to a workspace.

    Allows each workspace to define custom system prompts, instruction
    templates, and few-shot examples that guide the LLM when extracting
    tasks from user stories.
    """

    workspace_id: UUID
    system_prompt: str | None = None
    instruction_template: str | None = None
    few_shot_examples: list[dict] | None = None
    id: UUID = field(default_factory=uuid4)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
