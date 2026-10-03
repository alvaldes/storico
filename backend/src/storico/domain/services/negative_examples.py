"""The negative-example composer — slice (c), WU2, tasks 2.1–2.2.

Turns (b)'s ``TaskInvalidationCandidate`` rows (the mark read
``list_active_on_other_versions`` returns) into the block the prompt renders
under ``## Do Not Produce These Tasks (Previously Marked Invalid)``.

Pure composition: no session, no I/O, no repository, no new mark read. The cap
is a module constant of the feature — deliberately not a column, not a
``workspace_prompts`` field, not a parameter (D19): a workspace knob would let
a workspace silently re-break the cap. Title matching reuses (b)'s
``normalize_task_title``, which is the only place the rule lives.

Determinism matters because the block's text is snapshotted: the sort is a
total order (``marked_at DESC``, then ``version_number DESC``, then normalized
title, then reason), so two runs over the same project state compose
byte-identical blocks even when ``marked_at`` ties.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from storico.domain.ports.task_invalidation_repository import TaskInvalidationCandidate
from storico.domain.services.task_title_normalizer import normalize_task_title

MAX_NEGATIVE_EXAMPLES = 20


@dataclass(frozen=True, slots=True)
class NegativeExample:
    title: str
    reason: str
    version_number: int
    marked_at: datetime


@dataclass(frozen=True, slots=True)
class NegativeExampleBlock:
    examples: tuple[NegativeExample, ...]
    omitted: int

    def as_template_variables(self) -> list[dict[str, object]]:
        """JSON-native: ``[{title, reason, version_number, marked_at}]``.

        ``marked_at`` serializes to ISO-8601 at this boundary — the template
        renders only title, reason and version number, and the JSON-native
        shape is what the snapshot's ``json.dumps`` relies on everywhere else.
        """
        return [
            {
                "title": example.title,
                "reason": example.reason,
                "version_number": example.version_number,
                "marked_at": example.marked_at.isoformat(),
            }
            for example in self.examples
        ]


def compose_negative_examples(
    candidates: Sequence[TaskInvalidationCandidate],
) -> NegativeExampleBlock:
    """Sort, dedupe, cap, and report the omission.

    Order is total: ``marked_at DESC``, then ``version_number DESC``, then
    normalized title, then reason. Dedupe is on
    ``(normalize_task_title(title), reason)`` keeping the most recent of each
    pair — the same normalized title with a different reason is two entries —
    and it runs before the cap, so ``omitted`` counts only what the cap
    dropped, never what dedupe collapsed: ``omitted = deduped_total - taken``.
    """
    ranked = sorted(
        candidates,
        key=lambda c: (
            -c.marked_at.timestamp(),
            -c.version_number,
            normalize_task_title(c.title),
            c.reason,
        ),
    )

    examples: list[NegativeExample] = []
    seen: set[tuple[str, str]] = set()
    for candidate in ranked:
        key = (normalize_task_title(candidate.title), candidate.reason)
        if key in seen:
            continue
        seen.add(key)
        examples.append(
            NegativeExample(
                title=candidate.title,
                reason=candidate.reason,
                version_number=candidate.version_number,
                marked_at=candidate.marked_at,
            )
        )

    taken = examples[:MAX_NEGATIVE_EXAMPLES]
    return NegativeExampleBlock(
        examples=tuple(taken),
        omitted=len(examples) - len(taken),
    )
