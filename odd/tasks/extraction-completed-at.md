# ODD Feature: extraction-completed-at

> **Status**: implemented on `feat/extraction-completed-at` (off `main` @ `8a33baf`), not pushed.
> Green and mutation-checked; the independent verification is recorded below. Receipt-driven
> development is **off** in this clone, so no native review ran.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/extraction-completed-at`.

## Problem

`completed_at` was a **phantom field**. It was not a column on `tasks` and not a column on
`extractions`; it existed only as an always-`null` default on `ExtractionResponse`
(`api/schemas/extraction.py:51`), hardcoded to `None` at three construction sites
(`api/routes/extractions.py:146` and `:185`, `api/routes/extraction.py:298`), with **zero** writes
and zero reads anywhere. `docs/api.md` stated the invariant honestly — "`completed_at` viaja
siempre en `null`" — and **no test asserted anything about the field**: a grep across
`backend/tests`, `frontend/src` and `frontend/e2e` returned exactly one hit, the frontend type
declaration.

So the API advertised a completion timestamp that was structurally incapable of being set, and a
finished extraction had no recorded end time.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Set it, do not drop it | **User-approved**: a finished extraction gets a real timestamp. The alternative — removing the phantom field — was offered and rejected, because the value is meaningful and simply was never wired. |
| D2 | The three layers | Column (revision `0023`) + field on the `Extraction` entity + the three `completed_at=None` literals replaced by the stored value. |
| D3 | Where it is stamped | **At the write sites, not in the entity** — and the reason is the read path. See below; this is the decision the design turns on. |
| D4 | Nullability | The column is nullable, because a `pending` extraction has not finished. The invariant is "non-null exactly when the status is terminal", and it has its own tests. |
| D5 | No backfill | An extraction that finished before the column existed has no recoverable end time. Copying `created_at` would report an instantaneous run and `now()` would report every historical row as completing at deploy time. Both invent data; the rows keep `NULL`. |
| D6 | Docs | `docs/api.md` (both the claim and the now-incoherent example, which showed `status: completed` beside `completed_at: null`) and the `extractions` table in `docs/database.md`. |
| D7 | Coverage | The contract assertion the field never had, plus the invariant on both sides, plus the migration, plus — the part that mattered — the failure paths. |

## D3, the decision the design turns on

The tidy-looking alternative was to derive the value inside the entity: a `__post_init__` that
stamps any terminal construction, so no call site can forget. It is wrong, and the reason is worth
recording because it is not obvious:

The repository reconstructs an entity from **every row it loads**. Seven of the eight terminal
rows in a fresh database are historical, and a historical row has `NULL` — by D5, deliberately.
Deriving the value would therefore hand each of those reads a **fresh timestamp**, so the API
would report a completion time that changed every time it was fetched, and the no-backfill decision
would be silently undone by the thing that was supposed to enforce it.

So the value is stamped explicitly by the call sites that reach a terminal state. There are
**six**, not the four the plan first listed:

| Site | Path |
|------|------|
| `extraction_task.py:181` | `recover_stuck_extractions` — a job abandoned by a crash, swept at startup |
| `extraction_task.py:420` | `_run_extraction` — the completed save |
| `extraction_task.py:480` | `_mark_failed` — the in-request failure |
| `extraction_task.py:565` | `_mark_extraction_failed` — the out-of-band failure, which opens its own session |
| `extraction_service.py:280` | the in-process service, completed |
| `extraction_service.py:315` | the in-process service, failed |

The under-count was the plan's, not a discovery at implementation time; the fourth and sixth sites
were found by grepping for terminal constructions rather than trusting the list.

## The bug this change introduced, and how it was found

Adding `completed_at=datetime.now(UTC)` to those sites produced a **real crash** on two of them,
and the 654-test suite passed straight through it.

`extraction_task.py` imports `datetime` at module level (line 27) but **four functions re-import it
locally** (`from datetime import UTC, datetime`), inside an `if` block that also imports
`dataclasses.replace`. A function-local import makes the name local for the function's entire
scope, so a use *before* that line raises `UnboundLocalError`:

```text
UnboundLocalError: cannot access local variable 'datetime' where it is not associated with a value
```

`_mark_failed` (line 487 vs its import at 495) and `_mark_extraction_failed` (575 vs 586) were
exactly that shape. Proven by replicating the shadowing pattern and by an AST pass over the real
functions that listed every `datetime` use ordered against its local import.

**The fix is the root cause, not the symptom**: the four local imports were redundant — the
module-level import already provides both names — so they were deleted. That removes the trap
rather than moving my lines below it, and it cannot recur in that file.

**Why the suite missed it, and what closed that**: `_mark_failed` and `_mark_extraction_failed` had
**zero tests**. No file in `backend/tests` referenced either one. They are failure paths, which is
the least likely place to look and the easiest to leave uncovered. Four tests now reach them, plus
the recovery sweep, and reverting the fix fails two of them.

## A latent defect the new coverage found

Writing the sweep test surfaced a **pre-existing** bug in `recover_stuck_extractions`:

```python
deadline = datetime.now(UTC) - timedelta(minutes=max_age_minutes)   # aware
...
if ext.status == ExtractionStatus.PENDING and ext.created_at and ext.created_at < deadline:
```

`ext.created_at` comes back **naive** from SQLite (which has no timezone type) and **aware** from
Postgres, so the comparison is a `TypeError` on one and fine on the other. It has never fired in
production because production runs Postgres. It is fixed here, with a small `_as_utc` helper and
the reasoning in its docstring, because this feature makes the sweep a terminal site for
`completed_at` and the test that covers it cannot pass otherwise. The premise was verified before
the fix was written: SQLite drops the offset but **preserves the UTC wall clock**, so reading a
naive value as UTC is correct rather than convenient.

## Environment facts worth keeping

- **SQLite drops `tzinfo` on a `DateTime(timezone=True)` column** and keeps the instant. The repo
  already documents this convention in `test_custom_provider_repo.py:127`; `completed_at` inherits
  it, and the round-trip test says so rather than papering over it. Postgres, which production
  runs, keeps the offset.
- The repo's **`Result.rowcount` pattern appears in seven repositories** and one analyzer
  (pi-lens, not Pyright, which is not even installed) reports it as an untyped attribute. Proved
  false at runtime: on the real repository path, deleting an absent id raises `EntityNotFound`
  through that branch. The extraction repository's `delete` was rewritten to go through the
  session's identity map anyway, because two analyzer findings on one line is a poor trade for a
  count that is not needed.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Backend suite | `python -m pytest -q` | **667 passed, 1 skipped** (654 before, +13) |
| Backend lint (CI scope) | `ruff check src tests` | `All checks passed!` |
| Backend format | `ruff format --check src tests` | `217 files already formatted` |
| Frontend suite | `pnpm vitest run` | 36 files / 420 passed (unchanged: `completed_at` was already typed `string \| null`) |
| Types | `pnpm exec tsc --noEmit` | exit 0 |
| The crash, before the fix | replicate the shadowing pattern | `UnboundLocalError: cannot access local variable 'datetime'` |
| The crash, ordered in the real code | AST pass over `extraction_task.py` | `_mark_failed` use@487 < import@495; `_mark_extraction_failed` use@575 < import@586 |
| The tz defect, before the fix | the new sweep test | `TypeError: can't compare offset-naive and offset-aware datetimes` |
| Non-vacuity, the tz fix | remove `_as_utc` | **2 tests fail**; green on restore |
| SQLite keeps the instant | write aware UTC, read back | `2020-01-01 03:30:00+00:00` → `2020-01-01 03:30:00`, same wall clock |
| No invention on read | `test_reading_a_terminal_row_invents_no_end_time` | a terminal row stored with `NULL` reads back `NULL`, twice |
| Parameterization (for the analyzer) | compile the `INSERT` | 5 bound parameters, `llama3.2` not interpolated |

New tests: the migration (4: nullable, no backfill of existing rows, downgrade, correct parent),
the repository (4: round trip, pending has none, a historical null stays null, delete), the failure
paths (4: `_mark_failed`, `_mark_extraction_failed`, the recovery sweep, a pending job untouched),
the contract (1), and one assertion in each of the two service tests that already exercise the
terminal branches.

## Follow-ups this surfaced, recorded rather than bundled

1. **`Result.rowcount` is untyped in six other repositories** (`project`, `task`, `user`,
   `user_story`, `workspace_member`, `workspace`). The analyzer complains about the extraction one
   only because it sits in a changed file. Nothing is wrong at runtime; a shared helper or a typed
   cast in all seven would settle it, and doing one alone is worse than doing none.
2. **Pyright is not a gate**: not in `backend/pyproject.toml`, not in the CI workflow, not in
   pre-commit, and not installed in the venv. The findings in this session's edit loop came from
   pi-lens's bundled analyzer, and the repository already records a stale-cache problem with it.
   Either wire it in or stop treating its output as authoritative — the current state is a gate
   that exists only in an editor.
3. **Gemini's built-in branch still has no positive-construction test** in
   `test_llm_test_route.py` (carried over from the previous slice).
4. **`recover_stuck_extractions` swallows a `list()` failure** with a warning and returns, so a
   database problem at startup is invisible. Out of this feature's scope; noted because the test
   had to work around the function's structure.

## Tasks — all closed

- [x] Confirm the extraction table's columns and the head revision before writing the migration.
- [x] Entity field + revision `0023` with a working `downgrade` and the deploy-order note.
- [x] Stamp both terminal transitions — all six sites, including the two the plan had missed.
- [x] Replace the three `completed_at=None` literals.
- [x] Fix the `UnboundLocalError` by removing the redundant local imports (root cause).
- [x] Fix the pre-existing tz comparison the new sweep test found, with its premise verified.
- [x] Tests: contract, both directions of the invariant, no-invention on read, migration up/down, and the four failure paths that had none.
- [x] Correct `docs/api.md` (claim and example) and `docs/database.md`.
- [x] Run backend `ruff check src tests`, `ruff format --check src tests`, `pytest -q`; frontend `tsc --noEmit` and `vitest run`.
- [ ] Work-unit commits on the feature branch — **pending**.
- [ ] Independent verification — **pending**.
- [ ] Fast-forward into `main`, delete the branch, re-gate — **pending**.
