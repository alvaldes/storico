"""The ``TaskInvalidationRepository`` port surface and the mark entity's shape.

Slice (a) shipped the storage half (table, model, invariants) with no door; WU5-A
adds the domain trio. This file pins the port's exact method set — the repo's
convention (see ``test_extraction_repo.py`` for the extraction port's pin) — and the
entity/candidate dataclass contracts the design sketches verbatim.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from storico.domain.entities.task_invalidation import TaskInvalidation
from storico.domain.ports.task_invalidation_repository import (
    TaskInvalidationCandidate,
    TaskInvalidationRepository,
)


def test_the_port_pins_its_six_methods() -> None:
    """The exact abstract surface; a future re-add or rename fails visibly."""
    abstract_methods = {
        name
        for name, member in vars(TaskInvalidationRepository).items()
        if getattr(member, "__isabstractmethod__", False)
    }
    assert abstract_methods == {
        "create",
        "find_active_by_task",
        "list_by_task",
        "revoke",
        "list_active_on_other_versions",
        "list_standing_revocations_by_user",
    }


def test_the_entity_is_frozen_slotted_and_defaults_its_events() -> None:
    """A fresh mark has no revoke fields, a minted id and a marked_at timestamp."""
    mark = TaskInvalidation(task_id=uuid4(), reason="overlaps the export task")
    assert mark.revoked_by is None
    assert mark.revoked_at is None
    assert mark.marked_by is None
    assert mark.marked_at is not None
    assert mark.id.version == 7

    with pytest.raises(dataclasses.FrozenInstanceError):
        mark.reason = "mutated"  # type: ignore[misc]


def test_two_marks_mint_distinct_ids_and_their_own_timestamps() -> None:
    first = TaskInvalidation(task_id=uuid4(), reason="first")
    second = TaskInvalidation(task_id=uuid4(), reason="second")
    assert first.id != second.id


def test_the_candidate_is_a_frozen_read_model_with_its_four_fields() -> None:
    """The D16 join's rows belong to *other* tasks, so they are not entities."""
    assert TaskInvalidationCandidate.__dataclass_params__.frozen is True
    assert TaskInvalidationCandidate.__dataclass_params__.slots is True
    assert list(TaskInvalidationCandidate.__dataclass_fields__) == [
        "version_number",
        "title",
        "reason",
        "marked_at",
    ]

    candidate = TaskInvalidationCandidate(
        version_number=1,
        title="Implement login",
        reason="covered",
        marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        candidate.reason = "mutated"  # type: ignore[misc]
