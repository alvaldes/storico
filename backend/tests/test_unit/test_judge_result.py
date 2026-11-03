"""Unit tests for the judge output contract — ``JudgeResult`` and ``JudgeOutputError``.

The rubric is the experimental design's (S1 of feature ``llm-judge-instrument``):
seven criteria scored 1-7 each, ``clarity`` having replaced the old ``format``.
``JudgeResult`` is the ONE place the judge's output is validated and coerced
(D1/D6 of the same feature): an unusable payload raises ``JudgeOutputError`` — an
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
    """The rubric description is module-level: seven criteria on 1-7 (S1)."""

    def test_the_seven_criteria_names_in_wire_order(self) -> None:
        assert JUDGE_CRITERIA == (
            "coherence",
            "completeness",
            "feasibility",
            "clarity",
            "granularity",
            "dependencies",
            "usefulness",
        )

    def test_bounds_and_approval_ratio(self) -> None:
        assert MAX_TOTAL_SCORE == 49
        assert APPROVAL_RATIO == 0.7


class TestCoercion:
    """Numeric strings and floats are coerced; every score lands inside [1, 7]."""

    def test_a_float_score_is_kept(self) -> None:
        result = JudgeResult.from_model_output(_payload(coherence={"score": 6.5}))
        assert result.criteria["coherence"]["score"] == 6.5

    def test_a_numeric_string_score_is_coerced(self) -> None:
        result = JudgeResult.from_model_output(_payload(clarity={"score": "5"}))
        assert result.criteria["clarity"]["score"] == 5

    def test_zero_is_clamped_up_to_the_floor(self) -> None:
        """The 1-7 rubric has no zero: a claimed 0 lands on 1, never 0."""
        result = JudgeResult.from_model_output(_payload(feasibility={"score": 0}))
        assert result.criteria["feasibility"]["score"] == 1

    def test_nine_is_clamped_down_to_the_ceiling(self) -> None:
        """The 0-10 habit has no nine: a claimed 9 lands on 7, never 9."""
        result = JudgeResult.from_model_output(_payload(completeness={"score": 9}))
        assert result.criteria["completeness"]["score"] == 7

    def test_above_the_bound_is_clamped_down(self) -> None:
        result = JudgeResult.from_model_output(_payload(completeness={"score": 12}))
        assert result.criteria["completeness"]["score"] == 7

    def test_below_the_bound_is_clamped_up(self) -> None:
        result = JudgeResult.from_model_output(_payload(feasibility={"score": -3}))
        assert result.criteria["feasibility"]["score"] == 1

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
        # 12 → 7 and -3 → 1, so the total is 6×7 + 1 = 43, never the model's claim.
        payload = _payload(completeness={"score": 12}, feasibility={"score": -3})
        payload["total_score"] = 99  # trusted from nobody (D3)
        payload["approved"] = False
        result = JudgeResult.from_model_output(payload)
        assert result.total_score == 43
        assert result.max_total == 49

    def test_the_total_range_spans_seven_to_forty_nine(self) -> None:
        """Every criterion is at least 1, so the floor total is 7, not 0."""
        floor = JudgeResult.from_model_output({name: {"score": 1} for name in JUDGE_CRITERIA})
        assert floor.total_score == 7
        assert floor.approved is False

        ceiling = JudgeResult.from_model_output(_payload())
        assert ceiling.total_score == 49
        assert ceiling.approved is True

    def test_the_model_verdict_is_never_trusted(self) -> None:
        """``approved`` and ``total_score`` from the model are recomputed, not read."""
        payload = _payload()  # 7 × 7 = 49
        payload["approved"] = False
        payload["total_score"] = 3
        result = JudgeResult.from_model_output(payload)
        assert result.total_score == 49
        assert result.approved is True


class TestIndices:
    """TAS and IFI are means the code derives, never values the model sends (S2)."""

    def test_tas_is_the_mean_of_coherence_and_feasibility(self) -> None:
        result = JudgeResult.from_model_output(
            _payload(coherence={"score": 3}, feasibility={"score": 5})
        )
        assert result.tas == pytest.approx(4.0)

    def test_ifi_is_the_mean_of_clarity_granularity_and_dependencies(self) -> None:
        result = JudgeResult.from_model_output(
            _payload(
                clarity={"score": 2},
                granularity={"score": 4},
                dependencies={"score": 6},
            )
        )
        assert result.ifi == pytest.approx(4.0)

    def test_the_indices_are_means_not_sums(self) -> None:
        """A sum would give 8 and 12 here; the rubric defines averages (S2)."""
        result = JudgeResult.from_model_output(
            _payload(
                coherence={"score": 3},
                feasibility={"score": 5},
                clarity={"score": 2},
                granularity={"score": 4},
                dependencies={"score": 6},
            )
        )
        assert result.tas == pytest.approx(4.0)
        assert result.ifi == pytest.approx(4.0)

    def test_completeness_and_usefulness_are_exposed_not_derived(self) -> None:
        """The two dimensions that are no index travel as their own scores (S2)."""
        result = JudgeResult.from_model_output(
            _payload(completeness={"score": 5}, usefulness={"score": 6})
        )
        assert result.completeness == 5
        assert result.usefulness == 6


class TestApprovalBoundary:
    """``approved`` is ``total >= ceil(0.7 × 49) = 35`` — the same cut as before."""

    def test_34_is_not_approved(self) -> None:
        # Six 5s and one 4: 6×5 + 4 = 34
        scores = {name: 5 for name in JUDGE_CRITERIA}
        scores["clarity"] = 4
        result = JudgeResult.from_model_output(
            {name: {"score": score} for name, score in scores.items()}
        )
        assert result.total_score == 34
        assert result.approved is False

    def test_35_is_approved(self) -> None:
        result = JudgeResult.from_model_output(
            {name: {"score": 5} for name in JUDGE_CRITERIA}  # 7 × 5 = 35
        )
        assert result.total_score == 35
        assert result.approved is True


class TestClassifiedFailures:
    """Every unusable payload raises ``JudgeOutputError`` — an ``LLMError``."""

    def test_judge_output_error_is_an_llm_error(self) -> None:
        assert issubclass(JudgeOutputError, LLMError)

    def test_a_non_coercible_score_names_the_field_and_the_value(self) -> None:
        with pytest.raises(JudgeOutputError) as excinfo:
            JudgeResult.from_model_output(_payload(granularity={"score": "high"}))
        message = str(excinfo.value)
        assert "granularity" in message
        assert "high" in message

    def test_a_null_score_is_not_coercible(self) -> None:
        with pytest.raises(JudgeOutputError):
            JudgeResult.from_model_output(_payload(coherence={"score": None}))

    def test_a_non_dict_criterion_entry_names_the_field(self) -> None:
        with pytest.raises(JudgeOutputError) as excinfo:
            JudgeResult.from_model_output(_payload(clarity=8))
        message = str(excinfo.value)
        assert "clarity" in message
        assert "8" in message

    def test_a_missing_criterion_names_the_field(self) -> None:
        payload = _payload()
        del payload["feasibility"]
        with pytest.raises(JudgeOutputError) as excinfo:
            JudgeResult.from_model_output(payload)
        assert "feasibility" in str(excinfo.value)

    def test_a_six_criterion_payload_is_refused_as_missing(self) -> None:
        """A payload with one criterion short is not accepted with a silent zero.

        The old 0-10 rubric defaulted missing scores to 0; the 1-7 rubric has
        no zero, so a missing criterion is a classified failure naming the
        field — exactly the drift the prompt/parser guard watches for.
        """
        payload = _payload()
        del payload["usefulness"]
        with pytest.raises(JudgeOutputError) as excinfo:
            JudgeResult.from_model_output(payload)
        assert "usefulness" in str(excinfo.value)
        assert "missing" in str(excinfo.value)

    def test_a_criterion_without_a_score_names_the_field(self) -> None:
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
        assert result.total_score == 49
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
            json.dumps(_payload(clarity=8)),
            json.dumps({k: v for k, v in _payload().items() if k != "feasibility"}),
        ],
        ids=["non-coercible", "non-dict", "missing"],
    )
    def test_unusable_payloads_are_judge_output_errors_never_bare_type_errors(
        self, raw: str
    ) -> None:
        with pytest.raises(JudgeOutputError):
            self._service()._parse_judge_response(raw)


class TestPromptParserDriftGuard:
    """The template cannot import the constants: the guard pins them together.

    A silent mismatch between what ``single_judge.j2`` asks for and what
    ``JudgeResult`` parses is exactly how the two drifted apart when the rubric
    moved from five 0-10 criteria to seven 1-7 ones.
    """

    def test_the_prompt_names_exactly_the_rubric_criteria(self) -> None:
        import re

        from storico.infrastructure.llm.prompt_manager import PromptManager

        source = PromptManager().get_template_source("single_judge.j2")

        # The JSON output contract's top-level keys are the wire names the
        # parser reads; they must be exactly ``JUDGE_CRITERIA``, in order.
        named = re.findall(r'^  "([a-z_]+)": \{', source, flags=re.MULTILINE)
        assert named == list(JUDGE_CRITERIA)

        # And the converse: every criterion name appears somewhere in the
        # template, so the rubric section cannot drop one.
        for name in JUDGE_CRITERIA:
            assert name in source

        # The renamed dimension must not survive under its old wire name, and
        # the scale the template announces must be the rubric's own.
        assert '"format"' not in source
        assert "1-7" in source
        assert "0-10" not in source
