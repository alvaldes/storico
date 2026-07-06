"""TaskParser — parses raw LLM output into structured ParsedTask objects.

Adapted from DataForge's ExplodeTasks with three regex fallback levels.
"""

from __future__ import annotations

import re
from typing import ClassVar

from storico.domain.entities import ParseError
from storico.domain.ports import ParsedTask


class TaskParser:
    """Parses raw text from LLM responses into a list of ``ParsedTask``.

    Implements three regex fallback levels:
        1. **Structured** (2-line pattern): ``N. summary: ...`` / ``description: ...``
        2. **Single-line**: ``N. summary: ..., description: ...``
        3. **Numbered items**: Just ``N. ...`` — text becomes summary, empty description.

    Raises ``ParseError`` only if all three fallbacks yield zero tasks.
    """

    # Fallback 1: Structured 2-line format
    _PATTERN_STRUCTURED: ClassVar[re.Pattern[str]] = re.compile(
        r"^(\d+)\.\s*summary:\s*(.+?)\s*\n\s*description:\s*(.+?)(?=\n\s*\d+\.\s*summary:|\Z)",
        re.DOTALL | re.MULTILINE,
    )

    # Fallback 2: Single-line summary,description on the same line
    _PATTERN_SINGLE_LINE: ClassVar[re.Pattern[str]] = re.compile(
        r"^(\d+)\.\s*summary:\s*(.+?),\s*description:\s*(.+)",
        re.MULTILINE,
    )

    # Fallback 3: Any numbered item line
    _PATTERN_NUMBERED: ClassVar[re.Pattern[str]] = re.compile(
        r"^\d+\.\s*(.+)",
        re.MULTILINE,
    )

    # Preamble detector: text before the first "1. summary:" should be stripped
    _PREAMBLE_CUT: ClassVar[re.Pattern[str]] = re.compile(
        r"^.*?(?=1\.\s*summary:\s)",
        re.DOTALL,
    )

    # Markdown bold marker cleanup
    _BOLD_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"\*\*(.+?)\*\*")

    # Label extraction: text inside brackets after summary
    _LABEL_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"\[([^\]]+)\]")

    def parse(self, raw_response: str) -> list[ParsedTask]:
        """Parse raw LLM response into a list of ``ParsedTask``.

        Args:
            raw_response: Raw text from the LLM.

        Returns:
            List of ``ParsedTask`` instances.

        Raises:
            ParseError: If all three fallback parsers yield zero tasks.
        """
        # Try fallback 1 first (structured format)
        tasks = self._parse_structured(raw_response)
        if tasks:
            return tasks

        # Try fallback 2 (single-line format)
        tasks = self._parse_single_line(raw_response)
        if tasks:
            return tasks

        # Try fallback 3 (just numbered items)
        tasks = self._parse_numbered(raw_response)
        if tasks:
            return tasks

        raise ParseError("Could not parse any tasks from LLM response")

    def _clean_text(self, text: str) -> str:
        """Strip markdown bold markers and normalize whitespace."""
        text = self._BOLD_PATTERN.sub(r"\1", text)
        return text.strip()

    def _extract_labels(self, text: str) -> tuple[str, tuple[str, ...]]:
        """Extract labels (e.g., ``[backend]``) from text and return (cleaned_text, labels)."""
        label_matches = self._LABEL_PATTERN.findall(text)
        cleaned = self._LABEL_PATTERN.sub("", text).strip()
        return cleaned, tuple(label_matches)

    def _strip_preamble(self, text: str) -> str:
        """Remove any text before the first ``1. summary:`` line."""
        match = self._PREAMBLE_CUT.match(text)
        if match:
            # Only strip if the preamble doesn't start with a number
            before = match.group(0)
            if not re.match(r"^\s*\d+", before):
                text = text[match.end() :]
        return text.strip()

    def _parse_structured(self, raw: str) -> list[ParsedTask]:
        """Fallback 1: Structured 2-line format.

        Expects each task as:
            N. summary: <title>
            description: <body>

        Strips preamble before first ``1. summary:``.
        """
        raw = self._strip_preamble(raw)
        matches = self._PATTERN_STRUCTURED.findall(raw)
        if not matches:
            return []

        tasks: list[ParsedTask] = []
        for _num, summary, description in matches:
            summary_clean, labels = self._extract_labels(summary)
            summary_clean = self._clean_text(summary_clean)
            description_clean = self._clean_text(description)
            if summary_clean:
                tasks.append(
                    ParsedTask(
                        summary=summary_clean,
                        description=description_clean,
                        labels=labels,
                    )
                )
        return tasks

    def _parse_single_line(self, raw: str) -> list[ParsedTask]:
        """Fallback 2: Single-line format.

        Expects each task as:
            N. summary: <title>, description: <body>
        """
        matches = self._PATTERN_SINGLE_LINE.findall(raw)
        if not matches:
            return []

        tasks: list[ParsedTask] = []
        for _num, summary, description in matches:
            summary_clean, labels = self._extract_labels(summary)
            summary_clean = self._clean_text(summary_clean)
            description_clean = self._clean_text(description)
            if summary_clean:
                tasks.append(
                    ParsedTask(
                        summary=summary_clean,
                        description=description_clean,
                        labels=labels,
                    )
                )
        return tasks

    def _parse_numbered(self, raw: str) -> list[ParsedTask]:
        """Fallback 3: Just numbered items.

        Treats each ``N. <text>`` line as a task with the text as summary
        and an empty description.
        """
        matches = self._PATTERN_NUMBERED.findall(raw)
        if not matches:
            return []

        tasks: list[ParsedTask] = []
        for item in matches:
            text = self._clean_text(item)
            if text:
                tasks.append(ParsedTask(summary=text, description=""))
        return tasks
