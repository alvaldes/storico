# Tasks: Extraction Versioning — Schema and Version Identity

Slice (a) of three for Storico 0.9.0. Planning artifact only: every line below is unchecked and no
line claims a check that has not run. Evidence base: `explore.md` (`main` `ecea3e2`), the two specs
(14 requirements), the 11 design decisions, and `openspec/config.yaml` (`strict_tdd: true`).

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ≈2,250–3,000 for the whole slice |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | WU1 (unsplittable, over budget on its own) → WU2 → WU3 (optionally 3a → 3b) → WU4 |
| Delivery strategy | ask-on-risk |
| Chain strategy | deferred until chaining is selected |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

Delivery strategy: ask-on-risk
Chain strategy: deferred until chaining is selected
size:exception: not accepted

### Delivery decision — accepted by the user on 2026-09-28, before apply

This block records the answer to the `ask-on-risk` pause. The three lines above are the forecast as it
was issued and are kept unchanged.

```text
Delivery strategy: ask-on-risk — resolved
Chain strategy: chained PRs, one PR per work unit
size:exception: accepted for (a) WU1, (b) WU2 and (b) WU4 only
```

- This slice chains per work unit in the order the Per-Work-Unit Estimate table already states
  (`WU1 → WU2 → WU3a → WU3b → WU4`), each unit starting from the previous unit's green head.
- **`size:exception` is accepted for `WU1` of this slice and for no other unit here.** WU1 is
  ≈1,300–1,700 lines because the new `NOT NULL` columns break every legacy test seed at once, and the
  alternative — a nullable bridge revision — is the shape the slice's one-revision decision rejects.
  The acceptance does not waive the review; it acknowledges that the first PR of the feature is a
  schema-plus-seed-migration read, not a skim, and that its size is the point of the change.
- `WU3` is **not** covered by the exception: it splits 3a → 3b as scheduled, and each half fits.
- The acceptance is scoped to the three units named above across the three slices. It transfers to no
  other unit, and a unit that turns out larger in practice than forecasted goes back on the table
  rather than being absorbed.

### Per-Work-Unit Estimate

| Work unit | Start state | Estimated changed lines (additions + deletions) | Fits 400-line budget? |
|-----------|-------------|------------------------------------------------|------------------------|
| **WU1 — Schema identity + birth through allocation (Phases 1+2, merged 2026-09-29)** | `main` `ecea3e2`, head `0027` | ≈1,400–1,900 | **No — and it cannot be split** |
| ~~WU2 — Birth through allocation (Phase 2)~~ | absorbed into WU1 | ≈100–150 | — |
| WU3 — Render-time snapshot + terminal marks (Phase 3) | WU1 green | ≈600–800 (≈300–420 per half if split 3a/3b) | No as designed; yes only split |
| WU4 — Invalidation invariants (Phase 4) | WU1 green (model already migrated) | ≈250–350 | Yes |
| **Slice total** | | **≈2,250–3,000** | **No** |

### Boundary correction — measured 2026-09-29, before any GREEN was written

The Phase 1 / Phase 2 boundary in the first version of this file was **wrong**. WU1 as forecast could
not have ended green, and the two proofs are in the code, not in judgement:

1. **`save()` writes columns `0028` declares `NOT NULL`.** Task 1.13 keeps `save()` and states
   `_to_orm_kwargs` omits `version_number`; today that helper writes exactly the twelve pre-`0028`
   keys (`extraction_repository.py:152-164`). An INSERT that names neither `version_number` nor
   `provider` nor `temperature` against the `0028` shape is refused — reproduced directly on SQLite:
   `IntegrityError: NOT NULL constraint failed: e.provider`. Task 1.12 kept `save()` *because* its
   route, runner and `extract_and_persist` callers were "rewired in Phases 2–3", which is precisely
   the argument that puts Phase 2 inside Phase 1: the birth path is a Phase 2 file.
2. **Task 1.9 makes `provider`/`temperature` required on the entity, and three of the src
   construction sites live in later phases.** `api/routes/extraction.py:230` is owned by task **2.3**;
   `domain/services/extraction_service.py:293` and `:329` are owned by task **3.4**. Landing 1.9 alone
   leaves three `TypeError` sites red.

So WU1 and WU2 are one unit. The user was asked again, on this measurement, and re-accepted the
`size:exception` for the merged unit; PR 1 is ≈1,400–1,900 lines and slice (a) chains **4 PRs, not 5**.

Two decisions follow from the merge, both taken by the user on 2026-09-29:

- **`extract_and_persist` allocates.** The dead, test-only path builds its `Extraction` with
  `create_next_version` instead of `save()` (≈10 lines). This also discharges, in PR 1, the hazard this
  file's own "Hazards" list recorded — "the dead path mints two numbers for one run" — because a row
  that allocates at birth cannot mint a second one. Its nine cases are re-pointed at the live path in
  Phase 3 as scheduled.
- **The four rebuild sites, not three.** `extraction_task.py` has **four** `Extraction(...)` rebuilds
  (`:191` recovery sweep, `:430` completed, `:498` failed, `:592` failed-on-retry). Task 1.15 said
  "three terminal rebuild sites" and counted the recovery sweep separately; the file list in 1.16 also
  omitted `tests/test_services/test_extraction_service.py`, which is the suite that exercises
  `extract_and_persist`. Both are corrected in Phase 1/2 below.

**What runs in PR 1, in order.** Phase 1 (1.1–1.20) plus Phase 2's 2.1–2.5, with 2.6 (the
`tests/test_api` refactor pass) taken by the merged unit as well. Phase 3 keeps the render-time
snapshot, the terminal marks, `save()` removal and the nine re-pointed cases; Phase 4 keeps
`task_invalidations`' invariants. Task ids are **not renumbered**: slices (b) and (c) cite
`(a) 2.3`, `(a) 3.4` and `(a) 3.7` by these numbers, and renumbering would silently break those
references. "PR 1" means one commit, not one task range.

- 2.1 RED landed 2026-09-29 in `backend/tests/test_api/test_extraction.py`
  (`TestExtractionVersioningAtBirth`, six cases): birth carries `version_number == 1`, the
  workspace's `provider`, `0.1` when the body omits `temperature` and the explicit value when it
  does not, `prompt_config` keeps no `temperature` key, and two POSTs on one story mint 1 then 2.
- The RED of Phase 1 and Phase 2 together is **18 cases**; the pre-tranche baseline of 1008 unit
  passes is untouched (`1010 passed` = 1008 + the two guard cases named below).

**A second Phase-3 clause was pulled into PR 1 while GREEN ran, by the same logic.**
`infrastructure/tasks/extraction_task.py:466` builds the extracted `Task` rows, and task **3.5** owns
"build every `Task` with `extraction_id=extraction_id`" — but `tasks.extraction_id NOT NULL` lands in
PR 1. Two pre-existing cases (`test_the_completed_save_records_when_it_finished`,
`test_the_rag_point_records_the_real_model_and_no_judge_confidence`) fail because the runner's
`Task(...)` insert is refused, the run dies and the extraction is marked failed. Same root cause as
the Phase 1/2 merge: a `NOT NULL` introduced in a unit cannot have its writer scheduled in a later
unit, because the later unit is the only place the earlier one could go green. Phase 3 therefore
drops 3.5's `extraction_id` clause from its scope (it keeps the marks swap, `record_rendered_prompt`,
`_get_created_at` removal and the nine re-pointed cases) and PR 1 gains four constructor arguments:
`extraction_task.py:466` and the three `Task(...)` sites in `extraction_service.py`'s
`extract_and_persist`. Nothing else moved: the terminal writes stay `save()` until Phase 3.

### Landed size versus the forecast — measured after GREEN

| Area | Changed lines | Files |
| --- | --- | --- |
| production `backend/src/**` | 697 | 15 |
| new unit test files (`test_task_invalidation`, `test_extraction_versioning_migration`) | 268 | 2 |
| rewired existing tests (seeds through `create_next_version`, the two 201→500 refusals, the 2.5 triangulations) | 1,160 | 12 |
| **reviewable without a Docker daemon** | **2,125** | **29** |
| new Postgres-only integration file (task 1.18/1.19) | 532 | 1 |
| **code total** | **2,657** | **30** |

The forecast re-accepted on 2026-09-29 was ≈1,400–1,900, so PR 1 came in ≈760–1,260 lines over it.
The shape of the overage is the forecast under-counting the seeds, not scope creeping: every seed
that moves through `create_next_version` drags its assertions with it, and the two test files the
plan asked for as new were priced as edits.

**PR 1 is not splittable into greener commits.** A commit carrying `0028` without the rewired seeds is
a red suite, which the repo's work-unit rule forbids — and that same argument is what earned the
`size:exception` in the first place. What *is* separated is the part no reviewer on this machine can
execute: the integration file lands as its own commit, so the reviewable core stays at 2,125 lines and
the 532 Postgres-only lines are judged by CI, which is the only place they have ever run.

The overage goes back to the user rather than being absorbed; it is recorded here so the next session
reads the size that actually landed, not the one that was predicted.

These are `additions + deletions`. They are built from what the design actually touches: migration
`0028` with its guard and `downgrade()` (≈210–260 new lines), four ORM models, four domain
entities/ports, the repository rewrite (allocation + retry + discrimination + three targeted write
methods + `save`/`delete` removal), the route, the runner, the render/generate split with
`extract_and_persist` deleted (~140 lines out), the dead path's nine migrated cases, the ~32 test
seeds the new `NOT NULL` columns break, and the new unit/integration test files.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test | Runtime harness | Rollback boundary |
|------|------|-----------|--------------|-----------------|-------------------|
| 1 | Schema identity: `0028`, models, entities, repository allocation/current-version/marks, seeds rewired | PR 1 (over budget — needs the delivery decision) | `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_extraction_repo.py tests/test_unit/test_extraction_versioning_migration.py -m "not integration"` | SQLite in-memory (suite default); Postgres half needs Docker | Revert `0028` via `downgrade`, then the models/entities/port/repo and the seed rewiring |
| 2 | Birth through allocation: route mints the number and writes the snapshot columns; one `temperature` | PR 2 | `cd backend && conda run -n storico python -m pytest tests/test_api/test_extraction.py -m "not integration"` | FastAPI `TestClient` over SQLite | Revert `api/routes/extraction.py`, `llm_port.py`, the runner's `temperature` typing |
| 3 | Render-time snapshot + terminal marks + dead path deleted | PR 3 (one unit, or 3a → 3b) | `cd backend && conda run -n storico python -m pytest tests/test_unit/test_extraction_failure_paths.py tests/test_services/test_extraction_service.py -m "not integration"` | SQLite in-memory; `tests/test_extraction_flow_few_shot.py` for the few-shot wiring | Revert `extraction_service.py`, `extraction_task.py`, the migrated cases; restore `save()`/`extract_and_persist` if the whole slice is reverted |
| 4 | Invalidation mark invariants (reason, one active mark, revoke-as-update, attribution, version membership) | PR 4 | `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_task_invalidation.py -m "not integration"` | SQLite in-memory (`sqlite_where` mirror); Postgres index shape/cascades need Docker | Delete `tests/test_repositories/test_task_invalidation.py` and the integration additions; the table itself reverts with `0028` |

### Why the budget cannot be met by slicing

**WU1 is atomic, and its overage is a budget breach, not a chain-strategy question.** Two `NOT NULL`
extraction columns plus `tasks.extraction_id NOT NULL` break every test that inserts an extraction or
a task directly — about twenty `Extraction(...)` sites and about a dozen `Task(...)` sites across
`tests/test_repositories/test_extraction_repo.py`, `tests/test_repositories/test_list_by_workspaces.py`,
`tests/test_repositories/test_task_repo.py`, `tests/test_api/test_extractions.py`,
`tests/test_api/test_extraction.py`, `tests/test_api/test_export.py`, `tests/test_api/test_tasks.py`,
`tests/test_api/test_unfiltered_list_queries.py`, `tests/test_unit/test_extraction_failure_paths.py`
and `tests/integration/test_state_machine_scenarios.py` — and the SQLite test schema enforces
`NOT NULL` exactly as Postgres does. There is no green intermediate: a nullable bridge revision is
precisely what the design's one-revision decision rejects, and a red suite is what the repo's
work-unit rule forbids. The same atomicity makes WU1 touch
`infrastructure/tasks/extraction_task.py`'s three terminal `Extraction(...)` rebuild sites, because
the entity's new required fields are visible to the type checker the moment the model lands.

**WU3 is over budget as one unit but has an honest split axis**: (3a) `RenderedPrompt` +
`render()`/`generate()` + the render-time write, keeping `extract()` as a thin temporary wrapper, then
(3b) `mark_completed`/`mark_failed`, `save()` removal, `extract_and_persist` deletion and the nine
migrated cases. The wrapper is the only deviation the split needs, and it is what keeps each half
green. Choosing between "WU3 as one over-budget PR" and "3a → 3b" is the delivery decision this
forecast hands to `ask-on-risk`; it is not taken here.

### Verification environment (what the sandbox can and cannot prove)

- Unit layer: `cd backend && conda run -n storico python -m pytest` (optionally `-m "not integration"`).
  Runs against `sqlite+aiosqlite://` in-memory built from the models (`backend/tests/conftest.py:36`);
  SQLite 3.53.3, so `RETURNING` and partial indexes exist and `sqlite_where` is a real mirror.
- Integration layer: `cd backend && conda run -n storico python -m pytest -m integration`. Postgres 16
  via testcontainers; every test is marked `@pytest.mark.integration` individually and carries the
  `_docker_reachable()` skipif pattern of `backend/tests/test_integration/test_migration_chain.py`.
  **Without a Docker daemon these skip, and the invariant stays unverified** — that is the honest
  status, not a green.
- Unverifiable without Docker: the empty-database half of `0028` (DDL and `downgrade`), the duplicate
  `(user_story_id, version_number)` pair, `tasks.extraction_id NOT NULL`, "no current flag / trigger /
  matview", the story cascade, the real allocation collision, the *partial* shape of
  `uq_task_invalidations_active_task`, `ON DELETE SET NULL` attribution, and the existing drift gate.
- Provable without Docker: the refusal arm of `0028` (it raises before any DDL, so SQLite reaches it),
  revision metadata, allocation numbering and retry bound/discrimination, current-version derivation,
  the SQLite-mirrored `CHECK`s and partial index.
- `0028` only ever runs on an empty `extractions`/`tasks` pair. The D11 data wipe is a **separate
  destructive operation**, executed with its own confirmation before the deploy that carries `0028`.
  It is deliberately not a task in this file.

## Spec Coverage

| Requirement (spec) | Covered by |
|--------------------|------------|
| R1 One Version Per Run, Numbered Per Story | 1.1, 1.4, 1.13, 1.18, 5.2 |
| R2 Every Run Consumes a Number, Including a Failed One | 1.1, 1.13, 1.17, 2.1, 3.2, 3.4, 3.5 |
| R3 Current Version Is Derived, Never Stored | 1.1, 1.12, 1.13, 1.17, 5.4 |
| R4 Concurrent Runs Receive Distinct Numbers | 1.1, 1.13, 1.18, 2.5 |
| R5 Every Extracted Task Belongs to Its Extraction | 1.6, 1.10, 1.14, 1.16, 1.17, 3.2, 3.5, 3.8 |
| R6 Each Version Freezes Its Run Snapshot at Render Time | 1.17, 2.1, 2.2, 2.3, 2.4, 3.1, 3.4, 3.5 |
| R7 Nothing Inside a Version Is Ever Deleted | 1.12, 1.13, 1.17, 3.4, 3.7, 5.4 |
| R8 The Migration Refuses Legacy Data and Never Backfills | 1.3, 1.4, 1.17, 5.3 |
| R9 The Mark Is a Row in `task_invalidations` | 1.7, 1.8, 4.1, 4.2, 4.3 |
| R10 The Reason Is Mandatory as a Database Invariant | 1.7, 4.1, 4.2, 4.4 |
| R11 At Most One Active Mark Per Task | 1.7, 4.1, 4.2, 4.3 |
| R12 Revoking Is an Update, Never a Delete | 4.1, 4.2 |
| R13 Actor References Survive Account Deletion | 1.7, 4.3 |
| R14 The Mark Belongs to the Version It Was Made On | 4.1, 4.2 |

---

## Phase 1: WU1 — Schema Identity (atomic, over budget)

Runner for this phase: `cd backend && conda run -n storico python -m pytest` (unit layer), plus
`-m integration` for the Postgres half. STRICT TDD order: RED first, then GREEN, then TRIANGULATE,
then REFACTOR.

> **RED tranche executed 2026-09-29** (tasks 1.1–1.3, on branch `feat/extraction-versioning-schema-wu1`).
> Measured: `12 failed, 1010 passed, 21 deselected` versus the pre-tranche baseline of
> **1008 passed, 21 deselected** — no existing case moved. `ruff check` and `ruff format --check`
> clean on all three files. Two of the fourteen new cases are green on purpose and are guards, not
> behaviour: `test_the_unit_environment_supports_returning` pins the SQLite `>= 3.35.0` precondition
> (the fallback if it fails is the recorded by-primary-key re-read), and
> `test_tasks_carry_no_invalidation_columns` protects the rejected shape that task 1.6 must not
> create. Every other new case fails on a named missing behaviour — `provider`/`temperature` absent
> from the entity, `create_next_version`/`mark_completed`/`mark_failed`/`find_current_version` absent
> from the port, `_is_version_conflict` and `VersionAllocationConflictError` absent,
> `TaskInvalidationModel` absent, and `0028_extraction_versioning.py` absent on disk. GREEN (1.4–1.17)
> is not yet authorized.

- [x] 1.1 RED — `backend/tests/test_repositories/test_extraction_repo.py`: add the failing allocation
      and derivation cases. Three `create_next_version(...)` calls on one story yield `version_number`
      1, 2, 3; the fourth yields 4 (a burned/completed number is never reused); a `pending` v3 on top
      of a completed v2 leaves `find_current_version(story)` at v2; completed v1 + failed v2 leaves it
      at v1; a `failed` row keeps its `version_number`; `_is_version_conflict` is true for an
      asyncpg-shaped error (`constraint_name == "uq_extractions_story_version"`) and for a
      sqlite3-shaped one (`UNIQUE constraint failed: extractions.user_story_id,
      extractions.version_number`) and false for a `NOT NULL` violation; a forced conflict on every
      attempt stops after 3 and raises `VersionAllocationConflictError`. Verify RED with
      `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_extraction_repo.py -m "not integration"`.
- [x] 1.2 RED — `backend/tests/test_repositories/test_task_invalidation.py` (new): assert
      `TaskInvalidationModel.__tablename__ == "task_invalidations"`, that a mark round-trips through
      the model with its reason and `marked_by`/`marked_at` and null revoke fields, and that `tasks`
      carries no invalidation or invalid-reason column (the "not a column pair" scenario).
- [x] 1.3 RED — `backend/tests/test_unit/test_extraction_versioning_migration.py` (new): load
      `0028_extraction_versioning.py` by path with the `test_add_completed_at_migration.py` pattern
      (`importlib.util.spec_from_file_location` + `MigrationContext` + `Operations.context` over a
      `StaticPool` SQLite scratch database); pin `revision == "0028"` / `down_revision == "0027"`;
      assert `sqlite3.sqlite_version_info >= (3, 35, 0)` (the `RETURNING` precondition, with the
      by-primary-key re-read as the recorded fallback); insert one row into a pre-`0028` `extractions`
      and `tasks` and assert `upgrade()` raises **and** that no `0028` column/table was created.
- [x] 1.4 GREEN — `backend/src/storico/infrastructure/database/alembic/versions/0028_extraction_versioning.py`
      (new): `upgrade()` reads `SELECT count(*) FROM extractions` and `FROM tasks` through
      `op.get_bind()` **before any DDL** and raises naming D11 when either is non-zero; then, in order,
      `version_number` (`INTEGER NOT NULL`, `ck_extractions_version_number_positive`),
      `provider` (`VARCHAR(50) NOT NULL`), `temperature` (`DOUBLE PRECISION NOT NULL`),
      `prompt_rendered` (`TEXT NULL`), `uq_extractions_story_version` on
      `(user_story_id, version_number)`; `tasks.extraction_id` (`UUID NOT NULL`) →
      `fk_tasks_extraction_id_extractions` (`ON DELETE CASCADE`) → `ix_tasks_extraction_id`;
      `task_invalidations` with its three FKs, two `CHECK`s and `uq_task_invalidations_active_task`
      (`postgresql_where=revoked_at IS NULL`) → `ix_task_invalidations_task_id`. All names written
      expanded inside `op.f(...)`. `downgrade()` reverses exactly that list in reverse and does **not**
      re-run the guard.
- [x] 1.5 GREEN — `backend/src/storico/infrastructure/database/models/extraction.py`:
      `version_number`, `provider`, `temperature`, `prompt_rendered`,
      `UniqueConstraint("user_story_id", "version_number", name="uq_extractions_story_version")`, the
      positive-version `CHECK`.
- [x] 1.6 GREEN — `backend/src/storico/infrastructure/database/models/task.py`: `extraction_id`
      (`Uuid`, `ForeignKey("extractions.id", ondelete="CASCADE")`, `nullable=False`) and
      `Index("ix_tasks_extraction_id", "extraction_id")`.
- [x] 1.7 GREEN — `backend/src/storico/infrastructure/database/models/task_invalidation.py` (new):
      `task_id` (FK → `tasks.id`, `ON DELETE CASCADE`), `reason` (`String(500)`, `nullable=False`),
      `marked_by`/`revoked_by` (`Uuid`, FK → `users.id`, `ON DELETE SET NULL`), `marked_at`
      (`DateTime(timezone=True)`, not null), `revoked_at` (nullable), and
      `CheckConstraint("length(trim(reason)) > 0", name="ck_task_invalidations_reason_not_blank")`,
      `CheckConstraint("(revoked_by IS NULL) = (revoked_at IS NULL)", name="ck_task_invalidations_revoke_pair")`,
      `Index("ix_task_invalidations_task_id", "task_id")`, and
      `Index("uq_task_invalidations_active_task", "task_id", unique=True, postgresql_where=..., sqlite_where=...)`.
- [x] 1.8 GREEN — `backend/src/storico/infrastructure/database/models/__init__.py`: import and
      `__all__`-register `TaskInvalidationModel` (the drift gate compares models ↔ migrated schema).
- [x] 1.9 GREEN — `backend/src/storico/domain/entities/extraction.py`: `provider: str` and
      `temperature: float` required (after `raw_response`), then
      `version_number: int | None = None`, `prompt_rendered: str | None = None`.
- [x] 1.10 GREEN — `backend/src/storico/domain/entities/task.py`: `extraction_id: UUID | None = None`.
- [x] 1.11 GREEN — `backend/src/storico/domain/entities/exceptions.py`:
      `VersionAllocationConflictError(RepositoryError)`.
- [x] 1.12 GREEN — `backend/src/storico/domain/ports/extraction_repository.py`: add
      `create_next_version(extraction) -> Extraction`,
      `record_rendered_prompt(extraction_id, *, prompt_rendered, prompt_config) -> None`,
      `mark_completed(extraction_id, *, raw_response, confidence_score, completed_at) -> None`,
      `mark_failed(extraction_id, *, error_info, completed_at) -> None`,
      `find_current_version(user_story_id) -> Extraction | None`; remove `delete()`. **Keep `save()`
      in this unit** — its callers in the route, the runner and `extract_and_persist` are rewired in
      Phases 2–3, and removing it here would leave no green boundary (design's File Changes table
      bundles the removal into WU1; no green-suite boundary can honor that — resolved in 3.7).
- [x] 1.13 GREEN — `backend/src/storico/infrastructure/database/repositories/extraction_repository.py`:
      `create_next_version` as one `insert(...).values(version_number=select(coalesce(max(...), 0) + 1)
      .where(user_story_id = :id).scalar_subquery()).returning(version_number)` inside a bounded
      `MAX_ALLOCATION_ATTEMPTS = 3` loop with `rollback()`, conflict discrimination **before** the
      `SQLAlchemyError` → `RepositoryError` wrap, and `VersionAllocationConflictError` after the bound;
      `record_rendered_prompt`, `mark_completed`, `mark_failed` as single `UPDATE`s that name no
      snapshot column and raise `EntityNotFound` on no match; `find_current_version`
      (`ORDER BY version_number DESC` + `status = 'completed'` + `LIMIT 1`); `_to_orm_kwargs` omits
      `version_number`; `_to_domain` reads the four new fields; `save()` unchanged; `delete()` removed.
- [x] 1.14 GREEN — `backend/src/storico/infrastructure/database/repositories/task_repository.py`:
      carry `extraction_id` through `_to_orm_kwargs` and `_to_domain`.
- [x] 1.15 GREEN — `backend/src/storico/infrastructure/tasks/extraction_task.py`: the three terminal
      `Extraction(...)` rebuild sites (the `_mark_extraction_failed` path and both terminal writes) and
      the recovery sweep stop dropping the new fields, so the entity's required `provider`/`temperature`
      do not raise and the terminal writes carry the snapshot. The `mark_completed`/`mark_failed` swap
      itself belongs to Phase 3.
- [x] 1.16 GREEN — `backend/tests/_helpers.py`: extraction and task builders that go through
      `create_next_version` (and default `provider`/`temperature`), so the seed rewiring below is
      mechanical. Then rewire the ten named seed files —
      `tests/test_repositories/test_extraction_repo.py`, `tests/test_repositories/test_list_by_workspaces.py`,
      `tests/test_repositories/test_task_repo.py`, `tests/test_api/test_extractions.py`,
      `tests/test_api/test_extraction.py`, `tests/test_api/test_export.py`,
      `tests/test_api/test_tasks.py`, `tests/test_api/test_unfiltered_list_queries.py`,
      `tests/test_unit/test_extraction_failure_paths.py`,
      `tests/integration/test_state_machine_scenarios.py` — off `save()`/untargeted `Task(...)`.
- [x] 1.17 GREEN — `backend/tests/test_api/test_tasks.py`: the two manual-creation tests that assert
      201 today (`:42`, `:67`) change to pin the refusal: `POST /api/v1/tasks/` can no longer satisfy
      `extraction_id NOT NULL` and answers 500 `REPOSITORY_ERROR` through `repository_error_handler`.
      Accepted for (a) because (a) is not deployed; slice (b) retires the route.
- [x] 1.18 TRIANGULATE — `backend/tests/test_integration/test_extraction_versioning_schema.py` (new),
      `@pytest.mark.integration` + the `_docker_reachable()` skipif per test: raw duplicate
      `(user_story_id, version_number)` insert is refused by `uq_extractions_story_version`;
      `tasks.extraction_id` refuses null; `information_schema.columns` / `pg_trigger` / `pg_matviews`
      show no `is_current`, no trigger and no view on `extractions`; deleting the story removes its
      extractions and their tasks (the D15 cascade) and nothing else; `upgrade` to `0027`, insert a row,
      then `upgrade head` refuses and leaves the pre-`0028` schema untouched; `downgrade 0027`
      round-trips on the empty container. **Requires a Docker daemon; on a daemon-less sandbox every
      case here skips and stays unverified.**
- [x] 1.19 TRIANGULATE — `backend/tests/test_integration/test_extraction_versioning_schema.py`: the real
      collision outcome, provoked deterministically (an uncommitted competing insert blocks the
      allocation; committing it fails the first attempt and the retry mints the next number) — the only
      deterministic provocation, since the race window lives inside one server-side statement.
      Postgres-only: **unverified without Docker**, and never asserted as "three real collisions".
- [x] 1.20 REFACTOR — remove `ExtractionRepository.delete`'s single test from
      `backend/tests/test_repositories/test_extraction_repo.py`; confirm nothing in
      `backend/src/storico` calls `save`-as-delete or `extraction_repo.delete`. Run
      `cd backend && conda run -n storico python -m pytest`.

## Phase 2: WU2 — Birth Through Allocation

Runner for this phase: `cd backend && conda run -n storico python -m pytest tests/test_api/test_extraction.py -m "not integration"`.

- [x] 2.1 RED — `backend/tests/test_api/test_extraction.py`: after `POST /workspaces/{id}/extract/`, the
      pending row carries `version_number == 1`, `provider` from the workspace config, and
      `temperature == 0.1` when the request omits it and the explicit value when it does not; the
      `LLMConfig` the adapter received carries the same temperature as the column; `prompt_config` no
      longer contains a `temperature` key; two POSTs on one story mint 1 then 2. Verify RED.
- [x] 2.2 GREEN — `backend/src/storico/domain/ports/llm_port.py`: `DEFAULT_TEMPERATURE: float = 0.1`
      beside `LLMConfig`, and `LLMConfig.temperature` defaults to that constant (one literal).
- [x] 2.3 GREEN — `backend/src/storico/api/routes/extraction.py`: resolve
      `body.temperature if body.temperature is not None else DEFAULT_TEMPERATURE` once; build the
      pending `Extraction` with `provider=provider`, `temperature=resolved`,
      `prompt_config={"validate": body.run_validation}`; create it with
      `await extraction_repo.create_next_version(pending)` instead of `save(...)`; pass
      `temperature=resolved` to `run_background_extraction`.
- [x] 2.4 GREEN — `backend/src/storico/infrastructure/tasks/extraction_task.py`: `temperature: float`
      (no `None`, no `if/else`) on `_run_extraction`, `LLMConfig(temperature=temperature)`
      unconditional, and the public wrapper's default is `DEFAULT_TEMPERATURE`.
- [x] 2.5 TRIANGULATE — `backend/tests/test_api/test_extraction.py`: the three call sites that omit
      `temperature=` still run at the default; two POSTs on one story produce two rows and the second
      is the current version only once completed; and an exhausted allocation is **not silent** — pin
      that `VersionAllocationConflictError` reaches the generic `repository_error_handler` as 500
      `REPOSITORY_ERROR` today, recording that slice (b) owns the final status code.
- [x] 2.6 REFACTOR — rerun `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.

## Phase 3: WU3 — Render-Time Snapshot and Terminal Marks

Runner for this phase:
`cd backend && conda run -n storico python -m pytest tests/test_unit/test_extraction_failure_paths.py tests/test_services/test_extraction_service.py -m "not integration"`.
Optional split axis if the delivery decision asks for one: 3.1–3.5 as 3a (with `extract()` kept as a
thin wrapper over `render()`/`generate()` so the suite stays green), 3.6–3.8 as 3b (marks, `save()`
removal, dead-path deletion).

**The split needs one clause the axis note does not mention, found while planning 3a.**
`_to_orm_kwargs` writes `prompt_rendered` (`extraction_repository.py:335`), and the in-run terminal
rebuilds in the runner construct `Extraction(... prompt_rendered=pending.prompt_rendered ...)` from a
row read **before** the render. So the moment 3a writes the prompt at render time, the next `save()`
re-nulls it and 3.1's survival case fails: 3a could not close green on the axis as written. 3a
therefore threads the freshly rendered text into those in-run rebuilds (`prompt_rendered=rendered.text`)
— the same value `record_rendered_prompt` just wrote, so it cannot diverge from the row — and 3b deletes
the whole rebuild when it swaps in `mark_completed`/`mark_failed`. `_mark_extraction_failed` re-reads
its row and already preserves the column; it is left alone.
This is not 3b arriving early: the mark swap, the `save()` removal, the `extract_and_persist()` deletion
and the nine re-pointed cases all stay in 3b.

- [x] 3.1 RED — `backend/tests/test_unit/test_extraction_failure_paths.py`: render succeeds, `generate`
      raises `LLMError` → `version_number`, `provider`, `temperature`, `prompt_rendered` and
      `prompt_config.system_prompt` are all populated, `raw_response == ""`, no `confidence_score`, no
      `usage`; a run that dies before render keeps `prompt_rendered IS NULL` and it stays null through
      any later terminal write; and the regression test — after a failed run and after a completed run
      every snapshot column still holds its birth/render value. RED today because the terminal rebuilds
      null the columns.
- [x] 3.2 RED — `backend/tests/test_api/test_extraction.py`: the retry path leaves exactly one
      extraction row and one number; every task row the completed run writes carries its
      `extraction_id`; a v2 run on the same story produces new task rows while v1's remain (disjoint
      sets).
- [x] 3.3 RED — `backend/tests/test_services/test_extraction_service.py`: re-point the nine
      `extract_and_persist` cases at the live path (`run_background_extraction` with the engine and
      adapters monkeypatched, the pattern `tests/test_api/test_extraction.py` already uses): "persists
      an extraction" becomes "the row the runner completes carries these outputs"; the judge and
      vector-store cases assert on the row and on the recording fake. These must fail before the
      rewrite.
- [x] 3.4 GREEN — `backend/src/storico/domain/services/extraction_service.py`: add the frozen, slotted
      `RenderedPrompt(instruction, system_prompt, template_variables)` with
      `text = system_prompt + "\n\n" + instruction`; replace `extract()` with `render(...) ->
      RenderedPrompt` and `generate(rendered, config) -> tuple[list[ParsedTask], str]`; drop the
      repository constructor parameters; delete `extract_and_persist()`.
      **3a note (2026-09-29):** half landed — `RenderedPrompt` + `render()`/`generate()` with
      `extract()` kept as the temporary wrapper. The repository-parameter removal and the
      `extract_and_persist()` deletion stay in 3b, so 3.4 remains open.
      **3b-ii-a note (2026-09-29):** closed. `extract_and_persist()`, the orphaned service-level `_store_rag`,
      the temporary `extract()` wrapper and the two repository constructor parameters are gone; `judge_service`
      stays because the runner reaches into `_judge_service` directly.
- [x] 3.5 GREEN — `backend/src/storico/infrastructure/tasks/extraction_task.py`: in order,
      `render()` → `record_rendered_prompt(extraction_id, prompt_rendered=rendered.text,
      prompt_config={"validate": ..., "system_prompt": system_prompt})` → `generate()`; replace the
      terminal writes with `mark_completed(...)` / `mark_failed(...)` and delete `_get_created_at`;
      build every `Task` with `extraction_id=extraction_id`.
      **3a note (2026-09-29):** half landed — render -> record -> generate, and the completed
      rebuild threads `rendered.text` instead of reading `prompt_rendered` off a row fetched
      before the render. The `mark_completed`/`mark_failed` swap and the `_get_created_at`
      deletion stay in 3b, so 3.5 remains open.
      **3b-i note (2026-09-29):** closed. The four terminal paths call `mark_completed`/`mark_failed`
      (commit `3364c43`), 3a's `rendered.text` threading is dead and removed, and `_get_created_at`
      needed no deletion because `1a90aff` already removed it.
- [x] 3.6 GREEN — construction and comment sites of the removed methods:
      `backend/tests/test_extraction_flow_few_shot.py` and
      `backend/tests/test_integration/test_few_shot_rag_qdrant.py` (rewrite the stale comment that
      claims `extract` never touches repositories), plus any remaining `extract_and_persist` reference.
- [x] 3.7 GREEN — `backend/src/storico/domain/ports/extraction_repository.py` and
      `backend/src/storico/infrastructure/database/repositories/extraction_repository.py`: remove
      `save()` now that no caller remains (the route moved in Phase 2, the runner and the dead path in
      this phase), so the port has no whole-row writer. Also pin in
      `backend/tests/test_repositories/test_extraction_repo.py` that the port exposes no `delete`.
      **3b-ii-b note (2026-09-29):** closed. No whole-row writer remains; the port surface is pinned
      by exact method set, and the deletion reached one spy helper outside the granted three.
- [x] 3.8 TRIANGULATE — `backend/tests/test_api/test_extraction.py`: run one story twice; v1's task
      rows are byte-for-byte untouched, v2's tasks are new rows, `find_current_version` is v2, and the
      story-level read (`user_story_id`) still returns both sets.
- [x] 3.9 REFACTOR — rerun
      `cd backend && conda run -n storico python -m pytest tests/test_unit/test_extraction_failure_paths.py tests/test_services/test_extraction_service.py -m "not integration"`
      then the whole suite `cd backend && conda run -n storico python -m pytest`.

### Discovered defect D-a-1 — re-dispatching a run duplicates its task rows (found by 3.2, not fixed here)

A second `run_background_extraction` call for the **same** `extraction_id` re-runs the pipeline and
appends a second set of `tasks` rows: the persist loop (`extraction_task.py:441`) is INSERT-only and
carries no guard on `extraction_id`. Probed at 3b-iii — re-dispatching a 2-task run yields 3 rows for
the story, while extraction rows stay at 1 and `version_number` stays at `[1]`.

**Latent, not live.** Every production path either mints a new version (POST) or marks failed without
re-running (`recover_stuck_extractions` → `mark_failed`, `extraction_task.py:193`). Nothing re-dispatches
today, so no user-visible defect exists. This is also why the 3.2 case pins "one extraction row, one
number" — the invariant the spec states — and not "exactly one set of task rows", which the code does
not guarantee.

Deliberately **not** fixed in slice (a): the fix is either an idempotent persist or a rejection of a
non-pending `extraction_id`, and both change behaviour the (b) slice's endpoints will depend on.
Routed to slice (b) as a named requirement rather than absorbed silently here.

## Phase 4: WU4 — Invalidation Storage Invariants

Runner for this phase: `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_task_invalidation.py -m "not integration"`.
The table and model land in Phase 1 because the drift gate needs table **and** model in one step;
this unit owns the invariants, not the DDL.

- [x] 4.1 RED — `backend/tests/test_repositories/test_task_invalidation.py`: add the invariant cases —
      an empty and a space-only `reason` are refused by `ck_task_invalidations_reason_not_blank`; a
      bounded non-empty reason round-trips verbatim; a second active mark for one task is refused; a
      revoke then re-mark succeeds and the first row still records its marking and its revocation;
      revoking sets `revoked_by`/`revoked_at` on the same row and leaves `reason`, `marked_by`,
      `marked_at` unchanged; a mark resolves to extraction v2 only through its task's `extraction_id`;
      a v2 task with the same title as a marked v1 task carries no mark.
- [x] 4.2 GREEN/TRIANGULATE — make the SQLite layer actually guard the invariants: delete each model
      `CHECK` and the `sqlite_where` in turn, confirm the corresponding 4.1 case **fails**, then restore
      it. This is the unit's RED evidence: on a green Phase-1 tree some of these cases pass because the
      model already declares the constraint, and a mutation check is what proves the test guards the
      invariant instead of passing vacuously. Pin that `tasks` still exposes no invalidation columns.
      **WU4a note (2026-09-29):** mutation matrix run and independently spot-checked by the parent: removing
      `sqlite_where` alone makes exactly the revoke-then-re-mark case fail (`UNIQUE constraint failed:
      task_invalidations.task_id`), the other 11 pass. No gap found on the SQLite half, so 4.4's
      refinement condition did not trigger there; it remains live for 4.3's Postgres half.
- [x] 4.3 TRIANGULATE — `backend/tests/test_integration/test_extraction_versioning_schema.py`:
      Postgres-only half — `uq_task_invalidations_active_task` exists as a **partial** index (not a
      full unique index on `task_id`); a revoked row survives while a re-mark succeeds; deleting the
      task cascades the mark away; deleting the marking user nulls `marked_by` only and keeps
      `reason`/`marked_at`; deleting the revoking user keeps `revoked_at`. **Requires a Docker daemon;
      skipped and unverified otherwise.**
- [ ] 4.4 GREEN — `backend/src/storico/infrastructure/database/models/task_invalidation.py`: refine only
      if 4.2 or 4.3 exposed a gap (a missing `sqlite_where`, a wrong FK action, a non-portable `CHECK`
      expression), then rerun 4.1–4.3.
- [x] 4.5 REFACTOR — rerun the phase runner plus
      `cd backend && conda run -n storico python -m pytest tests/test_repositories -m "not integration"`.

### Discovered defect D-a-2 — `ck_task_invalidations_revoke_pair` contradicts `revoked ON DELETE SET NULL`

Found while writing 4.3, from reading `0028`'s DDL rather than from running it. The table declares
`fk_task_invalidations_revoked_by_users ... ON DELETE SET NULL` (0028:104-109) **and** the equivalence
CHECK `(revoked_by IS NULL) = (revoked_at IS NULL)` (0028:114-117). Postgres evaluates CHECK constraints
during the referential action, so deleting a user who revoked a mark sets `revoked_by = NULL` while
`revoked_at` stands — violating the CHECK, and the deletion fails instead of completing. `marked_by`
has the same FK action but no paired CHECK (`marked_at` is `NOT NULL`), so only the revoke pair
collides.

**This cannot be settled on this machine, and the reason is structural:** `PRAGMA foreign_keys` is OFF
by default in SQLite and nothing in the repo ever turns it on — verified by grepping `tests/` and
`src/` (no occurrence) and by printing the pragma from a fresh aiosqlite connection (`0`). So **no FK
action of any kind fires in the unit layer**: the conflict is Postgres-only, and so is every
`ON DELETE CASCADE` / `SET NULL` claim in 1.18 and 4.3. Consequence for reading this change's
evidence: the unit layer proves `NOT NULL`, `CHECK`, `UNIQUE` and partial-index shape, and proves
*nothing* about referential actions.

Case 4.3-6 asserts the DDL reading (refusal) with both outcomes documented in its docstring, so CI
adjudicates rather than encodes a guess. The fix is a product decision, not a mechanical one: keep the
CHECK and make the revoker FK `RESTRICT` (deleting a revoking user fails loudly, audit stays whole),
or drop the CHECK's second arm and accept an anonymous surviving revocation. `0028` is unreleased —
this branch is its first deployment — so whichever way goes, it is an edit to `0028` and not a new
migration. **Not taken here: it needs the owner's call.**

## Phase 5: Slice Verification

- [ ] 5.1 Whole suite (the acceptance gate): `cd backend && conda run -n storico python -m pytest`.
- [ ] 5.2 Integration layer: `cd backend && conda run -n storico python -m pytest -m integration`.
      Requires a Docker daemon. If it is absent, every case skips and the Postgres-only invariants
      listed under "Verification environment" remain unverified — record that outcome instead of
      reporting green.
- [ ] 5.3 Migration chain acceptance: `cd backend && conda run -n storico python -m pytest tests/test_integration/test_migration_chain.py -m integration`
      — the chain reaches head on the empty container and `_KNOWN_DRIFT` is still an empty frozenset
      (Docker).
- [ ] 5.4 No-delete and no-flag sweep: confirm `ExtractionRepository.delete`,
      `SQLAlchemyExtractionRepository.delete`, `extract_and_persist` and `ExtractionRepository.save`
      no longer exist, that no service/route/background task removes an `extractions` or `tasks` row
      inside a version, and that no `is_current` column, trigger or materialized view is declared
      anywhere.
- [ ] 5.5 Repo-documented lint/format (AGENTS.md §0): `conda run -n storico python -m ruff check src tests`
      and `conda run -n storico python -m ruff format --check src tests`, run from `backend/`.
- [ ] 5.6 Record in the verify report the honest split of evidence: what the SQLite unit layer proved,
      what ran against Postgres, and what skipped without a Docker daemon.

## Slice Boundary

- **(a) is the root slice.** Slices **(b)** `extraction-versioning-api` and **(c)**
  `extraction-versioning-prompt` depend on this schema and on `explore.md` as the shared evidence
  base; neither can start before `0028` lands.
- **(a) is a reviewable unit but not independently deployable.** Board, export and `GET /tasks` still
  read tasks by `user_story_id` until (b) applies the `find_current_version` filter, so a second run
  on a story would show both versions' task sets. (a) and (b) ship in one release; do not deploy (a)
  alone. The manual `POST /api/v1/tasks/` route is likewise left untouched for (b) to retire.
- **The D11 data wipe is not a task in this file.** Wiping the relational data and the two Qdrant
  collections (`storico_extractions_dev`, `storico_extractions_prod`) is a separate destructive
  operation with its own confirmation and record, executed **before** the deploy that carries `0028`.
  It is not an Alembic step, it is not reversible, and the production E2E evidence it removes does not
  come back.
- **Out of this slice**: the marks endpoints and permission gate, the `410 Gone` for
  `DELETE /tasks/{id}`, the current-version HTTP filter, the version selector and the editor → (b);
  snapshot content, context ports, Qdrant payload keys and token `usage` → (c). The domain entity and
  repository port for the mark are (b)'s: this slice stores the mark, it does not expose it.
- **Two of (a)'s own tasks are later amended by (c); do not treat (a)'s shape as final.**
  Task 3.4's `generate()` returns a two-tuple, and **(c) WU2 task 2.8** changes it to return
  `ExtractionResult` so the provider's `usage` can travel out of the adapter. Task 2.3 passes only
  `temperature` into `run_background_extraction`, and **(c) WU3 task 3.5** threads `version_number`
  through it for the Qdrant payload. Neither edit is a defect in (a): (a) cannot know a number the
  provider has not returned yet, and the payload key is (c)'s contract. They are recorded here so the
  (a) reviewer is not surprised by a later change to the same lines.
