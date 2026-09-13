"""Workspace prompt Pydantic schemas for Storico API."""

from pydantic import BaseModel, ConfigDict, Field
from typing import Annotated


class FewShotExample(BaseModel):
    """Single few-shot example for task extraction."""

    model_config = ConfigDict(extra="forbid")

    user_story: Annotated[str, Field(min_length=10, description="Input user story")]
    tasks: Annotated[str, Field(min_length=20, description="Expected task breakdown output")]


class PromptRequest(BaseModel):
    """Request body for upserting workspace prompts — all fields optional for partial updates."""

    model_config = ConfigDict(extra="forbid")

    system_prompt: str | None = None
    instruction_template: str | None = None
    few_shot_examples: Annotated[
        list[FewShotExample] | None,
        Field(default=None, max_length=3, description="Max 3 few-shot examples")
    ] = None


class PromptResponse(BaseModel):
    """Response body representing workspace prompts with resolved defaults."""

    model_config = ConfigDict(from_attributes=True)

    system_prompt: str | None = None
    instruction_template: str | None = None
    few_shot_examples: list[FewShotExample] | None = None
