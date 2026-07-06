"""LLMJudgeService — LLM-as-a-Judge validation for generated tasks."""

from __future__ import annotations

import json

from storico.domain.entities.exceptions import LLMError
from storico.domain.ports import LLMConfig, LLMPort
from storico.infrastructure.llm.prompt_manager import PromptManager


class JudgeResult:
    """Result of an LLM-as-a-Judge evaluation."""

    def __init__(
        self,
        approved: bool,
        total_score: int,
        criteria: dict | None = None,
    ) -> None:
        self.approved = approved
        self.total_score = total_score
        self.criteria = criteria or {}


class LLMJudgeService:
    """LLM-as-a-Judge validation service.

    Uses a secondary LLM call to evaluate the quality of generated tasks
    against the original user story. Evaluates coherence, completeness,
    feasibility, format, and granularity.
    """

    def __init__(
        self,
        llm_port: LLMPort,
        prompt_manager: PromptManager,
    ) -> None:
        self._llm = llm_port
        self._prompt_manager = prompt_manager

    async def validate(
        self,
        user_story: str,
        tasks: list[dict],
        config: LLMConfig,
    ) -> JudgeResult:
        """Evaluate generated tasks against the original user story.

        Args:
            user_story: The original user story text.
            tasks: List of task dicts with ``summary`` and ``description`` keys.
            config: LLM configuration for the judge model.

        Returns:
            ``JudgeResult`` with approval status, total score, and per-criteria breakdown.

        Raises:
            LLMError: If the LLM call for judging fails.
        """
        judge_prompt = self._prompt_manager.render_judge_prompt(
            user_story=user_story,
            tasks=tasks,
        )

        try:
            raw_response = await self._llm.generate(judge_prompt, config)
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Judge LLM call failed: {exc}") from exc

        return self._parse_judge_response(raw_response)

    def _parse_judge_response(self, raw_response: str) -> JudgeResult:
        """Parse the JSON response from the judge LLM.

        Args:
            raw_response: Raw JSON text from the judge LLM.

        Returns:
            Parsed ``JudgeResult``.

        Raises:
            LLMError: If the response cannot be parsed as valid judge JSON.
        """
        cleaned = raw_response.strip()
        # Strip markdown code fences if present
        if cleaned.startswith("```"):
            # Find the first and last ```
            start = cleaned.find("\n")
            end = cleaned.rfind("```")
            if start != -1 and end != -1:
                cleaned = cleaned[start:end].strip()
            else:
                cleaned = cleaned.replace("```json", "").replace("```", "").strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            raise LLMError(f"Failed to parse judge response as JSON: {e}") from e

        if not isinstance(data, dict):
            raise LLMError("Judge response is not a JSON object")

        approved = data.get("approved", False)
        total_score = data.get("total_score", 0)
        # Extract per-criteria scores for the result
        criteria = {
            "coherence": data.get("coherence", {}).get("score", 0),
            "completeness": data.get("completeness", {}).get("score", 0),
            "feasibility": data.get("feasibility", {}).get("score", 0),
            "format": data.get("format", {}).get("score", 0),
            "granularity": data.get("granularity", {}).get("score", 0),
        }

        return JudgeResult(
            approved=bool(approved),
            total_score=int(total_score),
            criteria=criteria,
        )
