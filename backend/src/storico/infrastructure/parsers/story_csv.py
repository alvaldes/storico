"""Read raw uploaded CSV bytes into located rows, without judging story content.

This module owns decoding, delimiter and header detection, and file-level limits. It does
no story-field business validation: whatever the source file holds for a recognized column
is passed through verbatim, and the caller decides whether it satisfies the story format.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass

__all__ = [
    "MAX_FILE_BYTES",
    "MAX_ROWS",
    "ParsedStoryCsv",
    "StoryCsvError",
    "StoryCsvRow",
    "parse_story_csv",
]

MAX_ROWS = 1000
MAX_FILE_BYTES = 2 * 1024 * 1024

_PARTS_COLUMNS = ("actor", "feature", "benefit")
_FULL_COLUMNS = ("story", "input", "raw_text")
# Ordered so the choice is deterministic if a header ever carried two candidates. Every
# name in the recognized vocabulary is delimiter-free, so this cannot happen today.
_DELIMITER_PREFERENCE = (",", ";", "\t")
# Used when the header carries no candidate delimiter at all, which means the file has one
# column and its punctuation belongs to the story text. A byte that cannot appear in text
# makes the whole line a single field, while csv's quoting rules still apply — so a quoted
# field is still unwrapped, including one that spans several lines.
_SINGLE_COLUMN = "\x00"
_FAILURE_REASONS = frozenset(
    {"invalid_encoding", "header_unrecognized", "too_many_rows", "empty_file"}
)


class StoryCsvError(Exception):
    """A whole-file failure that stops the upload before any row is produced."""

    def __init__(self, reason: str) -> None:
        if reason not in _FAILURE_REASONS:
            raise ValueError(f"unknown StoryCsvError reason: {reason}")
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class StoryCsvRow:
    """One located data row.

    ``line_number`` is the 1-based physical line where the record **starts** (header is
    line 1). It is the line the user is told to fix, so it points at the beginning of the
    record, not at its last physical line when a quoted field spans several lines.

    In ``parts`` mode ``actor``/``feature``/``benefit`` are populated and ``raw_text``
    holds the optional raw-text column verbatim. In ``full`` mode ``raw_text`` holds the
    story text read from the single ``story``/``input``/``raw_text`` column.

    ``field_count`` is the number of fields ``csv.reader`` produced for this record. It is
    a structural fact only — a count differing from the header's column count means the
    column mapping on this row is unreliable, and judging that is the caller's job.
    """

    line_number: int
    field_count: int
    actor: str | None = None
    feature: str | None = None
    benefit: str | None = None
    raw_text: str | None = None


@dataclass(frozen=True)
class ParsedStoryCsv:
    """A parsed file: the detected ``mode`` and its rows in source order.

    ``expected_field_count`` is the header's column count, so the caller can compare it
    against each row's ``field_count`` and refuse any record whose field count does not
    match — such a row cannot be mapped to columns reliably.
    """

    mode: str
    rows: tuple[StoryCsvRow, ...]
    expected_field_count: int


def parse_story_csv(data: bytes) -> ParsedStoryCsv:
    """Decode, inspect the header and return the file's located rows.

    Raises ``StoryCsvError`` (with a ``reason``) for file-level failures.
    """
    # `data.decode` and `text.splitlines` below are the only places the raw bytes are
    # touched; nothing here judges story content, which the caller owns.
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise StoryCsvError("invalid_encoding") from exc

    if not text.strip():
        raise StoryCsvError("empty_file")

    header_line = text.splitlines()[0]
    reader = csv.reader(io.StringIO(text), delimiter=_detect_delimiter(header_line))

    header = next(reader, None)
    if header is None:
        raise StoryCsvError("empty_file")

    normalized_header = [cell.strip().lower() for cell in header]
    mode = _classify_header(normalized_header)
    positions = {name: index for index, name in enumerate(normalized_header)}

    rows: list[StoryCsvRow] = []
    # ``reader.line_num`` is the last physical line of the record just consumed, so the
    # record about to be read starts on the line after it. Tracking it this way — instead
    # of reading ``line_num`` after the fact — is what keeps the reported line number on
    # the record's *first* line when a quoted field carries an embedded newline, and what
    # keeps blank line skips from shifting every number below them.
    previous_line = reader.line_num
    for raw_row in reader:
        record_start_line = previous_line + 1
        previous_line = reader.line_num
        if not _has_content(raw_row):
            continue
        if len(rows) >= MAX_ROWS:
            raise StoryCsvError("too_many_rows")
        rows.append(
            _build_row(mode, positions, raw_row, record_start_line, field_count=len(raw_row))
        )

    return ParsedStoryCsv(mode=mode, rows=tuple(rows), expected_field_count=len(header))


def _detect_delimiter(header_line: str) -> str:
    """Pick the delimiter from the header line, defaulting to a single-column read.

    Reading it off the header rather than letting ``csv.Sniffer`` guess from the data is a
    correctness requirement, not a shortcut. Sniffing the data made the verdict depend on
    the *story text*: a single-column ``story`` file where every row contained a semicolon
    was read as semicolon-delimited, and every story was silently cut at its first ``;`` —
    ``"As a user I want A0; so that B0"`` arrived as ``"As a user I want A0"``. Downstream
    that surfaced as ``unparsable_story`` on rows the user had written correctly.

    The header is authoritative because the recognized vocabulary is fixed and every name
    in it is delimiter-free. A header containing no candidate therefore means the file has
    **one** column, and that column is returned whole.

    Returning one *whole* column is the part that is easy to get wrong, and it was: choosing
    comma as a fallback for a header with no delimiter split the canonical story text at its
    own commas — ``"As a user, I want A0, so that B0"`` arrived as ``"As a user"`` on every
    row. The canonical story format contains commas by construction, so a one-column upload
    was broken for its primary shape. A delimiter that cannot occur in text keeps the line
    intact and still honours CSV quoting.
    """
    for delimiter in _DELIMITER_PREFERENCE:
        if delimiter in header_line:
            return delimiter
    return _SINGLE_COLUMN


def _classify_header(header: list[str]) -> str:
    """Return ``"parts"`` or ``"full"`` for a normalized header, or fail the file.

    A file carrying all four columns declares its structure explicitly, so the presence of
    ``raw_text`` never demotes a fully specified parts header to full mode.
    """
    present = set(header)
    if set(_PARTS_COLUMNS).issubset(present):
        return "parts"
    if present.intersection(_PARTS_COLUMNS):
        # Some but not all of the parts columns: the file was meant to be parts mode and is
        # missing a column. Classifying it as "full" would read the story text out of a
        # ``raw_text`` column that happens to be there and then blame the stories for not
        # parsing, when the real fault is the missing header. A header of exactly
        # ``actor,raw_text`` used to take that path and report ``actor`` as ``None``.
        raise StoryCsvError("header_unrecognized")
    if present.intersection(_FULL_COLUMNS):
        return "full"
    raise StoryCsvError("header_unrecognized")


def _has_content(row: list[str]) -> bool:
    """A row is blank when every cell is empty, missing, or whitespace only."""
    return any(cell.strip() for cell in row)


def _cell(row: list[str], position: int | None) -> str | None:
    """Read a cell by column position, tolerating a short trailing row."""
    if position is None or position >= len(row):
        return None
    return row[position]


def _build_row(
    mode: str,
    positions: dict[str, int],
    row: list[str],
    line_number: int,
    field_count: int,
) -> StoryCsvRow:
    if mode == "parts":
        return StoryCsvRow(
            line_number=line_number,
            field_count=field_count,
            actor=_cell(row, positions.get("actor")),
            feature=_cell(row, positions.get("feature")),
            benefit=_cell(row, positions.get("benefit")),
            raw_text=_cell(row, positions.get("raw_text")),
        )

    column = next((name for name in _FULL_COLUMNS if name in positions), None)
    return StoryCsvRow(
        line_number=line_number,
        field_count=field_count,
        raw_text=_cell(row, positions.get(column)) if column is not None else None,
    )
