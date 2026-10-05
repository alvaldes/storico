"""Tests for the ``task_invalidations`` model — the storage shape of an invalidation mark.

The mark is a row, not a column pair on ``tasks``: only a row per mark event can hold who
revoked it and when (spec R9). The unit suite builds its schema from the models, so these
tests exercise the model the way every SQLite test does; the Postgres-only behaviours
(partial-index shape, FK actions on user deletion) belong to the integration suite.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from storico.domain.entities.extraction import ExtractionStatus
from storico.infrastructure.database.models import ExtractionModel, TaskModel
from tests._helpers import seed_extraction, seed_task


def test_the_mark_lives_in_the_task_invalidations_table() -> None:
    """A dedicated table, by name — not a column pair smuggled onto ``tasks``."""
    from storico.infrastructure.database.models import TaskInvalidationModel

    assert TaskInvalidationModel.__tablename__ == "task_invalidations"


@pytest.mark.asyncio
async def test_a_mark_round_trips_with_its_reason_and_attribution(
    db_session: AsyncSession,
) -> None:
    """A mark persists task_id, reason, marked_by and marked_at; the revoke fields stay null.

    The table is not created by hand: once ``TaskInvalidationModel`` is registered in
    ``models/__init__`` the conftest schema carries it through ``Base.metadata.create_all``,
    which is exactly what task 1.8 has to prove. Until then the import below is the failure.
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    marker_id = uuid4()
    marked_at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    db_session.add(
        TaskInvalidationModel(
            task_id=uuid4(),
            reason="overlaps the export task",
            marked_by=marker_id,
            marked_at=marked_at,
        )
    )
    await db_session.commit()

    found = (await db_session.execute(select(TaskInvalidationModel))).scalar_one()
    assert found.reason == "overlaps the export task"
    assert found.marked_by == marker_id
    # The test database is SQLite, which drops ``tzinfo`` on a ``DateTime(timezone=True)``
    # column — the same note as in ``test_extraction_repo.py``. The instant is what the
    # column carries; Postgres, which is what production runs, keeps the offset.
    assert found.marked_at.replace(tzinfo=None) == marked_at.replace(tzinfo=None)
    assert found.revoked_by is None
    assert found.revoked_at is None


def test_tasks_carry_no_invalidation_columns() -> None:
    """The mark is not a column pair on ``tasks``: only a row can hold who revoked and when.

    Guarding the rejected shape rather than the chosen one: any column whose name admits
    an invalidation meaning on ``tasks`` means the mark drifted back onto the task row.
    """
    invalid_columns = [
        column.name for column in TaskModel.__table__.columns if "invalid" in column.name
    ]
    assert invalid_columns == []


# --- 4.1 invariant cases ---------------------------------------------------
# The unit schema is built from the models, so every refusal below is a model
# declaration doing real work. Task 4.2 proves each declaration is load-bearing
# by deleting it from the model and watching the matching case here fail.


@pytest.mark.asyncio
async def test_an_empty_reason_is_refused_by_the_reason_not_blank_check(
    db_session: AsyncSession,
) -> None:
    """A mark with ``reason == ""`` is refused, by constraint name.

    The reason is mandatory as a database invariant (R10), not as an application
    rule: no caller, present or future, can persist a reasonless mark. SQLite
    reports named CHECK constraints by name, so the assertion pins the name the
    migration 0028 creates.
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    db_session.add(
        TaskInvalidationModel(
            task_id=uuid4(),
            reason="",
            marked_by=uuid4(),
            marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError, match="ck_task_invalidations_reason_not_blank"):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_a_space_only_reason_is_refused_by_the_reason_not_blank_check(
    db_session: AsyncSession,
) -> None:
    """Whitespace is not a reason: ``length(trim(reason)) > 0`` refuses it.

    The CHECK trims before measuring, so a reason of spaces cannot smuggle an
    empty mark past the invariant that ``reason=""`` hits.
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    db_session.add(
        TaskInvalidationModel(
            task_id=uuid4(),
            reason="   ",
            marked_by=uuid4(),
            marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError, match="ck_task_invalidations_reason_not_blank"):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_a_bounded_non_empty_reason_round_trips_verbatim(
    db_session: AsyncSession,
) -> None:
    """A reason filling the 500-character bound survives the column unchanged.

    The invariant refuses emptiness, not length: a reason at the full
    ``String(500)`` bound round-trips byte-for-byte, so no trimming or clamping
    happens between the caller and the column.
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    reason = "overlaps the export task" + "x" * (500 - len("overlaps the export task"))
    marked_at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    db_session.add(
        TaskInvalidationModel(
            task_id=uuid4(),
            reason=reason,
            marked_by=uuid4(),
            marked_at=marked_at,
        )
    )
    await db_session.commit()

    found = (await db_session.execute(select(TaskInvalidationModel))).scalar_one()
    assert found.reason == reason
    assert len(found.reason) == 500
    assert found.marked_at.replace(tzinfo=None) == marked_at.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_a_second_active_mark_for_one_task_is_refused(
    db_session: AsyncSession,
) -> None:
    """Two active marks on one task violate the partial unique index (R11).

    SQLite reports unique-index violations by column list, not index name, so
    the assertion pins ``task_invalidations.task_id``; the index's identity
    (``uq_task_invalidations_active_task``, partial on ``revoked_at IS NULL``)
    is the Postgres half, task 4.3's job to verify. The mutation matrix in 4.2
    proves which model declaration this case guards.
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    task = await seed_task(db_session, uuid4(), "Implement login")
    marked_at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    db_session.add(
        TaskInvalidationModel(
            task_id=task.id, reason="first mark", marked_by=uuid4(), marked_at=marked_at
        )
    )
    db_session.add(
        TaskInvalidationModel(
            task_id=task.id, reason="second mark", marked_by=uuid4(), marked_at=marked_at
        )
    )
    with pytest.raises(
        IntegrityError, match="UNIQUE constraint failed: task_invalidations.task_id"
    ):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_a_revoke_then_a_re_mark_succeeds_and_the_first_row_keeps_both_events(
    db_session: AsyncSession,
) -> None:
    """Revoking frees the task for a new mark; the revoked row keeps its history (R12).

    This is the case the partial index exists for: a *full* unique index on
    ``task_id`` would refuse the re-mark, so this case fails the moment the
    ``sqlite_where`` mirror is dropped from the model (mutation M3 in 4.2).
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    task = await seed_task(db_session, uuid4(), "Implement login")
    marker_id = uuid4()
    marked_at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    db_session.add(
        TaskInvalidationModel(
            task_id=task.id, reason="overlaps", marked_by=marker_id, marked_at=marked_at
        )
    )
    await db_session.commit()

    first = (await db_session.execute(select(TaskInvalidationModel))).scalar_one()
    revoker_id = uuid4()
    revoked_at = datetime(2026, 9, 28, 13, 0, tzinfo=UTC)
    first.revoked_by = revoker_id
    first.revoked_at = revoked_at
    await db_session.commit()

    # The re-mark: allowed precisely because the first mark is no longer active.
    second_marker = uuid4()
    db_session.add(
        TaskInvalidationModel(
            task_id=task.id,
            reason="still overlaps after the fix",
            marked_by=second_marker,
            marked_at=datetime(2026, 9, 28, 14, 0, tzinfo=UTC),
        )
    )
    await db_session.commit()

    rows = list((await db_session.execute(select(TaskInvalidationModel))).scalars())
    assert len(rows) == 2
    first_row = next(row for row in rows if row.reason == "overlaps")
    second_row = next(row for row in rows if row.reason == "still overlaps after the fix")
    # The first row still records BOTH events: its marking and its revocation.
    assert first_row.marked_by == marker_id
    assert first_row.marked_at.replace(tzinfo=None) == marked_at.replace(tzinfo=None)
    assert first_row.revoked_by == revoker_id
    assert first_row.revoked_at.replace(tzinfo=None) == revoked_at.replace(tzinfo=None)
    assert second_row.marked_by == second_marker
    assert second_row.revoked_by is None
    assert second_row.revoked_at is None


@pytest.mark.asyncio
async def test_revoking_records_attribution_on_the_same_row_without_touching_the_marking_fields(
    db_session: AsyncSession,
) -> None:
    """A revoke is an UPDATE on the mark row: who and when, nothing else moves (R12).

    No second row is created, no marking field is rewritten — the mark's
    history is the original row plus the revoke attribution on it.
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    task = await seed_task(db_session, uuid4(), "Implement login")
    marker_id = uuid4()
    marked_at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    db_session.add(
        TaskInvalidationModel(
            task_id=task.id, reason="overlaps", marked_by=marker_id, marked_at=marked_at
        )
    )
    await db_session.commit()

    row = (await db_session.execute(select(TaskInvalidationModel))).scalar_one()
    row_id = row.id
    revoker_id = uuid4()
    revoked_at = datetime(2026, 9, 28, 13, 0, tzinfo=UTC)
    row.revoked_by = revoker_id
    row.revoked_at = revoked_at
    await db_session.commit()

    found = (await db_session.execute(select(TaskInvalidationModel))).scalars().all()
    assert len(found) == 1  # same row, not a second one
    row = found[0]
    assert row.id == row_id
    assert row.revoked_by == revoker_id
    assert row.revoked_at.replace(tzinfo=None) == revoked_at.replace(tzinfo=None)
    assert row.reason == "overlaps"
    assert row.marked_by == marker_id
    assert row.marked_at.replace(tzinfo=None) == marked_at.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_a_half_revoke_is_refused_by_the_revoke_pair_check(
    db_session: AsyncSession,
) -> None:
    """A revoke with only one of ``revoked_by``/``revoked_at`` is refused, by name.

    ``ck_task_invalidations_revoke_pair`` ties the two revoke columns together
    ((``revoked_by IS NULL``) = (``revoked_at IS NULL``)): a revocation that
    records who but not when, or when but not who, is a corrupt history and the
    database refuses it. Both arms are exercised; an ordinary active mark (both
    null) is the one shape the CHECK allows besides a full revoke.
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    db_session.add(
        TaskInvalidationModel(
            task_id=uuid4(),
            reason="who but not when",
            marked_by=uuid4(),
            marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            revoked_by=uuid4(),
            revoked_at=None,
        )
    )
    with pytest.raises(IntegrityError, match="ck_task_invalidations_revoke_pair"):
        await db_session.flush()
    await db_session.rollback()

    db_session.add(
        TaskInvalidationModel(
            task_id=uuid4(),
            reason="when but not who",
            marked_by=uuid4(),
            marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
            revoked_by=None,
            revoked_at=datetime(2026, 9, 28, 13, 0, tzinfo=UTC),
        )
    )
    with pytest.raises(IntegrityError, match="ck_task_invalidations_revoke_pair"):
        await db_session.flush()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_a_mark_resolves_to_its_extraction_only_through_the_tasks_extraction_id(
    db_session: AsyncSession,
) -> None:
    """The mark's version membership resolves through task → extraction_id (R14).

    The mark table has no version column of its own: joining mark → task →
    extraction is the only route, and it must land on the extraction the task
    was built from (v2), never on an older version of the same story.
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    story_id = uuid4()
    v1 = await seed_extraction(
        db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v1"
    )
    v2 = await seed_extraction(
        db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v2"
    )
    assert v1.version_number == 1
    assert v2.version_number == 2

    task = await seed_task(db_session, story_id, "Implement login", extraction=v2)
    db_session.add(
        TaskInvalidationModel(
            task_id=task.id,
            reason="wrong version shipped",
            marked_by=uuid4(),
            marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
    )
    await db_session.commit()

    extraction = (
        await db_session.execute(
            select(ExtractionModel)
            .join(TaskModel, TaskModel.extraction_id == ExtractionModel.id)
            .join(TaskInvalidationModel, TaskInvalidationModel.task_id == TaskModel.id)
        )
    ).scalar_one()
    assert extraction.id == v2.id
    assert extraction.version_number == 2


@pytest.mark.asyncio
async def test_a_v2_task_sharing_a_marked_v1_tasks_title_carries_no_mark(
    db_session: AsyncSession,
) -> None:
    """Marks bind to task ids, not titles: a re-run's same-titled task is unmarked (R14).

    A v2 run on the story recreates the task row with the same title. The mark
    made on the v1 task does not follow the title — the new row starts clean,
    and the old row keeps its mark.
    """
    from storico.infrastructure.database.models import TaskInvalidationModel

    story_id = uuid4()
    v1 = await seed_extraction(
        db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v1"
    )
    v2 = await seed_extraction(
        db_session, story_id, status=ExtractionStatus.COMPLETED, raw_response="v2"
    )
    v1_task = await seed_task(db_session, story_id, "Implement login", extraction=v1)
    v2_task = await seed_task(db_session, story_id, "Implement login", extraction=v2)
    assert v1_task.id != v2_task.id

    db_session.add(
        TaskInvalidationModel(
            task_id=v1_task.id,
            reason="overlaps",
            marked_by=uuid4(),
            marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        )
    )
    await db_session.commit()

    v1_marks = (
        (
            await db_session.execute(
                select(TaskInvalidationModel).where(TaskInvalidationModel.task_id == v1_task.id)
            )
        )
        .scalars()
        .all()
    )
    v2_marks = (
        (
            await db_session.execute(
                select(TaskInvalidationModel).where(TaskInvalidationModel.task_id == v2_task.id)
            )
        )
        .scalars()
        .all()
    )
    assert [mark.reason for mark in v1_marks] == ["overlaps"]
    assert v2_marks == []


# --- 5.3 query-level cases (WU5-A) ------------------------------------------
# Slice (a) pinned the table's shape and invariants above; these cases exercise
# the repository port on top of it. Marks are seeded through the repository's
# ``create`` — the same birth path the API will use — and each case reads back
# through the method under test.


async def _seed_mark(
    db_session: AsyncSession,
    task_id,
    *,
    reason: str,
    marked_at: datetime,
    marked_by=None,
):
    from storico.domain.entities.task_invalidation import TaskInvalidation
    from storico.infrastructure.database.repositories import (
        SQLAlchemyTaskInvalidationRepository,
    )

    return await SQLAlchemyTaskInvalidationRepository(db_session).create(
        TaskInvalidation(task_id=task_id, reason=reason, marked_by=marked_by, marked_at=marked_at)
    )


def _repo(db_session: AsyncSession):
    from storico.infrastructure.database.repositories import (
        SQLAlchemyTaskInvalidationRepository,
    )

    return SQLAlchemyTaskInvalidationRepository(db_session)


@pytest.mark.asyncio
async def test_find_active_by_task_returns_the_single_active_row(
    db_session: AsyncSession,
) -> None:
    """The active mark resolves by task id alone — at most one row can match (R9)."""
    task = await seed_task(db_session, uuid4(), "Implement login")
    marker_id = uuid4()
    marked_at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    created = await _seed_mark(
        db_session,
        task.id,
        reason="overlaps the export task",
        marked_at=marked_at,
        marked_by=marker_id,
    )

    found = await _repo(db_session).find_active_by_task(task.id)

    assert found is not None
    assert found.id == created.id
    assert found.task_id == task.id
    assert found.reason == "overlaps the export task"
    assert found.marked_by == marker_id
    assert found.revoked_by is None
    assert found.revoked_at is None


@pytest.mark.asyncio
async def test_find_active_by_task_returns_none_when_the_only_row_is_revoked(
    db_session: AsyncSession,
) -> None:
    """A revoked mark is history, not an active mark: the read answers None (R10)."""
    task = await seed_task(db_session, uuid4(), "Implement login")
    created = await _seed_mark(
        db_session, task.id, reason="overlaps", marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    )
    await _repo(db_session).revoke(
        created.id,
        revoked_by=uuid4(),
        revoked_at=datetime(2026, 9, 28, 13, 0, tzinfo=UTC),
    )

    assert await _repo(db_session).find_active_by_task(task.id) is None


@pytest.mark.asyncio
async def test_list_by_task_puts_the_active_mark_first_then_orders_marked_at_desc(
    db_session: AsyncSession,
) -> None:
    """The active mark leads even when its marked_at is the *earlier* one (R9).

    The re-mark is created with an ``marked_at`` earlier than the revoked mark's:
    a bare ``marked_at DESC`` would put the revoked row first, so the ordering the
    port documents (active first, then ``marked_at DESC``) is pinned against both
    keys at once. The revoked row comes back with its full history.
    """
    task = await seed_task(db_session, uuid4(), "Implement login")
    marker_id = uuid4()
    first = await _seed_mark(
        db_session,
        task.id,
        reason="first mark",
        marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
        marked_by=marker_id,
    )
    revoker_id = uuid4()
    revoked_at = datetime(2026, 9, 28, 13, 0, tzinfo=UTC)
    await _repo(db_session).revoke(first.id, revoked_by=revoker_id, revoked_at=revoked_at)
    second = await _seed_mark(
        db_session,
        task.id,
        reason="re-mark after fix",
        marked_at=datetime(2026, 9, 28, 11, 0, tzinfo=UTC),
    )

    history = await _repo(db_session).list_by_task(task.id)

    assert [mark.id for mark in history] == [second.id, first.id]
    assert history[0].revoked_at is None
    assert history[1].revoked_by == revoker_id
    assert history[1].revoked_at.replace(tzinfo=None) == revoked_at.replace(tzinfo=None)
    assert history[1].marked_by == marker_id


@pytest.mark.asyncio
async def test_revoke_sets_only_the_revoke_fields_and_deletes_nothing(
    db_session: AsyncSession,
) -> None:
    """Revoking is an UPDATE on the resolved row; the row count never moves (R10)."""
    from sqlalchemy import func, select

    from storico.infrastructure.database.models import TaskInvalidationModel

    task = await seed_task(db_session, uuid4(), "Implement login")
    marker_id = uuid4()
    marked_at = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    created = await _seed_mark(
        db_session, task.id, reason="overlaps", marked_at=marked_at, marked_by=marker_id
    )
    count_before = (
        await db_session.execute(select(func.count()).select_from(TaskInvalidationModel))
    ).scalar_one()

    revoker_id = uuid4()
    revoked_at = datetime(2026, 9, 28, 13, 0, tzinfo=UTC)
    await _repo(db_session).revoke(created.id, revoked_by=revoker_id, revoked_at=revoked_at)

    count_after = (
        await db_session.execute(select(func.count()).select_from(TaskInvalidationModel))
    ).scalar_one()
    assert count_after == count_before == 1

    found = (await _repo(db_session).list_by_task(task.id))[0]
    assert found.id == created.id
    assert found.revoked_by == revoker_id
    assert found.revoked_at.replace(tzinfo=None) == revoked_at.replace(tzinfo=None)
    # Nothing else moved.
    assert found.reason == "overlaps"
    assert found.marked_by == marker_id
    assert found.marked_at.replace(tzinfo=None) == marked_at.replace(tzinfo=None)


@pytest.mark.asyncio
async def test_candidate_read_returns_other_versions_active_marks_with_version_and_title(
    db_session: AsyncSession,
) -> None:
    """The D16 read: non-revoked marks of the story's *other* versions, with their
    version number and task title attached (R11). Same-version, revoked and
    other-story marks are all invisible."""
    story_id = uuid4()
    v1 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
    )
    v2 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 9, 28, 11, 0, tzinfo=UTC),
    )
    v3 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
    )
    v1_task = await seed_task(db_session, story_id, "Implement  Login", extraction=v1)
    v3_task = await seed_task(db_session, story_id, "Implement login", extraction=v3)
    other_story_id = uuid4()
    other_v1 = await seed_extraction(
        db_session,
        other_story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
    )
    other_task = await seed_task(db_session, other_story_id, "Implement login", extraction=other_v1)

    await _seed_mark(
        db_session,
        v1_task.id,
        reason="covered by the auth refactor",
        marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
    )
    # A revoked mark on v2 must not surface.
    v2_task = await seed_task(db_session, story_id, "Implement login", extraction=v2)
    revoked = await _seed_mark(
        db_session,
        v2_task.id,
        reason="revoked mark",
        marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
    )
    await _repo(db_session).revoke(
        revoked.id, revoked_by=uuid4(), revoked_at=datetime(2026, 9, 28, 13, 0, tzinfo=UTC)
    )
    # Another story's active mark must not surface.
    await _seed_mark(
        db_session,
        other_task.id,
        reason="another story's mark",
        marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
    )

    candidates = await _repo(db_session).list_active_on_other_versions(
        user_story_id=story_id, exclude_extraction_id=v3_task.extraction_id
    )

    assert [(c.version_number, c.title, c.reason) for c in candidates] == [
        (1, "Implement  Login", "covered by the auth refactor")
    ]


@pytest.mark.asyncio
async def test_candidate_read_orders_version_number_desc_then_marked_at_desc(
    db_session: AsyncSession,
) -> None:
    """Newest version first; within one version, the latest mark first (R11).

    Two active marks can coexist inside one version because they sit on two
    different task rows — the partial unique index constrains per task, not per
    version — which is what makes the ``marked_at`` tiebreaker observable.
    """
    story_id = uuid4()
    v1 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
    )
    v2 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 9, 28, 11, 0, tzinfo=UTC),
    )
    v3 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
    )
    v1_task_earlier = await seed_task(db_session, story_id, "task a", extraction=v1)
    v1_task_later = await seed_task(db_session, story_id, "task b", extraction=v1)
    v2_task = await seed_task(db_session, story_id, "task c", extraction=v2)
    v3_task = await seed_task(db_session, story_id, "Implement login", extraction=v3)

    await _seed_mark(
        db_session,
        v1_task_earlier.id,
        reason="earlier in v1",
        marked_at=datetime(2026, 9, 28, 11, 0, tzinfo=UTC),
    )
    await _seed_mark(
        db_session,
        v1_task_later.id,
        reason="later in v1",
        marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC),
    )
    await _seed_mark(
        db_session, v2_task.id, reason="in v2", marked_at=datetime(2026, 9, 28, 10, 0, tzinfo=UTC)
    )

    candidates = await _repo(db_session).list_active_on_other_versions(
        user_story_id=story_id, exclude_extraction_id=v3_task.extraction_id
    )

    assert [(c.version_number, c.title, c.reason) for c in candidates] == [
        (2, "task c", "in v2"),
        (1, "task b", "later in v1"),
        (1, "task a", "earlier in v1"),
    ]


@pytest.mark.asyncio
async def test_candidate_read_with_no_excluded_version_excludes_nothing(
    db_session: AsyncSession,
) -> None:
    """``exclude_extraction_id=None`` means the predicate filters out nothing.

    The version D16 warning is for the task being edited — its own version is
    excluded — but the port keeps the parameter optional: ``None`` is the
    "exclude nothing" shape, not "exclude nulls".
    """
    story_id = uuid4()
    v1 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 9, 28, 10, 0, tzinfo=UTC),
    )
    v2 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 9, 28, 11, 0, tzinfo=UTC),
    )
    v1_task = await seed_task(db_session, story_id, "task a", extraction=v1)
    v2_task = await seed_task(db_session, story_id, "task b", extraction=v2)
    await _seed_mark(
        db_session, v1_task.id, reason="v1 mark", marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    )
    await _seed_mark(
        db_session, v2_task.id, reason="v2 mark", marked_at=datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
    )

    candidates = await _repo(db_session).list_active_on_other_versions(
        user_story_id=story_id, exclude_extraction_id=None
    )

    assert [(c.version_number, c.reason) for c in candidates] == [
        (2, "v2 mark"),
        (1, "v1 mark"),
    ]


# --- 5.14 account-delete read (W5-B2a) ---------------------------------------
# The account-delete pre-check needs the revocations one user's account is
# still standing behind — each carrying enough context to be named to a human:
# the story the mark sits in, the version number and the task title. Every case
# here reads through the new port method only; the twelve cases above are the
# slice-(a) and W5-A record and stay untouched.


@pytest.mark.asyncio
async def test_standing_revocations_come_back_with_story_version_and_title(
    db_session: AsyncSession,
) -> None:
    """A user's standing revokes answer with their story, version and title.

    The pre-check must be able to name each blocker to the account's owner:
    the story id the mark's task belongs to, the version number the task was
    built from and the task's title — resolved through the same
    mark → task → extraction join the D16 candidate read uses (R14).
    """
    from storico.domain.ports.task_invalidation_repository import StandingRevocation

    story_id = uuid4()
    extraction = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 10, 2, 10, 0, tzinfo=UTC),
    )
    task = await seed_task(db_session, story_id, "Implement login", extraction=extraction)
    revoker_id = uuid4()
    mark = await _seed_mark(
        db_session,
        task.id,
        reason="overlaps the export task",
        marked_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
    )
    await _repo(db_session).revoke(
        mark.id, revoked_by=revoker_id, revoked_at=datetime(2026, 10, 2, 13, 0, tzinfo=UTC)
    )

    standing = await _repo(db_session).list_standing_revocations_by_user(revoker_id)

    assert standing == [
        StandingRevocation(user_story_id=story_id, version_number=1, title="Implement login")
    ]


@pytest.mark.asyncio
async def test_a_nulled_revoker_is_attributed_to_no_one(db_session: AsyncSession) -> None:
    """A ``revoked_by IS NULL`` row belongs to no account's standing list.

    The revoke-pair CHECK ties the two nulls together — ``revoked_by IS NULL``
    can only stand beside a nulled ``revoked_at``, the active-mark shape — so
    the row the read must never attribute is exactly an active mark: neither
    the attribution predicate nor the ``revoked_at IS NOT NULL`` filter may let
    it through for any user id.
    """
    task = await seed_task(db_session, uuid4(), "Implement login")
    await _seed_mark(
        db_session,
        task.id,
        reason="still active",
        marked_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
    )

    standing = await _repo(db_session).list_standing_revocations_by_user(uuid4())

    assert standing == []


@pytest.mark.asyncio
async def test_a_revoked_then_remarked_task_yields_only_the_standing_revoke(
    db_session: AsyncSession,
) -> None:
    """Two mark rows on one task, one standing revoke: exactly one entry.

    The revoked row answers (its revoker still exists); the later active mark
    on the same task carries no revoke attribution and must not double the
    entry — the read counts standing revocations, not rows.
    """
    task = await seed_task(db_session, uuid4(), "Implement login")
    revoker_id = uuid4()
    first = await _seed_mark(
        db_session,
        task.id,
        reason="overlaps",
        marked_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
    )
    await _repo(db_session).revoke(
        first.id, revoked_by=revoker_id, revoked_at=datetime(2026, 10, 2, 13, 0, tzinfo=UTC)
    )
    await _seed_mark(
        db_session,
        task.id,
        reason="re-mark after fix",
        marked_at=datetime(2026, 10, 2, 14, 0, tzinfo=UTC),
        marked_by=uuid4(),
    )

    standing = await _repo(db_session).list_standing_revocations_by_user(revoker_id)

    assert [(entry.title, entry.version_number) for entry in standing] == [("Implement login", 1)]


@pytest.mark.asyncio
async def test_another_users_revocations_are_absent(db_session: AsyncSession) -> None:
    """Attribution is exact: only the revoker's own standing list carries a revoke."""
    task = await seed_task(db_session, uuid4(), "Implement login")
    mark = await _seed_mark(
        db_session,
        task.id,
        reason="overlaps",
        marked_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
    )
    await _repo(db_session).revoke(
        mark.id, revoked_by=uuid4(), revoked_at=datetime(2026, 10, 2, 13, 0, tzinfo=UTC)
    )

    standing = await _repo(db_session).list_standing_revocations_by_user(uuid4())

    assert standing == []


@pytest.mark.asyncio
async def test_a_mark_merely_made_by_the_user_is_absent(db_session: AsyncSession) -> None:
    """``marked_by`` is not attribution: an unrevoked mark blocks nobody's deletion.

    The read filters on ``revoked_by`` — who *revoked* — never on ``marked_by``;
    a user who only made a mark holds no standing revocation.
    """
    task = await seed_task(db_session, uuid4(), "Implement login")
    await _seed_mark(
        db_session,
        task.id,
        reason="overlaps",
        marked_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC),
        marked_by=uuid4(),
    )

    standing = await _repo(db_session).list_standing_revocations_by_user(uuid4())

    assert standing == []


@pytest.mark.asyncio
async def test_standing_revocations_order_version_number_asc_then_title_asc(
    db_session: AsyncSession,
) -> None:
    """The pinned order: oldest version first, alphabetical within a version.

    A refusal's entry list is a checklist the user acts on top-down, so the
    read is ordered ``version_number ASC, title ASC`` — deterministic across
    pages and independent of mark timestamps.
    """
    story_id = uuid4()
    v1 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 10, 2, 10, 0, tzinfo=UTC),
    )
    v2 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 10, 2, 11, 0, tzinfo=UTC),
    )
    task_b = await seed_task(db_session, story_id, "b task", extraction=v2)
    task_z = await seed_task(db_session, story_id, "z task", extraction=v1)
    task_a = await seed_task(db_session, story_id, "a task", extraction=v1)
    revoker_id = uuid4()
    for task, marked_at in [
        (task_z, datetime(2026, 10, 2, 12, 0, tzinfo=UTC)),
        (task_b, datetime(2026, 10, 2, 13, 0, tzinfo=UTC)),
        (task_a, datetime(2026, 10, 2, 14, 0, tzinfo=UTC)),
    ]:
        mark = await _seed_mark(db_session, task.id, reason="overlaps", marked_at=marked_at)
        await _repo(db_session).revoke(
            mark.id, revoked_by=revoker_id, revoked_at=datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
        )

    standing = await _repo(db_session).list_standing_revocations_by_user(revoker_id)

    assert [(entry.version_number, entry.title) for entry in standing] == [
        (1, "a task"),
        (1, "z task"),
        (2, "b task"),
    ]


# --- (c) 3.10 — the computed active-mark count -------------------------------
# The vector refresh needs "how many active marks will the extraction still
# carry after this mark is revoked": one statement over the mark → task join,
# scoped to the extraction, with the mark being revoked excluded. The count is
# a computed value, not a read model, which is what lets the refresh run
# before the revoke without touching the internally-committing ``revoke``.


@pytest.mark.asyncio
async def test_two_active_marks_on_one_extraction_count_two(
    db_session: AsyncSession,
) -> None:
    """Two active marks on tasks of one extraction answer 2."""
    story_id = uuid4()
    extraction = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 10, 2, 10, 0, tzinfo=UTC),
    )
    task_a = await seed_task(db_session, story_id, "task a", extraction=extraction)
    task_b = await seed_task(db_session, story_id, "task b", extraction=extraction)
    await _seed_mark(
        db_session, task_a.id, reason="overlaps", marked_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    )
    await _seed_mark(
        db_session,
        task_b.id,
        reason="duplicates",
        marked_at=datetime(2026, 10, 2, 13, 0, tzinfo=UTC),
    )

    count = await _repo(db_session).count_active_for_extraction(extraction_id=extraction.id)

    assert count == 2


@pytest.mark.asyncio
async def test_excluding_the_mark_being_revoked_gives_the_remaining_count(
    db_session: AsyncSession,
) -> None:
    """``exclude_mark_id`` answers the handler's pre-revoke question.

    The revoke handler counts with ``exclude_mark_id`` set to the mark it is
    about to revoke: the value is what the refresh writes, before the revoke
    happens. Two marks: excluding the first gives 1 (the refresh writes
    ``True`` and the mark is revoked); the last mark excluding itself gives 0
    (the refresh writes ``False``), and after both revokes the plain count
    gives 0.
    """
    story_id = uuid4()
    extraction = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 10, 2, 10, 0, tzinfo=UTC),
    )
    task_a = await seed_task(db_session, story_id, "task a", extraction=extraction)
    task_b = await seed_task(db_session, story_id, "task b", extraction=extraction)
    mark_a = await _seed_mark(
        db_session, task_a.id, reason="overlaps", marked_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    )
    mark_b = await _seed_mark(
        db_session,
        task_b.id,
        reason="duplicates",
        marked_at=datetime(2026, 10, 2, 13, 0, tzinfo=UTC),
    )
    repo = _repo(db_session)

    assert (
        await repo.count_active_for_extraction(
            extraction_id=extraction.id, exclude_mark_id=mark_a.id
        )
        == 1
    )
    await repo.revoke(
        mark_a.id, revoked_by=uuid4(), revoked_at=datetime(2026, 10, 2, 14, 0, tzinfo=UTC)
    )
    assert await repo.count_active_for_extraction(extraction_id=extraction.id) == 1

    assert (
        await repo.count_active_for_extraction(
            extraction_id=extraction.id, exclude_mark_id=mark_b.id
        )
        == 0
    )
    await repo.revoke(
        mark_b.id, revoked_by=uuid4(), revoked_at=datetime(2026, 10, 2, 15, 0, tzinfo=UTC)
    )
    assert await repo.count_active_for_extraction(extraction_id=extraction.id) == 0


@pytest.mark.asyncio
async def test_the_count_is_scoped_to_the_extraction(
    db_session: AsyncSession,
) -> None:
    """Another version's mark on the same story is not counted.

    The join is mark → task → ``tasks.extraction_id``: a mark on a superseded
    version's task belongs to a different extraction, so it never answers a
    count scoped to this one.
    """
    story_id = uuid4()
    v1 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 10, 2, 10, 0, tzinfo=UTC),
    )
    v2 = await seed_extraction(
        db_session,
        story_id,
        status=ExtractionStatus.COMPLETED,
        completed_at=datetime(2026, 10, 2, 11, 0, tzinfo=UTC),
    )
    v1_task = await seed_task(db_session, story_id, "v1 task", extraction=v1)
    v2_task = await seed_task(db_session, story_id, "v2 task", extraction=v2)
    await _seed_mark(
        db_session, v1_task.id, reason="in v1", marked_at=datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    )
    await _seed_mark(
        db_session, v2_task.id, reason="in v2", marked_at=datetime(2026, 10, 2, 13, 0, tzinfo=UTC)
    )

    count = await _repo(db_session).count_active_for_extraction(extraction_id=v2.id)

    assert count == 1


@pytest.mark.asyncio
async def test_active_marks_of_a_story_exclude_revoked_rows_and_other_stories(
    db_session: AsyncSession,
) -> None:
    """The story-scoped read answers exactly the story's active marks, newest first.

    Three exclusions, each of which would be a wrong card on the page: a revoked
    mark of the same story (history, not state), and an active mark of another
    story (another page's card). The order is ``marked_at DESC`` so the read is
    deterministic rather than incidental.
    """
    story_a = uuid4()
    story_b = uuid4()
    task_a1 = await seed_task(db_session, story_a, "Story A first")
    task_a2 = await seed_task(db_session, story_a, "Story A second")
    task_a3 = await seed_task(db_session, story_a, "Story A third — will be revoked")
    task_b1 = await seed_task(db_session, story_b, "Story B only")

    newer = await _seed_mark(
        db_session,
        task_a1.id,
        reason="kept, newer",
        marked_at=datetime(2026, 10, 5, 12, 0, tzinfo=UTC),
    )
    older = await _seed_mark(
        db_session,
        task_a2.id,
        reason="kept, older",
        marked_at=datetime(2026, 10, 5, 10, 0, tzinfo=UTC),
    )
    revoked = await _seed_mark(
        db_session,
        task_a3.id,
        reason="revoked, so history",
        marked_at=datetime(2026, 10, 5, 11, 0, tzinfo=UTC),
    )
    await _repo(db_session).revoke(
        revoked.id, revoked_by=uuid4(), revoked_at=datetime(2026, 10, 5, 13, 0, tzinfo=UTC)
    )
    await _seed_mark(
        db_session,
        task_b1.id,
        reason="another story",
        marked_at=datetime(2026, 10, 5, 14, 0, tzinfo=UTC),
    )

    marks = await _repo(db_session).list_active_for_story(story_a)

    assert [mark.id for mark in marks] == [newer.id, older.id]
    assert [mark.task_id for mark in marks] == [task_a1.id, task_a2.id]
    assert all(mark.revoked_at is None for mark in marks)
