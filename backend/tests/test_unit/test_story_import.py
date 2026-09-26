"""Tests for the pure story-import validation core."""

from __future__ import annotations

from pathlib import Path

import pytest

from storico.domain.services import story_import
from storico.domain.services.story_import import (
    CANONICAL_RAW_TEXT_TEMPLATE,
    FIELD_LIMITS,
    ImportRow,
    StoryParts,
    parse_user_story,
    validate_import,
)


@pytest.mark.unit
@pytest.mark.parametrize("article", ["As a", "As an", "As a(n)"])
def test_the_three_article_variants_parse(article: str) -> None:
    text = f"{article} user, I want to log in, so that I can access my account"

    parts = parse_user_story(text)

    assert parts == StoryParts(actor="user", feature="to log in", benefit="I can access my account")


@pytest.mark.unit
def test_a_story_without_commas_also_parses() -> None:
    parts = parse_user_story("As an admin I want to export CSV so that I can share reports")

    assert parts == StoryParts(
        actor="admin", feature="to export CSV", benefit="I can share reports"
    )


@pytest.mark.unit
def test_a_story_without_so_that_does_not_parse() -> None:
    assert parse_user_story("As a user, I want to log in.") is None


@pytest.mark.unit
def test_parse_user_story_returns_none_on_junk() -> None:
    assert parse_user_story("hello world, nothing to see here") is None


@pytest.mark.unit
def test_the_canonical_template_is_pinned_byte_for_byte() -> None:
    assert CANONICAL_RAW_TEXT_TEMPLATE == "As a(n) {actor}, I want {feature}, so that {benefit}"


@pytest.mark.unit
def test_the_canonical_template_expands_exactly() -> None:
    expanded = CANONICAL_RAW_TEXT_TEMPLATE.format(
        actor="user", feature="to log in", benefit="I can access my account"
    )

    assert expanded == "As a(n) user, I want to log in, so that I can access my account"


@pytest.mark.unit
def test_parts_mode_builds_the_canonical_raw_text_when_the_cell_is_absent() -> None:
    report = validate_import(
        [ImportRow(1, "user", "to log in", "I can access my account")], "parts", {}
    )

    assert not report.errors
    story = report.new_stories[0]
    assert story.raw_text == "As a(n) user, I want to log in, so that I can access my account"
    assert (story.actor, story.feature, story.benefit) == (
        "user",
        "to log in",
        "I can access my account",
    )


@pytest.mark.unit
def test_parts_mode_trims_the_provided_raw_text_at_its_ends() -> None:
    """The curated cell is kept, with only its ends trimmed.

    Storing it untrimmed made the length check disagree with the stored value, and
    diverged from `StoryForm`, which stores `fullText.trim()`. Internal newlines survive.
    """
    raw = "  As a user, I want to log in,\nso that I can access my account  "

    report = validate_import([ImportRow(1, "user", "log in", "access", raw_text=raw)], "parts", {})

    assert report.new_stories[0].raw_text == raw.strip()
    assert "\n" in report.new_stories[0].raw_text


@pytest.mark.unit
def test_parts_mode_tolerates_a_blank_raw_text_cell_by_building_the_canonical_text() -> None:
    report = validate_import(
        [ImportRow(1, "user", "log in", "access", raw_text="   ")], "parts", {}
    )

    assert not report.errors
    assert report.new_stories[0].raw_text == "As a(n) user, I want log in, so that access"


@pytest.mark.unit
def test_full_mode_stores_the_text_trimmed() -> None:
    """Full-mode text is stored trimmed, matching `StoryForm`'s `fullText.trim()`."""
    report = validate_import(
        [ImportRow(2, raw_text="  As a user, I want to log in, so that I can access  ")],
        "full",
        {},
    )

    assert report.new_stories[0].raw_text == "As a user, I want to log in, so that I can access"


@pytest.mark.unit
def test_padding_cannot_push_a_valid_full_story_over_the_limit() -> None:
    """The length check runs on the trimmed text, so surrounding whitespace cannot fail a
    valid row.

    The check used to measure the raw cell, so a story that fitted comfortably but arrived
    with padding was reported `too_long` on `raw_text` — measured 2100 for a 57-character
    story.
    """
    text = "As a user, I want to log in, so that I can access my account"
    padded = (" " * 1500) + text + (" " * 1500)
    assert len(padded) > FIELD_LIMITS["raw_text"]

    report = validate_import([ImportRow(2, raw_text=padded)], "full", {})

    assert report.errors == ()
    assert report.new_stories[0].raw_text == text


@pytest.mark.unit
@pytest.mark.parametrize("field", ["actor", "feature", "benefit", "raw_text"])
def test_each_field_over_its_limit_reports_too_long(field: str) -> None:
    limit = FIELD_LIMITS[field]
    values: dict[str, str] = {"actor": "user", "feature": "log in", "benefit": "access"}
    values[field] = "x" * (limit + 1)

    report = validate_import([ImportRow(7, **values)], "parts", {})  # type: ignore[arg-type]

    assert report.blocked
    error = report.errors[0]
    assert error.reason == "too_long"
    assert error.field == field
    assert error.actual_length == limit + 1
    assert error.max_length == limit
    assert error.line_number == 7


@pytest.mark.unit
def test_a_blank_cell_is_empty_field_and_an_absent_cell_is_missing_field() -> None:
    report = validate_import(
        [
            ImportRow(1, actor="  ", feature="log in", benefit="access"),
            ImportRow(2, feature="log in", benefit="access"),
        ],
        "parts",
        {},
    )

    assert report.blocked
    assert [(error.field, error.reason) for error in report.errors] == [
        ("actor", "empty_field"),
        ("actor", "missing_field"),
    ]


@pytest.mark.unit
def test_full_mode_unparsable_text_reports_unparsable_story_on_that_line() -> None:
    report = validate_import([ImportRow(3, raw_text="just some words, no so that")], "full", {})

    assert report.blocked
    error = report.errors[0]
    assert error.reason == "unparsable_story"
    assert error.line_number == 3


@pytest.mark.unit
def test_a_row_with_several_problems_reports_exactly_one_error() -> None:
    report = validate_import(
        [ImportRow(1, actor="", feature=None, benefit="x" * (FIELD_LIMITS["benefit"] + 1))],
        "parts",
        {},
    )

    assert len(report.errors) == 1
    assert report.errors[0].field == "actor"
    assert report.errors[0].reason == "empty_field"


@pytest.mark.unit
def test_a_project_duplicate_carries_the_existing_id_and_is_not_an_error() -> None:
    report = validate_import(
        [ImportRow(1, "user", "log in", "access")],
        "parts",
        {("user", "log in", "access"): "story-42"},
    )

    assert not report.blocked
    assert report.errors == ()
    assert report.new_stories == ()
    duplicate = report.duplicates[0]
    assert duplicate.reason == "duplicate"
    assert duplicate.first_line is None
    assert duplicate.existing_story_id == "story-42"
    assert duplicate.line_number == 1


@pytest.mark.unit
def test_an_in_file_duplicate_reports_duplicate_in_file_with_the_first_line() -> None:
    report = validate_import(
        [
            ImportRow(2, "user", "log in", "access"),
            ImportRow(5, "user", "log in", "access"),
        ],
        "parts",
        {},
    )

    assert not report.blocked
    assert report.errors == ()
    assert len(report.new_stories) == 1
    duplicate = report.duplicates[0]
    assert duplicate.reason == "duplicate_in_file"
    assert duplicate.first_line == 2
    assert duplicate.line_number == 5


@pytest.mark.unit
def test_an_errored_row_is_never_also_reported_as_a_duplicate() -> None:
    report = validate_import(
        [
            ImportRow(1, "user", "log in", "access"),
            ImportRow(2, "user", "log in", None),
        ],
        "parts",
        {},
    )

    assert len(report.errors) == 1
    assert report.errors[0].line_number == 2
    assert report.duplicates == ()


@pytest.mark.unit
def test_user_and_user_are_different_stories() -> None:
    report = validate_import(
        [
            ImportRow(1, "User", "log in", "access"),
            ImportRow(2, "user", "log in", "access"),
        ],
        "parts",
        {},
    )

    assert not report.blocked
    assert report.duplicates == ()
    assert len(report.new_stories) == 2


@pytest.mark.unit
def test_revalidating_with_the_first_pass_new_stories_yields_all_duplicates() -> None:
    rows = [
        ImportRow(1, "user", "log in", "access"),
        ImportRow(2, "guest", "browse", "the catalog"),
    ]

    first = validate_import(rows, "parts", {})
    assert not first.errors
    assert len(first.new_stories) == 2

    existing = {
        (story.actor, story.feature, story.benefit): f"story-{index}"
        for index, story in enumerate(first.new_stories)
    }
    second = validate_import(rows, "parts", existing)

    assert second.errors == ()
    assert second.new_stories == ()
    assert len(second.duplicates) == 2
    assert second.duplicates[0].existing_story_id == "story-0"
    assert second.duplicates[1].existing_story_id == "story-1"


@pytest.mark.unit
def test_the_report_exposes_totals_mode_and_blocked() -> None:
    report = validate_import(
        [
            ImportRow(1, "user", "log in", "access"),
            ImportRow(2, "user", "log in", None),
        ],
        "parts",
        {},
    )

    assert report.total_rows == 2
    assert report.mode == "parts"
    assert report.blocked


@pytest.mark.unit
def test_a_field_count_mismatch_reports_exactly_one_error_and_blocks_the_row() -> None:
    report = validate_import(
        [ImportRow(1, "user", "log in", "access", field_count=4, expected_field_count=3)],
        "parts",
        {},
    )

    assert report.blocked
    assert report.new_stories == ()
    assert len(report.errors) == 1
    error = report.errors[0]
    assert error.reason == "field_count_mismatch"
    assert error.line_number == 1
    assert error.observed_count == 4
    assert error.expected_count == 3


@pytest.mark.unit
def test_the_mismatch_wins_over_a_field_problem_on_the_same_row() -> None:
    """When the column mapping is unreliable, field-level complaints are noise.

    A row both ragged and carrying an over-long benefit reports exactly one error: the
    mismatch, not the length.
    """
    report = validate_import(
        [
            ImportRow(
                3,
                "user",
                "log in",
                "x" * (FIELD_LIMITS["benefit"] + 1),
                field_count=4,
                expected_field_count=3,
            )
        ],
        "parts",
        {},
    )

    assert len(report.errors) == 1
    error = report.errors[0]
    assert error.reason == "field_count_mismatch"
    assert error.observed_count == 4
    assert error.expected_count == 3


@pytest.mark.unit
def test_a_row_with_matching_counts_reports_no_mismatch() -> None:
    report = validate_import(
        [ImportRow(1, "user", "log in", "access", field_count=3, expected_field_count=3)],
        "parts",
        {},
    )

    assert not report.blocked
    assert report.errors == ()
    assert len(report.new_stories) == 1


@pytest.mark.unit
def test_rows_without_counts_are_not_checked_for_a_mismatch() -> None:
    """Existing callers that do not supply the counts keep working unchanged."""
    report = validate_import(
        [
            ImportRow(1, "user", "log in", "access"),
            ImportRow(2, feature="log in", benefit="access"),
        ],
        "parts",
        {},
    )

    assert [(error.reason, error.field) for error in report.errors] == [
        ("missing_field", "actor"),
    ]


@pytest.mark.unit
def test_the_unquoted_canonical_story_that_used_to_be_written_is_now_refused() -> None:
    """The exact silent-corruption case is now a blocking row error.

    A CSV whose header declares ``actor,feature,benefit`` and whose data row carries an
    unquoted canonical story splits at the story's own commas: the first fields map
    positionally to garbage values and whatever overflows the header is dropped, with
    nothing reported. The counts here reproduce that measured shape — 4 fields read by
    ``csv.reader`` against a 3-column header — and the row is now refused with nothing
    created.
    """
    report = validate_import(
        [
            ImportRow(
                2,
                actor="As a user",
                feature="I want A",
                benefit="so that B",
                field_count=4,
                expected_field_count=3,
            )
        ],
        "parts",
        {},
    )

    assert report.blocked
    assert report.new_stories == ()
    assert [(error.reason, error.line_number) for error in report.errors] == [
        ("field_count_mismatch", 2)
    ]


@pytest.mark.unit
@pytest.mark.parametrize(
    ("actor", "feature", "benefit"),
    [
        ("user", "log in", "access"),
        ("admin, senior", "export, save", "share, collaborate"),
        # A pasted prefix: the joined text still lacks "I want", so it does not parse.
        ("As a user", "log in", "access"),
        ("user", "log in", "so that users retry"),
        ("power user", "I want reports", "see data"),
    ],
)
def test_legitimate_part_rows_are_not_flagged_as_a_whole_story(
    actor: str, feature: str, benefit: str
) -> None:
    """False-positive guards: only a row that joins into a parseable story is refused."""
    report = validate_import([ImportRow(1, actor, feature, benefit)], "parts", {})

    assert not any(error.reason == "parts_look_like_a_full_story" for error in report.errors)
    story = report.new_stories[0]
    assert (story.actor, story.feature, story.benefit) == (actor, feature, benefit)


@pytest.mark.unit
def test_a_pasted_canonical_story_split_by_its_own_commas_is_refused_not_silently_corrupted() -> (
    None
):
    """The silent-corruption case that used to become a story is now a blocking error.

    Under an ``actor,feature,benefit`` header, an unquoted canonical story is split by
    the story's own commas into exactly three fields, so the counts agree with the
    header by coincidence and the ``field_count_mismatch`` guard cannot catch it: the
    row used to be mapped positionally into a plausible garbage story (actor='As a
    user', feature=' I want A', benefit=' so that B') with nothing reported. The row
    contradicts its own header and is refused with nothing created.
    """
    report = validate_import(
        [
            ImportRow(
                2,
                actor="As a user",
                feature=" I want A",
                benefit=" so that B",
                field_count=3,
                expected_field_count=3,
            )
        ],
        "parts",
        {},
    )

    assert report.blocked
    assert report.new_stories == ()
    assert len(report.errors) == 1
    error = report.errors[0]
    assert error.reason == "parts_look_like_a_full_story"
    assert error.field is None
    assert error.observed_count is None
    assert error.expected_count is None
    assert error.line_number == 2


@pytest.mark.unit
def test_parts_look_like_a_full_story_wins_over_a_length_problem_on_the_same_row() -> None:
    """The whole-story check runs before the per-field checks, so it reports alone."""
    over_limit_actor = "As a " + "x" * FIELD_LIMITS["actor"]
    assert len(over_limit_actor) > FIELD_LIMITS["actor"]

    report = validate_import(
        [ImportRow(4, over_limit_actor, " I want A", " so that B")], "parts", {}
    )

    assert len(report.errors) == 1
    assert report.errors[0].reason == "parts_look_like_a_full_story"


@pytest.mark.unit
def test_full_mode_does_not_run_the_whole_story_check() -> None:
    report = validate_import(
        [
            ImportRow(
                1,
                actor="As a user",
                feature=" I want A",
                benefit=" so that B",
                raw_text="As a user, I want to log in, so that I can access",
            )
        ],
        "full",
        {},
    )

    assert report.errors == ()
    assert len(report.new_stories) == 1
    assert report.new_stories[0].raw_text == "As a user, I want to log in, so that I can access"


@pytest.mark.unit
def test_a_row_with_a_blank_cell_still_falls_through_to_empty_field() -> None:
    """An empty row cannot join into a story, so the emptiness check keeps ruling."""
    report = validate_import([ImportRow(1, actor="  ", feature="", benefit=None)], "parts", {})

    assert [(error.reason, error.field) for error in report.errors] == [("empty_field", "actor")]


@pytest.mark.unit
def test_the_module_does_not_import_from_infrastructure() -> None:
    source = Path(story_import.__file__).read_text(encoding="utf-8")

    assert "infrastructure" not in source
