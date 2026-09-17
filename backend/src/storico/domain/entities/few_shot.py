"""Few-shot example types for workspace prompt configuration."""

from __future__ import annotations

from typing import TypedDict


class FewShotExample(TypedDict):
    """A single few-shot example for task extraction prompt.

    Attributes:
        user_story: The input user story text (min 10 chars).
        tasks: Expected task breakdown output matching the exact format
               the LLM should produce (numbered summary/description).
    """

    user_story: str
    tasks: str
