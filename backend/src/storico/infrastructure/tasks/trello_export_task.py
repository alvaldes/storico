"""Startup recovery for Trello export jobs — the sweep ``trello_exports`` never had.

Mirrors ``recover_stuck_extractions`` (``infrastructure/tasks/extraction_task.py``)
and is wired in the same lifespan block: a job row stranded at ``pending`` or
``running`` by a crash or a cancelled task is not an honest record of work in
progress — it is a member polling forever. The sweep marks those rows ``failed``
with ``TRELLO_EXPORT_INTERRUPTED`` so the row answers, and the member can
re-trigger (D3 makes retrying safe: a repeated export creates a new board).

Where it deviates from the extraction sweep, and why:

- The extraction sweep marks only ``pending`` rows; this one also marks
  ``running``, because a cancelled task leaves the row at ``running`` — the
  defect the WU5 repair closed — and ``running`` is exactly the state a dead
  process strands a job in.
- The extraction sweep lists every extraction and filters both status and age
  in Python; this one bounds the status in the query (``find_by_statuses``)
  and filters only the age in Python, with the same naive/aware guard the
  extraction module documents for SQLite timestamps.
- The extraction sweep writes a free-text ``error_info``; this table's polling
  contract is a code, so the sweep writes ``TRELLO_EXPORT_INTERRUPTED``.
- The extraction sweep lets a fault in one row's write abandon the rest of the
  recovery — its per-row ``save`` is unguarded — so one bad row leaves every
  healthy row behind it waiting for the next boot. This one guards the per-row
  write, logs the fault, and keeps going, because the next row may be perfectly
  writable.

It inherits the extraction sweep's age limitation: a row younger than the bound
at boot is left alone, so a job abandoned minutes before a restart is only
swept at the next one.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from datetime import UTC, datetime, timedelta

from storico.api.error_codes import TRELLO_EXPORT_INTERRUPTED
from storico.domain.entities.trello_export import TrelloExportStatus
from storico.infrastructure.database.base import create_session_factory, get_engine
from storico.infrastructure.database.repositories import SQLAlchemyTrelloExportRepository

logger = logging.getLogger(__name__)

# ``running`` is included on purpose — see the first deviation in the module docstring.
_STALE_STATUSES = frozenset({TrelloExportStatus.PENDING, TrelloExportStatus.RUNNING})


def _as_utc(value: datetime) -> datetime:
    """Read a stored timestamp as UTC.

    Same guard as the extraction sweep: SQLite has no timezone type, so a
    ``DateTime(timezone=True)`` column comes back naive and an aware deadline
    cannot be compared against it directly. Everything written to these columns
    is UTC, so a naive value is already UTC wall clock.
    """
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


async def recover_stuck_trello_exports(max_age_minutes: int = 5) -> None:
    """Mark ``pending``/``running`` Trello export jobs older than
    *max_age_minutes* as ``failed``.

    Call this once during application startup to clean up jobs abandoned when
    the server crashed or a task was cancelled before it could write its own
    terminal state.
    """
    factory = create_session_factory(get_engine())
    async with factory() as session:
        repo = SQLAlchemyTrelloExportRepository(session)
        try:
            candidates = await repo.find_by_statuses(_STALE_STATUSES)
        except Exception:
            logger.warning("Could not list Trello export jobs for recovery")
            return

        deadline = datetime.now(UTC) - timedelta(minutes=max_age_minutes)
        recovered = 0
        for job in candidates:
            if job.created_at is None or _as_utc(job.created_at) >= deadline:
                continue
            try:
                await repo.save(
                    replace(
                        job,
                        status=TrelloExportStatus.FAILED,
                        error_code=TRELLO_EXPORT_INTERRUPTED,
                        completed_at=datetime.now(UTC),
                    )
                )
            except Exception:
                # One unwritable row must not abandon the rest — the next row
                # may be fine, and the next boot is a long way off. The faulted
                # row is left as it stands and tried again at the next boot.
                logger.exception("Could not recover stuck Trello export job %s", job.id)
                continue
            recovered += 1

        if recovered:
            logger.warning("Recovered %d stuck Trello export job(s)", recovered)
