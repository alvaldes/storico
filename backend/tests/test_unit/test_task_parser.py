"""Unit tests for TaskParser — EXT-T18."""

import pytest

from storico.domain.entities import ParseError
from storico.infrastructure.llm.task_parser import TaskParser


class TestTaskParser:
    """TaskParser parses raw LLM output into structured ParsedTask objects.

    Implements three regex fallback levels:
        1. Structured (2-line): N. summary: ... / description: ...
        2. Single-line: N. summary: ..., description: ...
        3. Numbered items: N. ...
    """

    def setup_method(self) -> None:
        self.parser = TaskParser()

    # ── Fallback 1: Structured (2-line) ──────────────────────────────

    def test_structured_format(self) -> None:
        """Fallback 1: proper N. summary: / description: format."""
        raw = """1. summary: Set up database schema
description: Create tables for storing transaction records.
2. summary: Build REST API endpoint
description: Implement the transaction listing API."""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 2
        assert tasks[0].summary == "Set up database schema"
        assert tasks[0].description == "Create tables for storing transaction records."
        assert tasks[1].summary == "Build REST API endpoint"
        assert tasks[1].description == "Implement the transaction listing API."

    def test_structured_with_preamble(self) -> None:
        """Preamble text before first task should be stripped."""
        raw = """Here are the tasks I identified:

1. summary: Implement login form
description: Create the login UI component."""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 1
        assert tasks[0].summary == "Implement login form"

    def test_structured_multiple_tasks(self) -> None:
        """Three structured tasks are all parsed correctly."""
        raw = """1. summary: Task one
description: First description.
2. summary: Task two
description: Second description.
3. summary: Task three
description: Third description."""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 3
        assert tasks[2].summary == "Task three"

    # ── Fallback 2: Single-line format ──────────────────────────────

    def test_single_line_format(self) -> None:
        """Fallback 2: N. summary: ..., description: ... on one line."""
        raw = """1. summary: Create auth service, description: Implement JWT token generation
2. summary: Build login page, description: Create login form with validation"""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 2
        assert tasks[0].summary == "Create auth service"
        assert tasks[0].description == "Implement JWT token generation"
        assert tasks[1].summary == "Build login page"

    def test_single_line_with_preamble(self) -> None:
        """Preamble is stripped before single-line parsing."""
        raw = """Here are the tasks:

1. summary: Fix bug, description: Patch the vulnerability"""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 1
        assert tasks[0].summary == "Fix bug"

    # ── Fallback 3: Numbered items ──────────────────────────────────

    def test_numbered_fallback(self) -> None:
        """Fallback 3: just numbered lines."""
        raw = """1. First task
2. Second task
3. Third task"""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 3
        assert tasks[0].summary == "First task"
        assert tasks[0].description == ""
        assert tasks[1].summary == "Second task"
        assert tasks[2].summary == "Third task"

    def test_numbered_with_descriptive_text(self) -> None:
        """Numbered items with multi-word text."""
        raw = """1. Implement the login page with form validation
2. Write unit tests for the auth service
3. Update API documentation"""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 3
        assert "login page" in tasks[0].summary
        assert "unit tests" in tasks[1].summary

    # ── Edge cases ──────────────────────────────────────────────────

    def test_empty_response_raises_error(self) -> None:
        """Empty string should raise ParseError."""
        with pytest.raises(ParseError):
            self.parser.parse("")

    def test_whitespace_only_raises_error(self) -> None:
        """Whitespace-only string should raise ParseError."""
        with pytest.raises(ParseError):
            self.parser.parse("   \n  \n  ")

    def test_invalid_text_raises_error(self) -> None:
        """Text with no recognizable tasks raises ParseError."""
        with pytest.raises(ParseError):
            self.parser.parse("This is just a paragraph with no numbered tasks.")

    def test_strips_markdown_bold(self) -> None:
        """Markdown bold around labels should be stripped."""
        raw = """1. summary: Set up **database** schema
description: Create **tables** for storing records."""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 1
        assert "**" not in tasks[0].summary
        assert "**" not in tasks[0].description
        assert "database" in tasks[0].summary
        assert "tables" in tasks[0].description

    # ── Labels ──────────────────────────────────────────────────────

    def test_with_labels_in_brackets(self) -> None:
        """Labels in brackets after summary should be extracted."""
        raw = """1. summary: Set up database schema [backend][database]
description: Create the database tables."""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 1
        assert tasks[0].labels == ("backend", "database")
        assert tasks[0].summary == "Set up database schema"

    def test_labels_stripped_from_description(self) -> None:
        """Labels only apply to summary, not description."""
        raw = """1. summary: Implement login [frontend]
description: Build the login form [ui]"""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 1
        assert tasks[0].labels == ("frontend",)
        assert tasks[0].summary == "Implement login"
        # Labels in description are not extracted — the regex only
        # looks at the summary field
        assert "ui" in tasks[0].description

    # ── Mixed formatting and edge cases ─────────────────────────────

    def test_trailing_newlines_handled(self) -> None:
        """Trailing whitespace and newlines don't affect parsing."""
        raw = """1. summary: Task one
description: Do something

"""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 1
        assert tasks[0].summary == "Task one"

    def test_extra_whitespace_around_numbers(self) -> None:
        """Extra spaces around the number are handled."""
        raw = """  1.  summary: Task with spaces
description: Description here."""
        tasks = self.parser.parse(raw)
        assert len(tasks) == 1
        assert tasks[0].summary == "Task with spaces"
