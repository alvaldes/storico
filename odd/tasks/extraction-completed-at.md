# ODD Feature: extraction-completed-at

> **Status**: planning — no commit, no evidence yet.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/extraction-completed-at` (to be created off `main` @ `6174f5a`).
> **Receipt-driven development**: off in this clone.

## Problem

`completed_at` is a **phantom field**. It is not a column on `tasks` and not a column on
`extractions`; it exists only as an always-`null` default on the response schema:

```python
# backend/src/storico/api/schemas/extraction.py:51
completed_at: datetime | None = None
```

It is hardcoded to `None` at three construction sites and never written or read anywhere else:

- `backend/src/storico/api/routes/extractions.py:146`
- `backend/src/storico/api/routes/extractions.py:185`
- `backend/src/storico/api/routes/extraction.py:298`

`docs/api.md:257` states the invariant honestly — "`completed_at` viaja siempre en `null`" —
and no test asserts anything about the field at all (`grep` across `backend/tests`,
`frontend/src` and `frontend/e2e` returns only the frontend type declaration at
`frontend/src/types/extraction.ts:30`).

So the API advertises a completion timestamp that is structurally incapable of being set, and a
completed extraction has no recorded end time anywhere.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Set it, do not drop it | **User-approved**: a finished extraction gets a real timestamp. The alternative (removing the field) was rejected because the value is genuinely meaningful and simply was never wired. |
| D2 | The three layers | Column (Alembic revision `0023`) + field on the `Extraction` domain entity (`backend/src/storico/domain/entities/extraction.py:21-32`) + the three `completed_at=None` literals replaced by the stored value. |
| D3 | Which transitions set it | Both terminal ones. `_run_extraction`'s `ExtractionStatus.COMPLETED` save (`extraction_task.py:418-435`) and the failure path (`_mark_failed`, `extraction_task.py:468-486`), plus the in-process twins at `extraction_service.py:280` and `:315-316`. A terminal state with no end time is the same bug in a different status. |
| D4 | Nullability | The column is nullable, because a `PENDING` extraction has not completed. The invariant is "non-null exactly when the status is terminal", and that invariant gets its own test. |
| D5 | Not `created_at` rewritten | `created_at` stays the start. This adds a distinct value; it does not repurpose an existing one. |
| D6 | Docs | `docs/api.md:257` and the `extractions` table entry in `docs/database.md` (`:184-196`) are corrected in this slice; the currently-unverified "always null" claim is replaced by the real invariant. |
| D7 | Coverage | The field has no test today. Add the contract assertion that was missing (`tests/contract/test_api_schemas.py` has a `TestExtractionResponseContract` that does not mention it) plus the status/timestamp invariant. |

## Non-goals

- No task-level completion timestamp. `TaskService.update_status` and the inline `replace` at
  `routes/tasks.py:282-297` record only `updated_at`; whether `tasks` should record its own
  completion time is a separate question with a separate migration.
- No backfill of historical rows: an extraction that finished before this change has no
  recoverable end time. Backfilling from `updated_at` would invent data. Rows keep `NULL` and
  that is recorded, not hidden.

## Tasks

- [ ] Confirm the extraction table's current columns and the head revision (`0022`) before
      writing the migration.
- [ ] Entity field + migration `0023` (with a working `downgrade`).
- [ ] Set it on both terminal paths in `extraction_task.py` and in `extraction_service.py`.
- [ ] Replace the three `completed_at=None` literals.
- [ ] Tests: contract assertion, terminal-vs-pending invariant, failure path, migration
      up/down.
- [ ] Correct `docs/api.md` and `docs/database.md`.
- [ ] Run backend `ruff check`, `ruff format --check`, `pytest -q` (including the Postgres
      integration test); frontend `tsc --noEmit` and `vitest run` if the type changes.
- [ ] Work-unit commits on the feature branch.
- [ ] Independent verification.
- [ ] Fast-forward into `main`, delete the branch, re-gate.

## Evidence

_None yet._
