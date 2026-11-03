"""Unit tests for the judge output contract — ``JudgeResult`` and ``JudgeOutputError``.

The rubric in use today scores five criteria on 0-10 (T3 changes the scale; these
tests pin the five names and the 0-10 bounds until then). ``JudgeResult`` is the
ONE place the judge's output is validated and coerced (D1/D6 of feature
``llm-judge-instrument``): an unusable payload raises ``JudgeOutputError`` — an
``LLMError`` — so the runner's ``except LLMError`` classifies it as a failed
judge instead of retrying it as if it were a network cut.
"""

import json

import pytest

from storico.domain.entities.exceptions import JudgeOutputError, LLMError
from storico.domain.services.extraction_judge_service import (
    APPROVAL_RATIO,
    JUDGE_CRITERIA,
    MAX_TOTAL_SCORE,
    JudgeResult,
    LLMJudgeService,
)


def _payload(**overrides: object) -> dict:
    """A well-formed judge payload: every criterion scored 7 with a justification."""
    base: dict = {name: {"score": 7, "justification": f"why {name}"} for name in JUDGE_CRITERIA}
    base.update(overrides)
    return base


class TestRubricConstants:
    """The rubric description is module-level and matches the prompt in use today."""

    def test_the_five_criteria_names_in_use_today(self) -> None:
        assert JUDGE_CRITERIA == (
            "coherence",
            "completeness",
            "feasibility",
            "format",
            "granularity",
        )

    def test_bounds_and_approval_ratio(self) -> None:
        assert MAX_TOTAL_SCORE == 50
        assert APPROVAL_RATIO == 0.7


class TestCoercion:
    """Numeric strings and floats are coerced; every score lands inside [0, 10]."""

    def test_a_float_score_is_kept(self) -> None:
        result = JudgeResult.from_model_output(_payload(coherence={"score": 7.5}))
        assert result.criteria["coherence"]["score"] == 7.5

    def test_a_numeric_string_score_is_coerced(self) -> None:
        result = JudgeResult.from_model_output(_payload(format={"score": "8"}))
        assert result.criteria["format"]["score"] == 8

    def test_above_the_bound_is_clamped_down(self) -> None:
        result = JudgeResult.from_model_output(_payload(completeness={"score": 12}))
        assert result.criteria["completeness"]["score"] == 10

    def test_below_the_bound_is_clamped_up(self) -> None:
        result = JudgeResult.from_model_output(_payload(feasibility={"score": -3}))
        assert result.criteria["feasibility"]["score"] == 0

    @pytest.mark.parametrize("score", ["nan", "inf", "-inf", float("nan")])
    def test_a_non_finite_score_is_refused_not_clamped(self, score: object) -> None:
        """``nan`` compares False both ways and would land on the ceiling.

        Clamping it would turn unusable output into a perfect score, so a
        non-finite value is a classified failure instead (S6).
        """
        with pytest.raises(JudgeOutputError) as excinfo:
            JudgeResult.from_model_output(_payload(granularity={"score": score}))
        assert "granularity" in str(excinfo.value)

    def test_total_is_the_sum_of_the_clamped_criteria(self) -> None:
        # 12 → 10 and -3 → 0, so the total is 7+10+0+7+7 = 31, never the model's claim.
        payload = _payload(completeness={"score": 12}, feasibility={"score": -3})
        payload["total_score"] = 99  # trusted from nobody (D3)
        payload["approved"] = False
        result = JudgeResult.from_model_output(payload)
        assert result.total_score == 31
        assert result.max_total == 50

    def test_the_model_verdict_is_never_trusted(self) -> None:
        """``approved`` and ``total_score`` from the model are recomputed, not read."""
        payload = _payload()  # 5 × 7 = 35
        payload["approved"] = False
        payload["total_score"] = 3
        result = JudgeResult.from_model_output(payload)
        assert result.total_score == 35
        assert result.approved is True


class TestApprovalBoundary:
    """``approved`` is ``total >= ceil(0.7 × max_total)`` — 35 on today's rubric."""

    def test_34_is_not_approved(self) -> None:
        # 6+7+7+7+7 = 34
        scores = {"coherence": 6}
        result = JudgeResult.from_model_output(
            _payload(**{k: {"score": v} for k, v in scores.items()})
        )
        assert result.total_score == 34
        assert result.approved is False

    def test_35_is_approved(self) -> None:
        result = JudgeResult.from_model_output(_payload())  # 5 × 7 = 35
        assert result.total_score == 35
        assert result.approved is True


class TestClassifiedFailures:
    """Every unusable payload raises ``JudgeOutputError`` — an ``LLMError``."""

    def test_judge_output_error_is_an_llm_error(self) -> None:
        from storico.domain.services.extraction_judge_service import JudgeOutputError

        assert issubclass(JudgeOutputError, LLMError)

    def test_a_non_coercible_score_names_the_field_and_the_value(self) -> None:
        from storico.domain.services.extraction_judge_service import JudgeOutputError

        with pytest.raises(JudgeOutputError) as excinfo:
            JudgeResult.from_model_output(_payload(granularity={"score": "high"}))
        message = str(excinfo.value)
        assert "granularity" in message
        assert "high" in message

    def test_a_null_score_is_not_coercible(self) -> None:
        from storico.domain.services.extraction_judge_service import JudgeOutputError

        with pytest.raises(JudgeOutputError):
            JudgeResult.from_model_output(_payload(coherence={"score": None}))

    def test_a_non_dict_criterion_entry_names_the_field(self) -> None:
        from storico.domain.services.extraction_judge_service import JudgeOutputError

        with pytest.raises(JudgeOutputError) as excinfo:
            JudgeResult.from_model_output(_payload(format=8))
        message = str(excinfo.value)
        assert "format" in message
        assert "8" in message

    def test_a_missing_criterion_names_the_field(self) -> None:
        from storico.domain.services.extraction_judge_service import JudgeOutputError

        payload = _payload()
        del payload["feasibility"]
        with pytest.raises(JudgeOutputError) as excinfo:
            JudgeResult.from_model_output(payload)
        assert "feasibility" in str(excinfo.value)

    def test_a_criterion_without_a_score_names_the_field(self) -> None:
        from storico.domain.services.extraction_judge_service import JudgeOutputError

        with pytest.raises(JudgeOutputError):
            JudgeResult.from_model_output(_payload(completeness={"justification": "why"}))

    def test_justifications_survive_validation(self) -> None:
        result = JudgeResult.from_model_output(_payload())
        for name in JUDGE_CRITERIA:
            assert result.criteria[name]["justification"] == f"why {name}"


class TestParseResponse:
    """``_parse_judge_response`` keeps its JSON/fence handling and never raises bare."""

    def _service(self) -> LLMJudgeService:
        from storico.infrastructure.llm.prompt_manager import PromptManager

        return LLMJudgeService(llm_port=None, prompt_manager=PromptManager())  # type: ignore[arg-type]

    def test_a_fenced_response_parses(self) -> None:
        fenced = f"```json\n{json.dumps(_payload())}\n```"
        result = self._service()._parse_judge_response(fenced)
        assert result.total_score == 35
        assert result.approved is True

    def test_malformed_json_is_still_an_llm_error(self) -> None:
        with pytest.raises(LLMError):
            self._service()._parse_judge_response("not json at all")

    def test_a_non_object_json_is_an_llm_error(self) -> None:
        with pytest.raises(LLMError):
            self._service()._parse_judge_response("[1, 2, 3]")

    @pytest.mark.parametrize(
        "raw",
        [
            json.dumps(_payload(granularity={"score": "high"})),
            json.dumps(_payload(format=8)),
            json.dumps({k: v for k, v in _payload().items() if k != "feasibility"}),
        ],
        ids=["non-coercible", "non-dict", "missing"],
    )
    def test_unusable_payloads_are_judge_output_errors_never_bare_type_errors(
        self, raw: str
    ) -> None:
        from storico.domain.services.extraction_judge_service import JudgeOutputError

        with pytest.raises(JudgeOutputError):
            self._service()._parse_judge_response(raw)
