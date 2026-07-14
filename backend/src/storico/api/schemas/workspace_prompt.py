"""Workspace prompt Pydantic schemas for Storico API."""

from pydantic import BaseModel, ConfigDict


class PromptRequest(BaseModel):
    """Request body for upserting workspace prompts — all fields optional for partial updates."""

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = None
    instruction_template: str | None = None
    few_shot_examples: list[dict] | None = None


class PromptResponse(BaseModel):
    """Response body representing workspace prompts with resolved defaults."""

    model_config = ConfigDict(from_attributes=True)

    system_prompt: str | None = None
    instruction_template: str | None = None
    few_shot_examples: list[dict] | None = None
