"""E2E Test Matrix for Kanban drag-drop — validates all column transitions.

This matrix documents the expected behavior for every possible drag-drop
operation on the Kanban board. Used by frontend E2E tests (Playwright/Cypress).

Matrix columns:
- from_column: source Kanban column
- to_column: target Kanban column
- expected: "allow" (200 OK) or "reject" (400 INVALID_STATE_TRANSITION)
- description: rationale for the decision
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from storico.domain.entities.task import TaskStatus
from storico.domain.validators.state_machine import validate_task_transition


@dataclass(frozen=True)
class KanbanTransition:
    """Single Kanban drag-drop test case."""
    from_column: TaskStatus
    to_column: TaskStatus
    expected: Literal["allow", "reject"]
    description: str


# Complete E2E test matrix — all 25 possible transitions (5x5)
KANBAN_TEST_MATRIX: list[KanbanTransition] = [
    # BACKLOG (source)
    KanbanTransition(
        from_column=TaskStatus.BACKLOG,
        to_column=TaskStatus.BACKLOG,
        expected="allow",
        description="Idempotent drop on same column",
    ),
    KanbanTransition(
        from_column=TaskStatus.BACKLOG,
        to_column=TaskStatus.TODO,
        expected="allow",
        description="Promote from backlog to sprint-ready",
    ),
    KanbanTransition(
        from_column=TaskStatus.BACKLOG,
        to_column=TaskStatus.IN_PROGRESS,
        expected="reject",
        description="Cannot skip TODO column",
    ),
    KanbanTransition(
        from_column=TaskStatus.BACKLOG,
        to_column=TaskStatus.REVIEW,
        expected="reject",
        description="Cannot jump to review without work",
    ),
    KanbanTransition(
        from_column=TaskStatus.BACKLOG,
        to_column=TaskStatus.DONE,
        expected="reject",
        description="Cannot complete without any work",
    ),

    # TODO (source)
    KanbanTransition(
        from_column=TaskStatus.TODO,
        to_column=TaskStatus.BACKLOG,
        expected="allow",
        description="Move back to backlog (de-prioritize)",
    ),
    KanbanTransition(
        from_column=TaskStatus.TODO,
        to_column=TaskStatus.TODO,
        expected="reject",
        description="Idempotent drop on same column (not explicitly allowed)",
    ),
    KanbanTransition(
        from_column=TaskStatus.TODO,
        to_column=TaskStatus.IN_PROGRESS,
        expected="allow",
        description="Start working on task",
    ),
    KanbanTransition(
        from_column=TaskStatus.TODO,
        to_column=TaskStatus.REVIEW,
        expected="reject",
        description="Cannot skip IN_PROGRESS",
    ),
    KanbanTransition(
        from_column=TaskStatus.TODO,
        to_column=TaskStatus.DONE,
        expected="reject",
        description="Cannot complete without IN_PROGRESS and REVIEW",
    ),

    # IN_PROGRESS (source)
    KanbanTransition(
        from_column=TaskStatus.IN_PROGRESS,
        to_column=TaskStatus.BACKLOG,
        expected="reject",
        description="Cannot abandon work directly to backlog",
    ),
    KanbanTransition(
        from_column=TaskStatus.IN_PROGRESS,
        to_column=TaskStatus.TODO,
        expected="allow",
        description="Rework: pause work, back to ready",
    ),
    KanbanTransition(
        from_column=TaskStatus.IN_PROGRESS,
        to_column=TaskStatus.IN_PROGRESS,
        expected="reject",
        description="Idempotent drop on same column (not explicitly allowed)",
    ),
    KanbanTransition(
        from_column=TaskStatus.IN_PROGRESS,
        to_column=TaskStatus.REVIEW,
        expected="allow",
        description="Submit for review",
    ),
    KanbanTransition(
        from_column=TaskStatus.IN_PROGRESS,
        to_column=TaskStatus.DONE,
        expected="reject",
        description="Cannot skip REVIEW column",
    ),

    # REVIEW (source)
    KanbanTransition(
        from_column=TaskStatus.REVIEW,
        to_column=TaskStatus.BACKLOG,
        expected="reject",
        description="Cannot send reviewed work back to backlog",
    ),
    KanbanTransition(
        from_column=TaskStatus.REVIEW,
        to_column=TaskStatus.TODO,
        expected="reject",
        description="Cannot send reviewed work back to TODO",
    ),
    KanbanTransition(
        from_column=TaskStatus.REVIEW,
        to_column=TaskStatus.IN_PROGRESS,
        expected="allow",
        description="Request changes — return to development",
    ),
    KanbanTransition(
        from_column=TaskStatus.REVIEW,
        to_column=TaskStatus.REVIEW,
        expected="reject",
        description="Idempotent drop on same column (not explicitly allowed)",
    ),
    KanbanTransition(
        from_column=TaskStatus.REVIEW,
        to_column=TaskStatus.DONE,
        expected="allow",
        description="Accept and complete",
    ),

    # DONE (source) — all reject (terminal state)
    KanbanTransition(
        from_column=TaskStatus.DONE,
        to_column=TaskStatus.BACKLOG,
        expected="reject",
        description="DONE is terminal — cannot move",
    ),
    KanbanTransition(
        from_column=TaskStatus.DONE,
        to_column=TaskStatus.TODO,
        expected="reject",
        description="DONE is terminal — cannot move",
    ),
    KanbanTransition(
        from_column=TaskStatus.DONE,
        to_column=TaskStatus.IN_PROGRESS,
        expected="reject",
        description="DONE is terminal — cannot move",
    ),
    KanbanTransition(
        from_column=TaskStatus.DONE,
        to_column=TaskStatus.REVIEW,
        expected="reject",
        description="DONE is terminal — cannot move",
    ),
    KanbanTransition(
        from_column=TaskStatus.DONE,
        to_column=TaskStatus.DONE,
        expected="reject",
        description="DONE is terminal — cannot move",
    ),
]


def test_kanban_matrix_matches_state_machine():
    """Verify the test matrix matches the actual state machine implementation."""
    for case in KANBAN_TEST_MATRIX:
        actual = validate_task_transition(case.from_column, case.to_column)
        if case.expected == "allow":
            assert actual is True, (
                f"Expected ALLOW for {case.from_column.value} -> {case.to_column.value}: "
                f"{case.description}"
            )
        else:
            assert actual is False, (
                f"Expected REJECT for {case.from_column.value} -> {case.to_column.value}: "
                f"{case.description}"
            )


def test_matrix_covers_all_transitions():
    """Verify matrix covers all 5x5 = 25 possible transitions."""
    assert len(KANBAN_TEST_MATRIX) == 25

    # Verify every combination is present exactly once
    seen = set()
    for case in KANBAN_TEST_MATRIX:
        key = (case.from_column, case.to_column)
        assert key not in seen, f"Duplicate transition: {key}"
        seen.add(key)

    # Verify all combinations covered
    for from_col in TaskStatus:
        for to_col in TaskStatus:
            assert (from_col, to_col) in seen, f"Missing: {from_col.value} -> {to_col.value}"


def test_allowed_count():
    """Verify exactly 8 transitions are allowed (per Kanban flow)."""
    allowed = [c for c in KANBAN_TEST_MATRIX if c.expected == "allow"]
    assert len(allowed) == 8

    # List of allowed transitions
    allowed_pairs = [(c.from_column.value, c.to_column.value) for c in allowed]
    expected_allowed = [
        ("backlog", "backlog"),   # idempotent
        ("backlog", "todo"),
        ("todo", "backlog"),
        ("todo", "in_progress"),
        ("in_progress", "todo"),      # rework
        ("in_progress", "review"),
        ("review", "in_progress"),    # changes requested
        ("review", "done"),           # accept
    ]
    # Note: BACKLOG->BACKLOG is the only self-loop allowed
    # Total: 8 allowed (including BACKLOG self-loop)
    assert len(allowed_pairs) == 8


def test_terminal_state_done():
    """DONE has zero outgoing transitions."""
    done_transitions = [c for c in KANBAN_TEST_MATRIX if c.from_column == TaskStatus.DONE]
    for t in done_transitions:
        assert t.expected == "reject"


def test_backlog_cannot_skip_todo():
    """BACKLOG cannot jump to IN_PROGRESS, REVIEW, or DONE."""
    backlog_transitions = [c for c in KANBAN_TEST_MATRIX if c.from_column == TaskStatus.BACKLOG]
    skip_todo = [c for c in backlog_transitions if c.to_column in (
        TaskStatus.IN_PROGRESS, TaskStatus.REVIEW, TaskStatus.DONE
    )]
    for t in skip_todo:
        assert t.expected == "reject"


def test_todo_cannot_skip_in_progress():
    """TODO cannot jump to REVIEW or DONE."""
    todo_transitions = [c for c in KANBAN_TEST_MATRIX if c.from_column == TaskStatus.TODO]
    skip_in_progress = [c for c in todo_transitions if c.to_column in (
        TaskStatus.REVIEW, TaskStatus.DONE
    )]
    for t in skip_in_progress:
        assert t.expected == "reject"


def test_in_progress_cannot_skip_review():
    """IN_PROGRESS cannot jump to DONE."""
    in_progress_transitions = [c for c in KANBAN_TEST_MATRIX if c.from_column == TaskStatus.IN_PROGRESS]
    skip_review = [c for c in in_progress_transitions if c.to_column == TaskStatus.DONE]
    for t in skip_review:
        assert t.expected == "reject"


def test_review_cannot_go_backwards():
    """REVIEW cannot go to BACKLOG or TODO."""
    review_transitions = [c for c in KANBAN_TEST_MATRIX if c.from_column == TaskStatus.REVIEW]
    backwards = [c for c in review_transitions if c.to_column in (
        TaskStatus.BACKLOG, TaskStatus.TODO
    )]
    for t in backwards:
        assert t.expected == "reject"


def test_rework_loop_allowed():
    """Rework loop: IN_PROGRESS -> TODO and REVIEW -> IN_PROGRESS are allowed."""
    rework = [c for c in KANBAN_TEST_MATRIX if c.expected == "allow" and (
        (c.from_column == TaskStatus.IN_PROGRESS and c.to_column == TaskStatus.TODO) or
        (c.from_column == TaskStatus.REVIEW and c.to_column == TaskStatus.IN_PROGRESS)
    )]
    assert len(rework) == 2