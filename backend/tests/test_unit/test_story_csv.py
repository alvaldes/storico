"""Tests for the story CSV reader.

The reader is the boundary between an arbitrary uploaded file and the rest of the
extraction flow, so these tests pin what it accepts (encoding, delimiter, header shapes)
and where it refuses the whole file. They also pin the located line numbers, because a
downstream error report is only useful if it points at the line the user actually wrote.
"""

from __future__ import annotations

import csv

import pytest

from storico.infrastructure.parsers.story_csv import (
    MAX_ROWS,
    StoryCsvError,
    parse_story_csv,
)


def _csv(*lines: str) -> bytes:
    """Build UTF-8 bytes from logical lines, always ending each file with a newline."""
    return ("\n".join(lines) + "\n").encode("utf-8")


def _reason(data: bytes) -> str:
    """Parse and return the file-level failure reason, or fail the test."""
    with pytest.raises(StoryCsvError) as caught:
        parse_story_csv(data)
    return caught.value.reason


@pytest.mark.unit
def test_a_parts_header_yields_the_three_parts() -> None:
    parsed = parse_story_csv(_csv("actor,feature,benefit", "user,log in,access my account"))

    assert parsed.mode == "parts"
    row = parsed.rows[0]
    assert (row.actor, row.feature, row.benefit) == (
        "user",
        "log in",
        "access my account",
    )


@pytest.mark.unit
def test_a_full_header_is_recognized_and_kept_verbatim() -> None:
    story = "As a user I want to log in"

    parsed = parse_story_csv(_csv("story", story))

    assert parsed.mode == "full"
    assert parsed.rows[0].raw_text == story


@pytest.mark.unit
def test_the_input_and_raw_text_aliases_also_select_full_mode() -> None:
    for column in ("input", "raw_text"):
        parsed = parse_story_csv(_csv(column, "As a user I want to log in"))

        assert parsed.mode == "full"
        assert parsed.rows[0].raw_text == "As a user I want to log in"


@pytest.mark.unit
def test_a_header_with_all_four_columns_stays_in_parts_mode() -> None:
    parsed = parse_story_csv(_csv("actor,feature,benefit,raw_text", "user,log in,access,As a user"))

    assert parsed.mode == "parts"
    assert parsed.rows[0].raw_text == "As a user"


@pytest.mark.unit
def test_a_raw_text_column_in_parts_mode_passes_through_verbatim() -> None:
    raw = "As a user I want to log in "

    parsed = parse_story_csv(_csv("actor,feature,benefit,raw_text", f"user,log in,access,{raw}"))

    assert parsed.rows[0].raw_text == raw


@pytest.mark.unit
def test_a_utf8_bom_is_stripped_from_the_header() -> None:
    data = "actor,feature,benefit\nuser,log in,access\n".encode("utf-8-sig")

    parsed = parse_story_csv(data)

    assert parsed.mode == "parts"
    assert parsed.rows[0].actor == "user"


@pytest.mark.unit
def test_header_names_are_matched_case_insensitively() -> None:
    parsed = parse_story_csv(_csv("Actor,FEATURE,Benefit", "user,log in,access"))

    assert parsed.mode == "parts"
    assert parsed.rows[0].actor == "user"


@pytest.mark.unit
def test_header_names_are_trimmed_of_surrounding_whitespace() -> None:
    parsed = parse_story_csv(_csv("  actor  , feature,benefit ", "user,log in,access"))

    assert parsed.mode == "parts"
    assert parsed.rows[0].feature == "log in"


@pytest.mark.unit
def test_a_semicolon_delimited_file_is_detected() -> None:
    parsed = parse_story_csv(_csv("actor;feature;benefit", "user;log in;access"))

    assert parsed.mode == "parts"
    assert parsed.rows[0].benefit == "access"


@pytest.mark.unit
def test_a_tab_delimited_file_is_detected() -> None:
    parsed = parse_story_csv(_csv("actor\tfeature\tbenefit", "user\tlog in\taccess"))

    assert parsed.mode == "parts"
    assert parsed.rows[0].feature == "log in"


@pytest.mark.unit
def test_a_single_column_story_file_is_not_split_at_its_commas() -> None:
    """A one-column file keeps each line whole, commas and all.

    This is the primary shape of a one-column upload, and it was broken: with no delimiter in
    the header the fallback was comma, which split the canonical story text at its own commas
    and left every row as ``"As a user"``. The canonical format contains commas by
    construction, so this was not an edge case.

    The semicolon test below passed while this was broken, which is the point of having both:
    a fix aimed at one delimiter says nothing about the others, and the canonical text carries
    commas rather than semicolons.
    """
    stories = [f"As a user, I want A{i}, so that B{i}" for i in range(30)]

    parsed = parse_story_csv(_csv("story", *stories))

    assert parsed.mode == "full"
    assert [row.raw_text for row in parsed.rows] == stories


@pytest.mark.unit
def test_a_single_column_row_may_be_quoted() -> None:
    """Quoting is still honoured when the file has one column, so Excel output works."""
    story = "As a user, I want to log in, so that I can access my account"

    parsed = parse_story_csv(_csv("story", f'"{story}"'))

    assert parsed.rows[0].raw_text == story


@pytest.mark.unit
def test_a_quoted_multiline_row_in_a_single_column_file_keeps_its_first_line() -> None:
    story = "As a user, I want to log in,\nso that I can access my account"

    parsed = parse_story_csv(_csv("story", f'"{story}"', "As a user, I want B, so that C"))

    assert [row.line_number for row in parsed.rows] == [2, 4]
    assert parsed.rows[0].raw_text == story


@pytest.mark.unit
def test_a_story_text_containing_a_semicolon_is_not_split() -> None:
    """A single-column file must not be read as semicolon-delimited.

    The delimiter used to come from ``csv.Sniffer`` reading the *data*, so a file whose
    stories each carried a ``;`` was read as two columns and every story was cut at its
    first semicolon. Thirty rows reproduced it on every single row.
    """
    stories = [f"As a user I want A{i}; so that B{i}" for i in range(30)]

    parsed = parse_story_csv(_csv("story", *stories))

    assert parsed.mode == "full"
    assert [row.raw_text for row in parsed.rows] == stories


@pytest.mark.unit
def test_a_tab_inside_a_single_column_story_stays_text() -> None:
    parsed = parse_story_csv(_csv("story", "As a user\tI want to log in"))

    assert parsed.rows[0].raw_text == "As a user\tI want to log in"


@pytest.mark.unit
def test_a_row_with_more_fields_than_the_header_reports_both_counts() -> None:
    """An unquoted canonical story under a parts header splits into extra fields.

    A canonical story carries commas by construction, so pasted under a comma header
    without quoting each comma adds a field: 'As a user, I want A, B, so that C' reads
    as 4 fields, maps positionally to a garbage story and silently drops the rest. The
    parser reports the structural fact (4 fields against a 3-column header); judging it
    is the domain's job.
    """
    parsed = parse_story_csv(_csv("actor,feature,benefit", "As a user, I want A, B, so that C"))

    assert parsed.expected_field_count == 3
    row = parsed.rows[0]
    assert row.field_count == 4


@pytest.mark.unit
def test_a_single_column_file_reports_one_field_for_every_row() -> None:
    stories = [f"As a user, I want A{i}, so that B{i}" for i in range(5)]

    parsed = parse_story_csv(_csv("story", *stories))

    assert parsed.expected_field_count == 1
    assert [row.field_count for row in parsed.rows] == [1] * len(stories)


@pytest.mark.unit
def test_a_quoted_field_with_the_delimiter_counts_as_one_field() -> None:
    """A properly quoted canonical story row must not trip the count.

    The canonical format contains commas by construction, so a quoted upload is the
    correct way to write a parts-header row and the counts must agree.
    """
    parsed = parse_story_csv(
        _csv("actor,feature,benefit", '"user, the admin","log in, hard","access, at last"')
    )

    assert parsed.expected_field_count == 3
    assert parsed.rows[0].field_count == 3


@pytest.mark.unit
def test_a_row_with_fewer_fields_than_the_header_reports_its_smaller_count() -> None:
    parsed = parse_story_csv(_csv("actor,feature,benefit", "user,log in"))

    assert parsed.expected_field_count == 3
    assert parsed.rows[0].field_count == 2


@pytest.mark.unit
def test_a_partial_parts_header_fails_the_file() -> None:
    """One parts column without the others is a missing column, not a full-mode file.

    ``actor,raw_text`` used to be classified as full mode, which read the story text out of
    ``raw_text`` and reported ``actor`` as ``None`` — blaming the stories instead of naming
    the missing header.
    """
    assert _reason(_csv("actor,raw_text", "user,As a user I want A")) == ("header_unrecognized")
    assert _reason(_csv("feature,benefit", "log in,access")) == "header_unrecognized"


@pytest.mark.unit
def test_line_numbers_survive_a_blank_line_in_the_middle() -> None:
    data = _csv(
        "actor,feature,benefit",
        "user,log in,access",
        "",
        "guest,browse,catalog",
    )

    parsed = parse_story_csv(data)

    assert [row.line_number for row in parsed.rows] == [2, 4]
    assert parsed.rows[1].actor == "guest"


@pytest.mark.unit
def test_a_quoted_field_with_an_embedded_newline_reports_the_first_line() -> None:
    """The reported line is where the record starts, not where it ends.

    ``reader.line_num`` after the fact points at the record's last physical line, which for
    a quoted multi-line field is one line past where the user should look — and collides
    with the next row's number.
    """
    data = _csv(
        "actor,feature,benefit",
        '"us\ner",log in,access',
        "guest,browse,catalog",
    )

    parsed = parse_story_csv(data)

    assert [row.line_number for row in parsed.rows] == [2, 4]
    assert parsed.rows[0].actor == "us\ner"
    assert parsed.rows[1].actor == "guest"


@pytest.mark.unit
def test_a_file_of_exactly_the_row_cap_is_accepted() -> None:
    lines = ["actor,feature,benefit"]
    lines += [f"user{i},feature{i},benefit{i}" for i in range(MAX_ROWS)]

    parsed = parse_story_csv(_csv(*lines))

    assert len(parsed.rows) == MAX_ROWS
    assert parsed.rows[-1].line_number == MAX_ROWS + 1


@pytest.mark.unit
def test_one_row_past_the_cap_fails_the_file() -> None:
    lines = ["actor,feature,benefit"]
    lines += [f"user{i},feature{i},benefit{i}" for i in range(MAX_ROWS + 1)]

    assert _reason(_csv(*lines)) == "too_many_rows"


@pytest.mark.unit
def test_an_unknown_header_fails_the_file() -> None:
    assert _reason(_csv("title,notes", "a,b")) == "header_unrecognized"


@pytest.mark.unit
def test_invalid_utf8_fails_the_file() -> None:
    assert _reason(b"actor,feature,benefit\n\xff\xfe,log in,access\n") == ("invalid_encoding")


@pytest.mark.unit
def test_an_empty_file_fails_the_file() -> None:
    assert _reason(b"") == "empty_file"


@pytest.mark.unit
def test_classic_mac_cr_only_line_endings_parse() -> None:
    """A file with lone CR line endings parses instead of raising csv.Error.

    With StringIO's default newline handling the CR reached the reader inside a field
    and the upload died as a 500. With ``newline=""`` the reader terminates records on
    ``\\r`` itself: the file holds two records — the header and one data row — and both
    must parse.
    """
    parsed = parse_story_csv(b"actor,feature,benefit\ruser,log in,access\r")

    assert parsed.mode == "parts"
    assert parsed.expected_field_count == 3
    assert [(row.line_number, row.actor, row.feature, row.benefit) for row in parsed.rows] == [
        (2, "user", "log in", "access")
    ]


@pytest.mark.unit
def test_a_field_of_200_000_characters_is_read_whole_not_raised() -> None:
    """A single field over csv's old 131072-char limit is read, not raised.

    The module raises csv's field-size limit to ``MAX_FILE_BYTES`` at import, so the
    oversized field comes back whole and the domain layer can report ``too_long`` with
    its exact length instead of the parser failing the file (or the 500 it used to be).
    """
    story = "x" * 200_000

    parsed = parse_story_csv(b"story\n" + story.encode("utf-8") + b"\n")

    assert parsed.mode == "full"
    assert parsed.rows[0].raw_text == story
    assert len(parsed.rows[0].raw_text) == 200_000


@pytest.mark.unit
def test_a_csv_error_beyond_every_guard_reports_malformed_csv() -> None:
    """The backstop turns any residual csv.Error into a file-level 422 reason.

    Real input can no longer reach the backstop (``newline=""`` and the raised field
    limit cover the measured failures), so the test forces a ``csv.Error`` by lowering
    the field-size limit. That limit is process-global state shared with every other
    csv consumer in the test process, so the test mutates it only inside try/finally
    and always restores the original value it read first.
    """
    original_limit = csv.field_size_limit()
    try:
        csv.field_size_limit(10)
        with pytest.raises(StoryCsvError) as caught:
            parse_story_csv(b"story\n" + b"x" * 50 + b"\n")
        assert caught.value.reason == "malformed_csv"
    finally:
        csv.field_size_limit(original_limit)


@pytest.mark.unit
def test_a_whitespace_only_file_is_empty() -> None:
    assert _reason(b"   \n\n") == "empty_file"
