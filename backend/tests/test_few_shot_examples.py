"""Unit tests for unified Few-Shot Examples prompting and config validation.

Replaces the stale manual ``few_shot_examples`` suite. Focuses on:
- the single ``## Few-Shot Examples`` prompt section (rendered from ``examples``)
- cold-start omission when no examples are available
- the config fields on ``PromptRequest``/``PromptResponse`` (legacy ``few_shot_examples``
  is rejected by schema ``extra="forbid"``)
"""

from __future__ import annotations

import pytest

from storico.api.schemas.workspace_prompt import PromptRequest, PromptResponse
from storico.infrastructure.llm.prompt_manager import PromptManager


class TestUnifiedFewShotSection:
    """task_generation.j2 renders a single Few-Shot Examples section."""

    def setup_method(self) -> None:
        self.pm = PromptManager()

    def test_renders_single_section_when_examples_provided(self) -> None:
        """Examples render under ``## Few-Shot Examples``."""
        result = self.pm.render_instruction(
            None,
            user_story="As a user, I want reset password",
            examples="Example 1:\nUser story: Previous story\nTasks:\n1. Task A",
        )

        assert "## Few-Shot Examples" in result
        assert "Previous story" in result
        assert "Now break down the following user story:" in result
        # Exactly one Few-Shot Examples section header.
        assert result.count("## Few-Shot Examples") == 1
        # The legacy "Style Reference" / "Relevant Historical Examples" headers are gone.
        assert "Style Reference" not in result
        assert "Relevant Historical Examples" not in result
        # The user story is still present at the end.
        assert "As a user, I want reset password" in result

    def test_omits_section_on_cold_start(self) -> None:
        """No examples → instruction-only prompt, no section."""
        result = self.pm.render_instruction(
            None,
            user_story="As a user, I want reset password",
        )

        assert "## Few-Shot Examples" not in result
        assert "As a user, I want reset password" in result

    def test_omits_section_on_empty_examples(self) -> None:
        """Explicitly empty examples string → no section."""
        result = self.pm.render_instruction(
            None,
            user_story="Story",
            examples="",
        )

        assert "## Few-Shot Examples" not in result


class TestPromptConfigSchema:
    """PromptRequest/PromptResponse config fields."""

    def test_request_defaults_to_none(self) -> None:
        request = PromptRequest()
        assert request.system_prompt is None
        assert request.few_shot_enabled is None
        assert request.few_shot_limit is None
        assert request.few_shot_threshold is None

    def test_response_defaults(self) -> None:
        response = PromptResponse()
        assert response.few_shot_enabled is True
        assert response.few_shot_limit == 3
        assert response.few_shot_threshold == 0.85

    def test_request_accepts_valid_config(self) -> None:
        request = PromptRequest(few_shot_enabled=False, few_shot_limit=5, few_shot_threshold=0.9)
        assert request.few_shot_enabled is False
        assert request.few_shot_limit == 5
        assert request.few_shot_threshold == 0.9

    @pytest.mark.parametrize("limit", [0, 11])
    def test_request_rejects_out_of_range_limit(self, limit) -> None:
        with pytest.raises(ValueError):
            PromptRequest(few_shot_limit=limit)

    @pytest.mark.parametrize("threshold", [-0.1, 1.1])
    def test_request_rejects_out_of_range_threshold(self, threshold) -> None:
        with pytest.raises(ValueError):
            PromptRequest(few_shot_threshold=threshold)

    def test_request_rejects_legacy_few_shot_examples(self) -> None:
        """Posting ``few_shot_examples`` is rejected (extra='forbid')."""
        with pytest.raises(ValueError, match="few_shot_examples"):
            PromptRequest.model_validate(
                {
                    "few_shot_examples": [
                        {
                            "user_story": "As a user, I want login",
                            "tasks": "1. summary: T\ndescription: D",
                        }
                    ]
                }
            )

    def test_no_few_shot_examples_field_in_response(self) -> None:
        """The response no longer exposes the legacy few_shot_examples field."""
        response = PromptResponse()
        data = response.model_dump()
        assert "few_shot_examples" not in data
        assert data["few_shot_enabled"] is True
