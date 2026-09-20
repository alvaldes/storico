# ODD Feature: extraction-completed-at

> **Status**: done and landed on `main` @ `2ab0001` — six commits from `8a33baf`: `f572c4b`,
> `0eeed2c`, `1864622` (the implementation and its record) then `46393ec`, `ef12334`, `2ab0001`
> (the answers to the verification). Branch deleted, `main` re-gated, **not pushed**. Receipt-driven
> development is **off** in this clone, so no native review ran; an independent verification did,
> and it found that the one site production actually takes had no test at all.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/extraction-completed-at`.

## Process correction: the review switch was on

**This record said receipt-driven development was "off in this clone", and for the second half of
this session that was false.** The switch read `off (decided by default)` when the session began, and
was turned on globally mid-session — `~/.gentle-ai/state.json` records `rdd_mode = 'on'` with
`rdd_mode_recorded_at = 2026-09-19T18:49:02Z`. This record's line was copied forward from the earlier
features without re-checking it, which is **the same defect this batch spent the day removing**: a
claim about state, written once and never re-read.

So native review was the expected path for this candidate and it did not run. Independent verification
did, and it found something material; its findings are recorded below. Whether that is an adequate
substitute is the maintainer's call, not this record's.

It could not have run from the parent session regardless: the `gentle_review` facade answers
`native-status-package-binary-missing` here, while a subagent's context reached the lifecycle and
returned an unresolved provider consent envelope for the last candidate. The recovery is
`node scripts/install-gentle-ai.mjs` from the installed package directory, which is a maintenance
action rather than something this session takes on its own.

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
| Backend suite | `python -m pytest -q` | **668 passed, 1 skipped** (654 before, +14) |
| Backend lint (CI scope) | `ruff check src tests` | `All checks passed!` |
| Backend format | `ruff format --check src tests` | `217 files already formatted` |
| Frontend suite | `pnpm vitest run` | 36 files / 420 passed (unchanged: `completed_at` was already typed `string \| null`) |
| Types | `pnpm exec tsc --noEmit` | exit 0 |
| The crash, before the fix | replicate the shadowing pattern | `UnboundLocalError: cannot access local variable 'datetime'` |
| The crash, ordered in the real code | AST pass over `extraction_task.py` | `_mark_failed` uses `datetime` before its function-local import, and so does `_mark_extraction_failed` |
| The tz defect, before the fix | the new sweep test | `TypeError: can't compare offset-naive and offset-aware datetimes` |
| Non-vacuity, the tz fix | remove `_as_utc` | **2 tests fail**; green on restore |
| SQLite keeps the instant | write aware UTC, read back | `2020-01-01 03:30:00+00:00` → `2020-01-01 03:30:00`, same wall clock |
| No invention on read | `test_reading_a_terminal_row_invents_no_end_time` | a terminal row stored with `NULL` reads back `NULL`, twice |
| Parameterization (for the analyzer) | compile the `INSERT` | 5 bound parameters, `llama3.2` not interpolated |

New tests: the migration (4: nullable, no backfill of existing rows, downgrade, correct parent),
the repository (4: round trip, pending has none, a historical null stays null, delete), the failure
paths (4: `_mark_failed`, `_mark_extraction_failed`, the recovery sweep, a pending job untouched),
the completed save (1 — see the verification below, which is what demanded it), the contract (1), and
one assertion in each of the two service tests that already exercise the terminal branches.

## Independent verification

Ran over `8a33baf..1864622`, read-only. The record's five counts all reproduced exactly, and the
verifier derived the six terminal sites **from the source rather than from the record**, checking
the indirect paths too (raw SQL in migrations, direct ORM writes, `dataclasses.replace`, the CLI
seeder, the startup sweep): all six stamp the field, and no terminal write misses it. It also
falsified D3's rejected alternative by actually applying it — an entity that derives the value in
`__post_init__` hands a historical `NULL` row a fresh timestamp on read, failing
`test_reading_a_terminal_row_invents_no_end_time` — and confirmed the API really returns the field
(`"completed_at":"2026-09-19T12:00:04"` on a completed extraction, `null` on a pending one and on a
historical one).

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| V1 | **high** | **The completed save — the site production actually takes — had no test.** Removing its stamp left the whole suite green (667 passed, 1 skipped); `extraction_task.py`'s coverage showed lines 399–468 never executing, because the only test that calls `run_background_extraction` drives it into `UnreachableLLM` and dies first. The failure paths were covered and the happy path was not. | **Fixed** — `test_the_completed_save_records_when_it_finished` drives the real pipeline with an answering adapter and asserts the saved extraction is `COMPLETED` with a non-null end time after `created_at`. Re-ran the verifier's own mutation: it now fails. |
| V2 | low | `_as_utc`'s docstring said SQLite "drops the offset", full stop, implying the instant survives. It does not convert: an `03:30-05:00` written and read back is `03:30`, not `08:30`. The helper is correct **only because everything written is UTC**. | **Fixed** — the docstring now says it drops the offset *without converting* and states the condition it depends on, plus the evidence that the condition holds (every `datetime.now` in the module passes `UTC`). |
| V3 | low | SQLite and Postgres serialize the field differently — `"2026-09-19T12:00:04"` versus `"2026-09-19T12:00:04Z"` — and `new Date("...04")` in JavaScript reads the first as **local** time, so the same instant renders differently in dev than in production. | **Recorded** — pre-existing (it is `created_at`'s convention too, documented in `test_custom_provider_repo.py:127`) and newly visible on a new field. See the follow-ups. |
| V4 | info | The record's line numbers for the crash (`use@487 < import@495`) are not reproducible from git: no committed revision has the stamps and the local imports coexisting, so they describe a working-tree state. | **Fixed** — the record names the functions instead of lines that never existed in a commit. |

Also confirmed by the verifier: the `UnboundLocalError` fix is complete with a **positive control**
(an AST pass over the reconstructed intermediate state finds the two helpers; over the fixed
revision and over `main` it finds nothing), the same shadowing pattern exists for **no other name**
in any file under `src/` or `tests/`, there is **exactly one** stored-datetime ordering comparison
in the backend and it is the one fixed, the migration's deploy order was proved by loading the ORM
against a column-less table (`OperationalError: no such column`), and no test was removed, skipped
or loosened (566 → 580 test nodes, +14, none deleted).

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
5. **A naive timestamp serializes without an offset**, so a client that parses it with `new Date()`
   reads it as local time while the Postgres-shaped `...Z` reads as UTC. That is a frontend hazard
   rather than a backend one (the type, `string | null`, is right either way), it predates this
   change on `created_at`, and this change gives it a second field to appear on. Worth one decision:
   either serialize with an explicit offset server-side, or make the client parse as UTC.

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
- [x] Work-unit commits on the feature branch (`f572c4b`, `0eeed2c`, `1864622`, plus the answer to the verification).
- [x] Independent verification — the six sites and the design decision confirmed by falsification; V1 (a real coverage hole on the production happy path) fixed and re-mutated, V2 and V4 corrected, V3 recorded.
- [x] Fast-forward into `main`, delete the branch, re-gate — `main` @ `2ab0001`; backend
      668 passed / 1 skipped with `ruff check src tests` clean and 217 files formatted, frontend
      36 files / 420 tests and `tsc --noEmit` exit 0 — all re-run **after** the merge.
