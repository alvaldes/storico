"""Unit table for the negative-example composer (slice (c), WU2 tasks 2.1–2.2).

The composer is pure: it takes (b)'s ``TaskInvalidationCandidate`` rows, sorts
them into a total order, dedupes on (normalized title, reason), applies the
module cap constant, and reports the omitted count. No session, no I/O, no new
mark read — the read is (b)'s ``list_active_on_other_versions`` and part (ii)
wires it; here only the composition is proven.
"""

from __future__ import annotations

import inspect
import json
from datetime import datetime, timedelta

import storico.domain.services.negative_examples as negative_examples
import storico.domain.services.task_title_normalizer as task_title_normalizer
from storico.domain.ports.task_invalidation_repository import TaskInvalidationCandidate
from storico.domain.services.negative_examples import (
    MAX_NEGATIVE_EXAMPLES,
    compose_negative_examples,
)

_BASE = datetime(2026, 9, 30, 12, 0, 0)


def _candidate(
    version_number: int,
    title: str,
    reason: str,
    offset_minutes: int = 0,
) -> TaskInvalidationCandidate:
    return TaskInvalidationCandidate(
        version_number=version_number,
        title=title,
        reason=reason,
        marked_at=_BASE + timedelta(minutes=offset_minutes),
    )


def test_cap_20_of_21_distinct_with_omitted_one_and_most_recent_first():
    candidates = [
        _candidate(
            version_number=n,
            title=f"Task number {n}",
            reason=f"Reason {n}",
            offset_minutes=n,
        )
        for n in range(21)
    ]

    block = compose_negative_examples(candidates)

    assert MAX_NEGATIVE_EXAMPLES == 20
    assert len(block.examples) == 20
    assert block.omitted == 1
    # Most recent marked_at first: the candidate with the largest offset leads.
    assert block.examples[0].title == "Task number 20"
    assert block.examples[19].title == "Task number 1"
    assert all(
        block.examples[i].marked_at >= block.examples[i + 1].marked_at
        for i in range(len(block.examples) - 1)
    )


def test_dedupe_keeps_most_recent_and_different_reason_stays_two():
    older = _candidate(1, "Implement login retry", "Duplicates the auth task", offset_minutes=0)
    newer = _candidate(
        2, "  Implement   LOGIN retry  ", "Duplicates the auth task", offset_minutes=30
    )
    other_reason = _candidate(
        3, "Implement login retry", "Too coarse to implement", offset_minutes=60
    )

    block = compose_negative_examples([older, newer, other_reason])

    assert block.omitted == 0
    titles_with_reasons = [(e.title, e.reason) for e in block.examples]
    # Same normalized title + same reason -> one entry, the most recent.
    assert ("  Implement   LOGIN retry  ", "Duplicates the auth task") in titles_with_reasons
    assert ("Implement login retry", "Duplicates the auth task") not in titles_with_reasons
    # Same normalized title, different reason -> still two entries.
    assert ("Implement login retry", "Too coarse to implement") in titles_with_reasons
    assert len(block.examples) == 2


def test_total_order_composes_byte_identically_twice_even_when_input_shuffled():
    # Tie-heavy fixture: same marked_at for every row, so marked_at DESC alone
    # leaves ties; the full tiebreak chain (version_number DESC, normalized
    # title, reason) must make the composition deterministic.
    candidates = [
        _candidate(
            version_number=n % 3,
            title=f"Shared moment task {n}",
            reason="same reason for all",
            offset_minutes=0,
        )
        for n in range(8)
    ]

    first = compose_negative_examples(candidates)
    second = compose_negative_examples(candidates)
    assert json.dumps(first.as_template_variables()) == json.dumps(second.as_template_variables())
    assert first.examples == second.examples

    # Input order must not matter either: a shuffled copy composes identically.
    shuffled_first = compose_negative_examples(list(reversed(candidates)))
    shuffled_second = compose_negative_examples(list(reversed(candidates)))
    assert json.dumps(shuffled_first.as_template_variables()) == json.dumps(
        shuffled_second.as_template_variables()
    )
    assert json.dumps(first.as_template_variables()) == json.dumps(
        shuffled_first.as_template_variables()
    )


def test_five_candidates_yield_zero_omitted_after_dedupe():
    # Two of the five share a normalized title and reason, so deduped_total is
    # 4 — still under the cap — and omitted must be 0.
    candidates = [
        _candidate(1, "Wire the retry banner", "Too coarse to implement", offset_minutes=0),
        _candidate(2, "Wire the retry banner", "Too coarse to implement", offset_minutes=10),
        _candidate(2, "Add pagination to listing", "Too coarse to implement", offset_minutes=20),
        _candidate(3, "Build history UI component", "Too coarse to implement", offset_minutes=30),
        _candidate(3, "Persist transactions", "Missing schema", offset_minutes=40),
    ]

    block = compose_negative_examples(candidates)

    assert len(block.examples) == 4
    assert block.omitted == 0


def test_empty_input_yields_empty_block_and_zero_omitted():
    block = compose_negative_examples([])

    assert block.examples == ()
    assert block.omitted == 0


def test_template_variables_are_json_native():
    block = compose_negative_examples(
        [_candidate(2, "Implement login retry", "Duplicates the auth task", offset_minutes=5)]
    )

    variables = block.as_template_variables()

    assert isinstance(variables, list)
    assert len(variables) == 1
    entry = variables[0]
    assert entry["title"] == "Implement login retry"
    assert entry["reason"] == "Duplicates the auth task"
    assert entry["version_number"] == 2
    # marked_at serializes, it does not travel as a datetime.
    assert isinstance(entry["marked_at"], str)
    assert entry["marked_at"] == (_BASE + timedelta(minutes=5)).isoformat()
    # The whole shape survives a JSON round-trip.
    json.dumps(variables)


def test_module_reuses_the_normalizer_and_defines_no_second_one():
    # The import identity: the module's namespace carries (b)'s function object,
    # not a re-import under a different spelling and not a local copy.
    assert negative_examples.normalize_task_title is (task_title_normalizer.normalize_task_title)

    # No second casefold or whitespace spelling may live in the module: the
    # normalizer is the only place the rule lives (b's module docstring).
    source = inspect.getsource(negative_examples)
    assert "casefold" not in source
    assert "lower(" not in source
    assert r"\s" not in source
    assert "re.compile" not in source
