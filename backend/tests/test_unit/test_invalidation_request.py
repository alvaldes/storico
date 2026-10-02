"""Unit contract for ``CreateInvalidationRequest`` — the mark's reason rule.

The blank-reason rule lives in a Pydantic ``field_validator`` (task 5.1 of
extraction-versioning) because Python whitespace is wider than the column's
``CHECK``: the table refuses an empty or trim-empty reason
(``ck_task_invalidations_reason_not_blank``, ``length(trim(reason)) > 0``), but
``"\t\n"`` is non-empty as a Python string and as a SQL length, and only a
Python-side strip sees it as blank. The validator is therefore the place the
blank rule can refuse all three shapes before the route is ever reached — a
blank reason answers 422 ``REQUEST_VALIDATION_FAILED`` through the framework's
body-validation handler, and the app handler never sees one.

The 500 bound is the column's ``String(500)``; the schema mirrors it with
``Field(..., max_length=500)`` so an over-long reason is refused at body
validation with the same 422 instead of an ``IntegrityError`` 500 at insert.

Pure unit test: no API client, no database.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from storico.api.schemas.task import CreateInvalidationRequest


@pytest.mark.parametrize("reason", ["", "   ", "\t\n"])
def test_a_blank_reason_is_refused(reason: str) -> None:
    """Empty, spaces-only and tab/newline-only reasons all refuse.

    ``"\t\n"`` is the shape the column's ``CHECK`` cannot see — Python
    whitespace is wider than ``length(trim(...))`` — so it is pinned next to
    the two shapes the database would also refuse.
    """
    with pytest.raises(ValidationError):
        CreateInvalidationRequest(reason=reason)


def test_a_reason_at_the_column_bound_is_accepted() -> None:
    """A non-blank reason of exactly 500 characters is the column's limit."""
    reason = "x" * 500
    request = CreateInvalidationRequest(reason=reason)
    assert request.reason == reason


def test_a_reason_past_the_column_bound_is_refused() -> None:
    """501 characters refuse at body validation, before any insert exists."""
    with pytest.raises(ValidationError):
        CreateInvalidationRequest(reason="x" * 501)
