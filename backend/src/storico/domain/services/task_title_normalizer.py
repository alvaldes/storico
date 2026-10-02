"""The task-title normalizer — the whole matching rule of the D16 repetition read.

One function: casefold, collapse whitespace runs to one space, strip. No fuzzy,
no vector, no prefix logic (D16): the backend match is an exact comparison of
normalized titles, and this module is the only place the rule lives.

``casefold`` is chosen over ``lower`` deliberately — Postgres ``LOWER()`` is not
``casefold`` for ``ß`` (vs "SS"), final ``ς`` (vs ``σ``) and friends — which is
why the match runs in Python after the SQL has narrowed to the story's other
versions, instead of in SQL.
"""

from __future__ import annotations

import re

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_task_title(text: str) -> str:
    """Normalize a task title for the exact D16 equality comparison."""
    return _WHITESPACE_RUN.sub(" ", text).strip().casefold()
