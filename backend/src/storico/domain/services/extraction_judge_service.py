"""LLMJudgeService — LLM-as-a-Judge validation for generated tasks."""

from __future__ import annotations

import json
import logging
import math

from storico.domain.entities.exceptions import JudgeOutputError, LLMError
from storico.domain.ports import LLMConfig, LLMPort
from storico.infrastructure.llm.prompt_manager import PromptManager

logger = logging.getLogger(__name__)

# The rubric in use today: five criteria scored 0-10 each (T3 of feature
# ``llm-judge-instrument`` moves this to the 1-7 design rubric; until then these
# constants are the single description of what the prompt asks for and what
# ``JudgeResult`` validates against).
JUDGE_CRITERIA: tuple[str, ...] = (
    "coherence",
    "completeness",
    "feasibility",
    "format",
    "granularity",
)
MAX_TOTAL_SCORE: int = len(JUDGE_CRITERIA) * 10  # 50
APPROVAL_RATIO: float = 0.7

_MIN_SCORE = 0
_MAX_SCORE = 10


def _coerce_score(name: str, value: object) -> float:
    """Coerce one criterion score into a number and clamp it into [0, 10].

    The clamp is S6 of the feature: the score is always a defined value inside
    the rubric's own range, whatever the model claims. Anything that cannot be
    coerced — a word, a ``null``, a list, a boolean (an ``int`` subclass that is
    not a score) — raises ``JudgeOutputError`` naming the criterion and the
    offending value.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise JudgeOutputError(f"judge criterion '{name}' is not a usable score: {value!r}")
    try:
        score = float(value)
    except ValueError:
        raise JudgeOutputError(
            f"judge criterion '{name}' is not a usable score: {value!r}"
        ) from None
    # ``float("nan")`` and ``float("inf")`` parse, and clamping them would turn
    # unusable output into a boundary score (``nan`` compares False both ways and
    # lands on the ceiling). Not finite is not a score.
    if not math.isfinite(score):
        raise JudgeOutputError(f"judge criterion '{name}' is not a finite score: {value!r}")
    return max(_MIN_SCORE, min(_MAX_SCORE, score))


class JudgeResult:
    """Result of an LLM-as-a-Judge evaluation.

    This class is the ONE place the judge's output is validated and coerced
    (D1/D6): every caller — the flagged runner and the unflagged service call
    site alike — gets its scores through ``from_model_output``, so a clamping
    fix can never land in one caller and miss the other. ``total_score`` and
    ``approved`` are computed from the clamped criteria, never trusted from the
    model (D3).
    """

    def __init__(
        self,
        *,
        approved: bool,
        total_score: float,
        max_total: int,
        criteria: dict[str, dict],
    ) -> None:
        self.approved = approved
        self.total_score = total_score
        self.max_total = max_total
        # Per criterion: ``{"score": <coerced number in [0, 10]>, "justification": <str|None>}``.
        self.criteria = criteria

    @classmethod
    def from_model_output(cls, data: dict) -> JudgeResult:
        """Validate and coerce a parsed judge payload into a result.

        Raises:
            JudgeOutputError: for any missing criterion, any non-object
                criterion entry, any missing score, and any score that cannot
                be coerced into the rubric's range — each message naming the
                field and the offending value.
        """
        if not isinstance(data, dict):
            raise JudgeOutputError(f"judge response is not a JSON object: {data!r}")

        criteria: dict[str, dict] = {}
        for name in JUDGE_CRITERIA:
            if name not in data:
                raise JudgeOutputError(
                    f"judge criterion '{name}' is missing from the judge response"
                )
            entry = data[name]
            if not isinstance(entry, dict):
                raise JudgeOutputError(f"judge criterion '{name}' is not an object: {entry!r}")
            if "score" not in entry:
                raise JudgeOutputError(f"judge criterion '{name}' has no score: {entry!r}")
            criteria[name] = {
                "score": _coerce_score(name, entry["score"]),
                "justification": entry.get("justification"),
            }

        total = sum(entry["score"] for entry in criteria.values())
        max_total = MAX_TOTAL_SCORE
        approved = total >= math.ceil(APPROVAL_RATIO * max_total)
        if total.is_integer():
            total = int(total)
        return cls(approved=approved, total_score=total, max_total=max_total, criteria=criteria)


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
        system_prompt: str | None = None,
    ) -> JudgeResult:
        """Evaluate generated tasks against the original user story.

        Args:
            user_story: The original user story text.
            tasks: List of task dicts with ``summary`` and ``description`` keys.
            config: LLM configuration for the judge model.
            system_prompt: Workspace system prompt, passed to the LLM port
                just like for extraction (``None`` sends no system message).

        Returns:
            ``JudgeResult`` with approval status, total score, and per-criteria breakdown.

        Raises:
            LLMError: If the LLM call for judging fails, or the response cannot
                be parsed as valid judge JSON. An unusable payload raises
                ``JudgeOutputError`` (an ``LLMError``): a classified failure,
                never a retried one and never a bare ``ValueError``.
        """
        judge_prompt = self._prompt_manager.render_judge_prompt(
            user_story=user_story,
            tasks=tasks,
        )

        try:
            judge_response = await self._llm.generate(
                judge_prompt,
                config,
                system_prompt=system_prompt,
            )
        except LLMError:
            raise
        except Exception as exc:
            logger.error(
                "Judge LLM call failed unexpectedly",
                extra={"error": str(exc), "error_type": type(exc).__name__},
            )
            raise LLMError(f"Judge LLM call failed: {exc}") from exc

        return self._parse_judge_response(judge_response.text)

    def _parse_judge_response(self, raw_response: str) -> JudgeResult:
        """Parse the JSON response from the judge LLM.

        Keeps the existing JSON/code-fence handling: malformed JSON and
        non-object payloads still raise ``LLMError``. Payload *validation* is
        delegated to ``JudgeResult.from_model_output`` so the contract lives in
        one place.

        Args:
            raw_response: Raw JSON text from the judge LLM.

        Returns:
            Parsed ``JudgeResult``.

        Raises:
            LLMError: If the response cannot be parsed as valid judge JSON, or
                the payload fails the ``JudgeResult`` contract.
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

        return JudgeResult.from_model_output(data)
