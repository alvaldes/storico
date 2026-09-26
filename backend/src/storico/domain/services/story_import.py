"""Pure validation for a story CSV import: errors, duplicates and stories to create.

This module owns the per-row business rules for an uploaded story file. It performs no
I/O, knows nothing about FastAPI, SQLAlchemy or the CSV reader (the caller maps parsed
rows into :class:`ImportRow`), and writes nothing: it returns an
:class:`ImportReport` and the caller decides atomicity and persistence.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

__all__ = [
    "CANONICAL_RAW_TEXT_TEMPLATE",
    "FIELD_LIMITS",
    "ImportReport",
    "ImportRow",
    "NewStory",
    "RowDuplicate",
    "RowError",
    "StoryParts",
    "build_raw_text",
    "parse_user_story",
    "validate_import",
]

# Hardcoded English on purpose: this string is the prompt text sent to the LLM, so a
# translation refactor must never be able to move it. It is pinned byte for byte by a
# unit test.
CANONICAL_RAW_TEXT_TEMPLATE = "As a(n) {actor}, I want {feature}, so that {benefit}"

# Same limits as the existing Pydantic story schema.
FIELD_LIMITS = {"actor": 100, "feature": 300, "benefit": 300, "raw_text": 2000}

_PART_FIELDS = ("actor", "feature", "benefit")

# Direct port of the frontend regex (same variants, same tolerance): accepts "As a",
# "As an" and "As a(n)", optional commas around the connectors, case-insensitive. The
# frontend slices over-length parts on its own path; that behaviour is deliberately NOT
# ported here — the caller decides what over-length means.
_STORY_PATTERN = re.compile(
    r"As\s+an?\s*(\(n\))?\s*(.+?)\s*,?\s*I\s+want\s+(.+?)\s*,?\s*so\s+that\s+(.+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ImportRow:
    """The caller-mapped input for one row: optional cells plus its located line."""

    line_number: int
    actor: str | None = None
    feature: str | None = None
    benefit: str | None = None
    raw_text: str | None = None


@dataclass(frozen=True)
class StoryParts:
    """The three trimmed parts of a story."""

    actor: str
    feature: str
    benefit: str


@dataclass(frozen=True)
class RowError:
    """One blocking problem on one row. At most one error is reported per row."""

    line_number: int
    reason: str
    field: str | None = None
    actual_length: int | None = None
    max_length: int | None = None


@dataclass(frozen=True)
class RowDuplicate:
    """A row identical to an existing story or to an earlier row of the same upload.

    ``reason`` is ``"duplicate"`` for a story already in the project and
    ``"duplicate_in_file"`` for a repeat inside this upload. It has no default on
    purpose: the field is set explicitly at both call sites, because a default labelled
    every project duplicate ``duplicate_in_file`` while leaving ``first_line`` empty.
    """

    line_number: int
    reason: str
    existing_story_id: str | None = None
    first_line: int | None = None


@dataclass(frozen=True)
class NewStory:
    """A story the caller may create, with all four fields populated."""

    line_number: int
    actor: str
    feature: str
    benefit: str
    raw_text: str


@dataclass(frozen=True)
class ImportReport:
    """The outcome of validating one upload. The service writes nothing."""

    total_rows: int
    mode: str
    errors: tuple[RowError, ...]
    duplicates: tuple[RowDuplicate, ...]
    new_stories: tuple[NewStory, ...]

    @property
    def blocked(self) -> bool:
        """Errors block the whole import; duplicates are only skipped and reported."""
        return bool(self.errors)


def build_raw_text(actor: str, feature: str, benefit: str) -> str:
    """Render the canonical full text from three already-trimmed parts."""
    return CANONICAL_RAW_TEXT_TEMPLATE.format(actor=actor, feature=feature, benefit=benefit)


def parse_user_story(text: str) -> StoryParts | None:
    """Split a full story text into its three trimmed parts, or ``None`` when it does
    not parse. Nothing is truncated here.
    """
    match = _STORY_PATTERN.search(text)
    if match is None:
        return None
    return StoryParts(
        actor=match.group(2).strip(),
        feature=match.group(3).strip(),
        benefit=match.group(4).strip(),
    )


def validate_import(
    rows: Iterable[ImportRow],
    mode: str,
    existing: Mapping[tuple[str, str, str], str],
) -> ImportReport:
    """Validate one upload and classify every row.

    ``existing`` maps ``(actor, feature, benefit)`` — exact strings, no case or
    whitespace normalisation — to an existing story id. A row carrying an error is
    never also reported as a duplicate: errors take precedence. Only error-free rows
    join the duplicate decision.
    """
    if mode not in ("parts", "full"):
        raise ValueError(f"unknown import mode: {mode}")

    row_list = tuple(rows)
    errors: list[RowError] = []
    duplicates: list[RowDuplicate] = []
    new_stories: list[NewStory] = []
    # (actor, feature, benefit) -> line number of the first error-free row with that key.
    seen: dict[tuple[str, str, str], int] = {}

    for row in row_list:
        error = _first_error(row, mode)
        if error is not None:
            errors.append(error)
            continue

        key = _story_key(row, mode)
        existing_id = existing.get(key)
        if existing_id is not None:
            duplicates.append(
                RowDuplicate(
                    line_number=row.line_number,
                    reason="duplicate",
                    existing_story_id=existing_id,
                )
            )
            continue

        first_line = seen.get(key)
        if first_line is not None:
            duplicates.append(
                RowDuplicate(
                    line_number=row.line_number,
                    reason="duplicate_in_file",
                    first_line=first_line,
                )
            )
            continue

        seen[key] = row.line_number
        new_stories.append(_build_new_story(row, mode))

    return ImportReport(
        total_rows=len(row_list),
        mode=mode,
        errors=tuple(errors),
        duplicates=tuple(duplicates),
        new_stories=tuple(new_stories),
    )


def _first_error(row: ImportRow, mode: str) -> RowError | None:
    """Return the first problem on the row, in the documented per-field order."""
    if mode == "parts":
        for field in _PART_FIELDS:
            error = _required_field_error(row, field)
            if error is not None:
                return error
        return _optional_raw_text_error(row)
    return _full_text_error(row)


def _required_field_error(row: ImportRow, field: str) -> RowError | None:
    value = getattr(row, field)
    if value is None:
        return RowError(line_number=row.line_number, reason="missing_field", field=field)
    trimmed = value.strip()
    if not trimmed:
        return RowError(line_number=row.line_number, reason="empty_field", field=field)
    return _length_error(row, field, trimmed)


def _optional_raw_text_error(row: ImportRow) -> RowError | None:
    # An absent or blank raw-text cell is not an error in parts mode: the canonical
    # text is built from the parts instead.
    value = row.raw_text
    if value is None or not value.strip():
        return None
    return _length_error(row, "raw_text", value.strip())


def _full_text_error(row: ImportRow) -> RowError | None:
    if row.raw_text is None:
        return RowError(line_number=row.line_number, reason="missing_field", field="raw_text")
    # Trimmed once here and reused for the emptiness check, the length check and the
    # parse, so all three reason about the same string. `StoryForm` stores
    # `fullText.trim()` as raw_text, so leaving the ends in place would both diverge from
    # the form and reject a story of exactly the limit that arrived with a trailing
    # space — 2000 characters plus one space measured as 2001 and failed `too_long`.
    text = row.raw_text.strip()
    if not text:
        return RowError(line_number=row.line_number, reason="empty_field", field="raw_text")
    error = _length_error(row, "raw_text", text)
    if error is not None:
        return error
    parts = parse_user_story(text)
    if parts is None:
        return RowError(line_number=row.line_number, reason="unparsable_story", field="raw_text")
    for field, value in zip(_PART_FIELDS, (parts.actor, parts.feature, parts.benefit)):
        error = _length_error(row, field, value)
        if error is not None:
            return error
    return None


def _length_error(row: ImportRow, field: str, value: str) -> RowError | None:
    max_length = FIELD_LIMITS[field]
    actual = len(value)
    if actual > max_length:
        return RowError(
            line_number=row.line_number,
            reason="too_long",
            field=field,
            actual_length=actual,
            max_length=max_length,
        )
    return None


def _story_key(row: ImportRow, mode: str) -> tuple[str, str, str]:
    parts = _parts_of(row, mode)
    return (parts.actor, parts.feature, parts.benefit)


def _parts_of(row: ImportRow, mode: str) -> StoryParts:
    """Return the row's trimmed parts.

    Only valid on rows that already passed ``_first_error``, which guarantees the cells
    are present in parts mode and the text parses in full mode.
    """
    if mode == "full":
        parts = parse_user_story(row.raw_text or "")
        if parts is None:
            raise ValueError(
                f"line {row.line_number}: full-mode text did not parse; "
                "validate with _first_error before calling _parts_of"
            )
        return parts
    return StoryParts(
        actor=row.actor.strip(),  # type: ignore[union-attr]
        feature=row.feature.strip(),  # type: ignore[union-attr]
        benefit=row.benefit.strip(),  # type: ignore[union-attr]
    )


def _build_new_story(row: ImportRow, mode: str) -> NewStory:
    parts = _parts_of(row, mode)
    if mode == "full":
        # Trimmed to agree with `_full_text_error` and with `StoryForm`, which stores
        # `fullText.trim()`; this string is the prompt sent to the LLM.
        raw_text: str = (row.raw_text or "").strip()
    else:
        cell = row.raw_text
        # The provided cell is kept as curated text, trimmed at the ends only so the
        # stored value and the length check agree. Internal newlines survive.
        raw_text = (
            cell.strip()
            if cell is not None and cell.strip()
            else build_raw_text(parts.actor, parts.feature, parts.benefit)
        )
    return NewStory(
        line_number=row.line_number,
        actor=parts.actor,
        feature=parts.feature,
        benefit=parts.benefit,
        raw_text=raw_text,
    )
