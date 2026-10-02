"""``normalize_task_title`` — the whole matching rule of the D16 repetition read.

The rule is deliberately small: casefold, collapse whitespace runs to one space, strip.
No fuzzy, no vector, no prefix logic (D16). These tables pin the *casefold* half over
the pairs SQL ``lower()`` would get wrong, and the whitespace half that a bare
``lower()`` cannot see at all.
"""

from __future__ import annotations

import pytest

from storico.domain.services.task_title_normalizer import normalize_task_title


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Plain case folding.
        ("Implement login", "implement login"),
        ("IMPLEMENT LOGIN", "implement login"),
        # Internal whitespace runs collapse to one space; edges are stripped.
        ("Implement   login", "implement login"),
        ("Implement\tlogin", "implement login"),
        ("  Implement login  ", "implement login"),
        ("Implement \t\n login", "implement login"),
        # Eszett: casefold expands to "ss", so "ß" and "STRASSE" share one
        # normalized form. ``lower()`` keeps "ß" distinct from "ss" and would
        # answer a different question than the spec's rule.
        ("Straße", "strasse"),
        ("STRASSE", "strasse"),
        # Final sigma: casefold folds "ς" and "Σ" to the same "σ";
        # ``lower()`` leaves "ς" standing.
        ("ς", "σ"),
        ("Σ", "σ"),
        # Dotted capital I: casefold decomposes to "i" + combining dot, the
        # form "İ".lower() happens to share — pinned here so the equivalence
        # survives a Python or normalization-library change.
        ("İ", "i̇"),
    ],
)
def test_the_normalization_table(raw: str, expected: str) -> None:
    assert normalize_task_title(raw) == expected


@pytest.mark.parametrize(
    ("left", "right"),
    [
        # Case-only difference.
        ("Implement Login", "implement login"),
        # Internal whitespace runs only.
        ("Implement  login", "Implement \tlogin"),
        # Eszett vs the SS spelling: ``lower()``-based matching would lose it.
        ("Straße", "STRASSE"),
        # Final vs capital sigma: ``lower()``-based matching would lose it.
        ("ς", "Σ"),
    ],
)
def test_titles_that_differ_only_by_case_or_whitespace_match(left: str, right: str) -> None:
    assert normalize_task_title(left) == normalize_task_title(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Implement login", "Implement logout"),
        ("Implement login", "Implement logins"),
        ("a b", "ab"),
    ],
)
def test_a_one_character_or_edge_difference_never_matches(left: str, right: str) -> None:
    assert normalize_task_title(left) != normalize_task_title(right)
