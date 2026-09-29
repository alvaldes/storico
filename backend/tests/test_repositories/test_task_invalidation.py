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
from sqlalchemy.ext.asyncio import AsyncSession

from storico.infrastructure.database.models import TaskModel


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
