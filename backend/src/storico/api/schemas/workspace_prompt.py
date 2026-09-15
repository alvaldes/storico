"""Workspace prompt Pydantic schemas for Storico API."""

from pydantic import BaseModel, ConfigDict, Field


class PromptRequest(BaseModel):
    """Request body for upserting workspace prompts — all fields optional for partial updates.

    ``few_shot_examples`` is no longer accepted: posting the legacy free-text
    examples field is rejected with 422 (``extra="forbid"``). Automatic few-shot
    retrieval is configured via ``few_shot_enabled``/``few_shot_limit``/
    ``few_shot_threshold``.
    """

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = None
    instruction_template: str | None = None
    few_shot_enabled: bool | None = None
    few_shot_limit: int | None = Field(default=None, ge=1, le=10)
    few_shot_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class PromptResponse(BaseModel):
    """Response body representing workspace prompts with resolved defaults.

    Defaults for the few-shot retrieval config are returned when a workspace has
    no explicit row (``enabled`` → true, ``limit`` → 3, ``threshold`` → 0.85).
    """

    model_config = ConfigDict(from_attributes=True)

    system_prompt: str | None = None
    instruction_template: str | None = None
    few_shot_enabled: bool = True
    few_shot_limit: int = Field(default=3, ge=1, le=10)
    few_shot_threshold: float = Field(default=0.85, ge=0.0, le=1.0)
