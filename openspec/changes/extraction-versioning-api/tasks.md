# Tasks: Extraction Versioning — HTTP Contract, Permission Gate and UI

Slice (b) of three for Storico 0.9.0. Planning artifact only: every line below is unchecked and no
line claims a check that has not run. Evidence base: `explore.md` (this change), the shared ledger
`../archive/2026-09-30-extraction-versioning-schema/explore.md` (`main` `ecea3e2`), the seven `specs/` deltas (25
requirements), the 14 design decisions, slice (a)'s `tasks.md`, and `openspec/config.yaml`
(`strict_tdd: true`, `rules.tasks.protect_review_workload: true`).

Runners: backend `cd backend && conda run -n storico python -m pytest` (unit `-m "not integration"`,
integration `-m integration`); frontend `cd frontend && pnpm test` (vitest). `python -m` is required
because the conda env exposes no bare console scripts (`AGENTS.md` §0); the `commands.integration`
line in `openspec/config.yaml` omits `python -m` and is the stale one. Frontend E2E is not runnable
(`@playwright/test` is not a devDependency), so every UI scenario below is a component test.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ≈4,400–5,700 for the whole slice (`additions + deletions`) |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | WU1 (410s) → WU2 (field matrix + client; atomic, over budget) → WU3 (reads) → WU4 (gate + story deletion; largest, over budget) → WU5 (marks backend) → WU6 (UI + i18n) → verification |
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

```text
Delivery strategy: ask-on-risk — RESOLVED
Chain strategy: chained PRs, one PR per work unit, with the splittable units cut on their named axis
size:exception: accepted for WU2 and WU4 of this slice, and for no other unit
```

- **WU2 (≈420–520) and WU4 (≈1,300–1,700) ship as single PRs over the 400-line budget** under the
  accepted exception, because neither has a green intermediate commit (WU2: `extra="forbid"` turns a
  split into one red half; WU4: migration `0029`, the model, the repository method and the cleanup
  ordering prove each other only together). The exception is a reviewer warning, not a waiver: WU2
  must be read as one cross-stack contract change, and WU4 as a storage change with a destructive
  half.
- **WU3, WU5 and WU6 do NOT carry the exception.** They are chained into two PRs each on the split
  axis already named in this file — WU3: current-version predicate + `extraction_id` read + export,
  then the selector read + response scalars; WU5: entity/port/repository + validator + invariants,
  then the endpoints + D16 read; WU6: `workspace-role.ts` + `versioning-api.ts` + types + selector,
  then the editor recut + confirmations + D16 notice + i18n. Each half must be independently green
  before the next starts; if a half still crosses 400 in practice, that is reported and decided, not
  absorbed by this exception.
- **WU1 (≈260–340) fits the budget** and ships whole.
- Chain order stays as the Per-Work-Unit Estimate table defines it: each unit starts from the previous
  unit's green head, and this slice starts from slice (a)'s green head.

### Per-Work-Unit Estimate

These are `additions + deletions`, built from the design's File Changes table plus the test lines each
pinned scenario forces, and from the constant churn the seven new error codes cause in
`frontend/src/lib/__tests__/error-codes.test.ts` (36 → 43) and in `frontend/src/i18n/{en,es}.json`
(41 → 48 keys), which must move in the same unit that adds each registry entry or the mirror test
leaves the suite red.

| Unit | Design unit | Commit | Estimated changed lines | Fits 400-line budget? |
|------|-------------|--------|-------------------------|------------------------|
| WU1 — the two `410` retirements | WU1 (second half) | `refactor(api): retire manual task creation and single-task deletion with 410 Gone` | ≈260–340 | Yes |
| WU2 — field matrix + client stop-sending | WU1 (first half) | `feat(tasks): enforce the D5/D21 field matrix and stop the editor sending removed fields` | ≈420–520 | **No — atomic cross-stack** |
| WU3 — current-version reads + selector read + response scalars | WU2 | `feat(api): read only the current version and expose the version selector` | ≈600–750 | **No** |
| WU4 — gate + story deletion + `0029` + vector cleanup | WU3 | `feat(api): gate version mutations to the owner or an admin and delete a story with its record and cleanup` | ≈1,300–1,700 | **No — the storage half has no greener boundary** |
| WU5 — marks backend + D16 read | WU4 (backend) | `feat(api): expose the invalidation mark and the repetition read` | ≈800–1,050 | **No** |
| WU6 — selector UI, mark controls, confirmations, i18n | WU4 (frontend) | `feat(frontend): wire the version selector, the mark controls and the confirmations into the editor` | ≈1,000–1,400 | **No** |
| **Slice total** | | | **≈4,400–5,700** | **No** |

### Two budget breaches, one of them atomic

- **WU2 is atomic and over budget.** The `UpdateTaskRequest` shrink and `lib/tasks-api.ts` +
  `TaskEditor.tsx` stopping the removed fields must land in one commit: `extra="forbid"` is already
  in force, so the moment the schema drops `title`/`description`/`priority` an un-updated editor
  422s on every save (proposal *Risks* row 1, design *Threat Matrix* row 1). No split along the
  backend/frontend stack produces two green halves — only a red one.
- **WU4's storage half is over budget.** Splitting off the gate (`api/dependencies.py` + its truth
  table, ≈350–450) does not bring the deletion half under budget: migration `0029`, the model, the
  entity, the port, `delete_with_record`, the vector port/adapter, `StoryDeletionService` and the
  route plus its tests have no green intermediate — the migration and model must exist before the
  repository method, and the route's tests are what prove cleanup-before-delete. WU4 as listed is
  the honest boundary; the split axis above is the only one, and it leaves a ≈900–1,200-line half.
- WU3, WU5 and WU6 breach but each has a genuine single-stack split axis (WU3: repository predicate
  + `extraction_id` read + export vs. selector read + scalars; WU5: entity/port/repository +
  validator + invariants vs. endpoints + D16; WU6: `workspace-role.ts` + `versioning-api.ts` + types
  + selector vs. editor recut + confirmations + D16 notice + i18n). One honest slicing pass was made
  here; none of them can be brought under 400 without either breaking the atomic pairs named above
  or separating copy from the component that renders it, which the design forbids.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test | Runtime harness | Rollback boundary |
|------|------|-----------|--------------|-----------------|-------------------|
| 1 | Retire `POST /api/v1/tasks/` and `DELETE /api/v1/tasks/{task_id}` with `410 Gone`; delete `CreateTaskRequest`; the two new codes and their copy | PR 1 | `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"` and `cd frontend && pnpm test src/lib/__tests__/error-codes.test.ts` | SQLite in-memory; FastAPI `TestClient`; vitest | Restore both handlers and `CreateTaskRequest`; revert the two codes and the mirror counts |
| 2 | The D5/D21 field matrix on `PUT /api/v1/tasks/{task_id}`; the editor and `lib/tasks-api.ts` stop sending the removed fields | PR 2 (over budget — needs the delivery decision) | `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"` and `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx src/lib/__tests__/tasks-api.test.ts` | SQLite in-memory; vitest with mocked `fetch` | Restore the three fields in `UpdateTaskRequest` (the frozen guard goes with them) and the editor's inputs |
| 3 | Current-version predicate on every read scope, `extraction_id` parameter and its refusal, `list_versions`, the selector endpoint, the export filter, the three response scalars | PR 3 | `cd backend && conda run -n storico python -m pytest tests/test_repositories tests/test_api/test_tasks.py tests/test_api/test_stories.py tests/test_api/test_export.py tests/test_api/test_unfiltered_list_queries.py -m "not integration"` | SQLite in-memory (`sqlite+aiosqlite://`, `backend/tests/conftest.py:36`) | Remove the predicate and `list_versions`, revert the route parameter and the scalars |
| 4 | `_is_owner_or_admin` + its three wrappers; the gate on extract, mark, unmark and story delete; `0029` + the deletion record; the vector cleanup and its ordering; the two new handlers | PR 4 | `cd backend && conda run -n storico python -m pytest tests/test_api/test_stories.py tests/test_api/test_extraction.py tests/test_unit/test_workspace_gate.py -m "not integration"` | SQLite in-memory; the cascade and the record's survival need Postgres (Docker) | `alembic downgrade 0028`, then revert the dependencies module, the routes and the vector port method |
| 5 | The mark entity/port/repository, the reason validator, the four endpoints, the normalizer and the D16 read | PR 5 | `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py tests/test_repositories/test_task_invalidation.py tests/test_unit/test_invalidation_request.py tests/test_unit/test_task_title_normalizer.py -m "not integration"` | SQLite in-memory | Delete the endpoints, the new modules and the `TASK_ALREADY_MARKED` entry; `task_invalidations` itself reverts with `0028` |
| 6 | `VersionSelector.tsx`, the recut `TaskEditor`, both confirmations, the D16 notice, the failed-version state, the delete dialog's version count, the client helpers, stores, types and all copy | PR 6 | `cd frontend && pnpm test` | vitest + `@testing-library/react` with mocked `fetch` | Remove `VersionSelector.tsx`, `versioning-api.ts`, `workspace-role.ts`, restore the editor and dialogs, revert the i18n keys — but not the corrected `landing.faq.a4` (proposal *Rollback Plan*) |

### What is consumed from slice (a) — and what is not re-scheduled

Every mechanism below is (a)'s; this slice reads it and never rebuilds it. No task here re-schedules
an (a) task.

| (b) task | Consumes | (a) owner |
|-----------|----------|-----------|
| 2.3, 3.2, 4.2 | `find_current_version(user_story_id)` on the extraction port | (a) 1.12, 1.13 |
| 2.3, 3.1, 3.4 | `tasks.extraction_id` column, model field and `Task.extraction_id` | (a) 1.6, 1.10, 1.14 |
| 3.2, 3.4, 3.8, 4.13 | `Extraction.version_number` / `provider` / `temperature` | (a) 1.5, 1.9 |
| 4.2, 4.7 | `VersionAllocationConflictError` | (a) 1.11 |
| 5.3–5.9 | `task_invalidations` table, its DB invariants and `TaskInvalidationModel` | (a) 1.7, 1.8, 4.1–4.5 |
| 4.17 | `0028` chain head and the models ↔ migrated-schema drift gate | (a) 1.3, 1.8, 5.3 |
| 1.1, 1.2 | the two `POST /api/v1/tasks/` tests (a) rewrote to pin the 500 | (a) 1.17 |
| 5.3 | `backend/tests/test_repositories/test_task_invalidation.py` exists as the invariants' home | (a) 1.2, 4.1 |

**Not tasks here** because (a) owns them: migration `0028` and the schema; the version-number
allocation and its bounded retry; `find_current_version` itself; the render/generate split and the
render-time snapshot write; the `task_invalidations` table and its database invariants; the removal
of `ExtractionRepository.delete` and `extract_and_persist`; and the removal of
`ExtractionRepository.save` (a 3.7). No task below calls `save` or `delete` on the extraction port,
and no task reintroduces a delete path inside a version.

**Two path corrections against the design's tables.** The design's testing table names
`test_repositories/test_story_repo.py`; the repository's test file in this repo is
`backend/tests/test_repositories/test_user_story_repo.py` (task 4.3 uses the real path). And the
design's `frontend/src/lib/error-codes.ts` needs no code change — it is a generic code→copy map; only
the two locale files and the mirror test move.

**Two new paths the design names but that (a) does not create**, verified free at planning time and
created here: `backend/tests/test_unit/test_workspace_gate.py`,
`backend/tests/test_unit/test_invalidation_request.py`,
`backend/tests/test_unit/test_task_title_normalizer.py`,
`backend/tests/test_integration/test_story_deletion_record.py`.

## Spec Coverage

All 25 `### Requirement:` headings across the seven deltas map to at least one task.

| Requirement (delta) | Covered by |
|--------------------|------------|
| R1 Task Reads Return the Current Version Only (`extraction-versioning`) | 3.1, 3.3, 3.4, 3.6, 3.10 |
| R2 The Story's Versions Are Readable Through One Selector Endpoint | 3.2, 3.5, 3.8, 3.9, 3.10 |
| R3 A Failed Version Is Surfaced Honestly | 3.8, 3.9, 3.10, 6.3, 6.5, 6.8 |
| R4 Task Creation and Single-Task Deletion Are Retired with 410 Gone | 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 1.8 |
| R5 The Task Write Contract Enforces the Field Matrix | 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11 |
| R6 An Exhausted Version Allocation Surfaces as an Explicit Conflict | 4.2, 4.7, 4.18, 6.4 |
| R7 Story Deletion Is the Only Sanctioned Deletion of Versions | 4.3, 4.5, 4.8, 4.9, 4.10, 4.11, 4.12, 4.13, 4.15, 4.16, 4.17, 6.3, 6.5, 6.9 |
| R8 Creating a Mark Requires a Reason, the Current Version and the Gate (`task-invalidation`) | 5.1, 5.4, 5.5, 5.6, 5.8, 5.9, 5.11, 5.12, 6.4, 6.6 |
| R9 The Mark Record Is Readable With Its Full History | 5.3, 5.4, 5.6, 5.8, 5.9 |
| R10 Revoking Updates the Row and Never Deletes It | 5.3, 5.4, 5.6, 5.9, 6.4, 6.6 |
| R11 The Repetition Read Warns on an Exact Normalized-Title Match | 5.2, 5.3, 5.7, 5.9, 5.11, 6.3, 6.4, 6.6, 6.8 |
| R12 The Gate Is the Owner-or-Admin Rule, Expressed as New Code (`workspace-permissions`) | 4.1, 4.2, 4.5, 4.15 |
| R13 The Four Version-Mutating Operations Require the Gate | 4.2, 4.6, 4.13, 4.15, 4.18 |
| R14 The Member-Accessible Surface Is Stated and Protected | 2.9, 4.2, 4.15, 6.7 |
| R15 Task Editor Component (`task-editor`) | 2.6, 2.7, 2.9, 6.4, 6.6 |
| R16 Task Editor Trigger | 6.3, 6.5, 6.8, 6.9 |
| R17 Task Editor Persistence | 2.6, 2.7, 2.9, 6.4, 6.6 |
| R18 Labels and Dependencies Validation | 2.6, 2.9, 6.4, 6.6 |
| R19 Marking and Unmarking Ask for Confirmation | 6.4, 6.6, 6.9 |
| R20 The Editor Warns on a Repetition of a Marked Title | 5.11, 6.4, 6.6, 6.8 |
| R21 Workspace-Scoped Extraction Client (`extraction-workflow`) | 4.6, 6.3, 6.5, 6.8 |
| R22 Extraction Error Surfacing | 4.2, 4.7, 6.4, 6.6 |
| R23 Kanban Task Fetching (`kanban-board`) | 3.4, 3.6, 3.10, 6.7 |
| R24 Kanban Drag-and-Drop Status Update | 2.1, 2.5, 2.9, 6.7 |
| R25 Backend Export Endpoint (`export-download`) | 3.7, 3.11 |

---

## Defects carried in from slice (a) — named before they are tasked

Slice (a) closed with two defects it found by reading its own shipped schema. Both were declared
"carried into (b) as a named requirement", and neither appeared anywhere in this change's artifacts
until now. Lines verified against `main` at `1c3f59b`, not from memory.

**D-a-1 — re-dispatching a run duplicates its task rows.**
`backend/src/storico/infrastructure/tasks/extraction_task.py:441` is an INSERT-only persist loop over
`parsed_tasks` with no `extraction_id` guard, so calling `run_background_extraction` twice for the same
extraction id appends a second set of tasks against the same version. Latent today because every live
caller either mints a new version or only calls `mark_failed`
(`recover_stuck_extractions`). It becomes live the moment (b) exposes any endpoint that can re-trigger a
run. Attach to **WU3 (the reads)** only if (b) adds a retry/redo surface; otherwise keep it as an
explicit non-goal with the reasoning, and do **not** let `3b-iii`'s test be widened to assert "one set of
task rows per version" — that test pins "one row, one number", which is all the code guarantees.

**D-a-4 — account deletion answers HTTP 500 once a revoke exists.**
`DELETE /api/v1/users/me` (`backend/src/storico/api/routes/settings.py:335`) promises in its docstring
(`:343`) that all associated data is cascade-deleted, and calls
`UserRepository.delete` (`repositories/user_repository.py:74-78`), a bare `delete(UserModel)` with no
`IntegrityError` handling — unlike `save()` and `link_account()` in the same file. No `IntegrityError`
handler is registered, so the refusal raised by `fk_task_invalidations_revoked_by_users`
(`ON DELETE RESTRICT`, live in production since `0028`) falls to
`api/errors.py:161 generic_error_handler` → **500 `{"detail": "Internal server error"}`**. No test in the
repository issues that verb. Slice (a) keeps it latent only because nothing can write a
`task_invalidations` row yet; **WU5 (marks backend) is exactly when it stops being latent**, so the
mark-endpoint work must decide the contract here — a designed 409 with a reason, or a pre-check that
explains which marks block the deletion — and add the route's first DELETE-verb test.

**Scope accounting, stated instead of smuggled:** these two are **not** among the 77 unchecked tasks
below and are **not** in the ≈4,400–5,700 line forecast. D-a-4 will add at least one backend test file
case plus either a handler or a pre-check, and a frontend copy decision if the account page must explain
the refusal. Give them task IDs and forecast numbers when apply is authorized for this slice, so the
review workload estimate reflects them rather than discovering them mid-PR.

---

## Phase 1: WU1 — The Two 410 Retirements

Commit: `refactor(api): retire manual task creation and single-task deletion with 410 Gone`.
Runner: `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`,
plus `cd frontend && pnpm test src/lib/__tests__/error-codes.test.ts` for the mirror.
STRICT TDD order: RED first, then GREEN, then TRIANGULATE, then REFACTOR.

- [x] 1.1 RED — `backend/tests/test_api/test_tasks.py`: add the failing retirement cases.
      `DELETE /api/v1/tasks/{task_id}` (currently 204 and the row is deleted) must answer 410 with
      `error_code` `TASK_DELETE_ENDPOINT_REMOVED`, a `detail` naming D12, and leave the task row
      linked to its version; `POST /api/v1/tasks/` (currently the 500 slice (a) pinned) must answer
      410 with `error_code` `TASK_CREATION_ENDPOINT_REMOVED`, a `detail` naming D3, and add no row.
      Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`.
- [x] 1.2 RED — `backend/tests/test_api/test_tasks.py`: flip slice (a)'s two pinned 500 cases
      (`TestCreateTask::test_create_task` and `::test_create_task_with_labels`, rewritten by (a)
      1.17) to pin the 410; add the route-shape case that `DELETE /api/v1/tasks/{task_id}/invalidations/current`
      still resolves (neither retirement may be a `/{path:path}` catch-all) and that
      `DELETE /api/v1/tasks/` still answers 405, not 410. Same runner command as 1.1.
- [x] 1.3 GREEN — `backend/src/storico/api/routes/tasks.py`: replace the `delete_task` handler body
      with `@router.api_route("/{task_id}", methods=["DELETE"], status_code=410, include_in_schema=False)`
      that runs the unchanged `_validate_task_workspace_access` walk and then raises
      `ApiError(410, TASK_DELETE_ENDPOINT_REMOVED, detail=…)`, with no `repo.delete` call; replace
      `create_task` with `@router.api_route("/", methods=["POST"], status_code=410, include_in_schema=False)`
      that reads no body and raises `ApiError(410, TASK_CREATION_ENDPOINT_REMOVED, detail=…)`.
- [x] 1.4 GREEN — `backend/src/storico/api/schemas/task.py`: delete `CreateTaskRequest` (and any
      import it leaves unused); `backend/src/storico/api/error_codes.py`: add
      `TASK_CREATION_ENDPOINT_REMOVED` and `TASK_DELETE_ENDPOINT_REMOVED` to the alphabetically
      sorted `__all__` plus their `# ── Route raise sites` comment block.
- [x] 1.5 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`: add
      both codes to the `errorCodes` family with neutral international Spanish copy (`tú`, no voseo);
      `frontend/src/lib/__tests__/error-codes.test.ts`: move `EXPECTED_REGISTRY_COUNT` from `36` to
      `38` and both locale counts from `41` to `43`. Prove with
      `cd frontend && pnpm test src/lib/__tests__/error-codes.test.ts`.
- [x] 1.6 TRIANGULATE — `backend/tests/test_api/test_tasks.py`: the non-member edge — a caller who is
      not a member of the owning workspace gets 403 `NOT_A_WORKSPACE_MEMBER` on
      `DELETE /api/v1/tasks/{task_id}`, and an addressed task that does not exist gets 404
      `ENTITY_NOT_FOUND`, both before the 410 is reached; assert the task row count is unchanged and
      the response discloses nothing about the workspace. Prove with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`.
- [x] 1.7 REFACTOR — `backend/src/storico/api/routes/tasks.py`: confirm no import of the deleted
      request schema survives and no `repo.delete(` call remains in the file; then rerun
      `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.
- [x] 1.8 REFACTOR (frontend) — rerun
      `cd frontend && pnpm test src/lib/__tests__/error-codes.test.ts src/i18n/__tests__/neutral-spanish.test.ts src/i18n/__tests__/no-duplicate-keys.test.ts`.

## Phase 2: WU2 — The Field Matrix and the Version-Aware Client

Commit: `feat(tasks): enforce the D5/D21 field matrix and stop the editor sending removed fields`.
Runners: `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`
and `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx src/lib/__tests__/tasks-api.test.ts`.
This unit is cross-stack by construction — the schema shrink and the client must land together or
every editor save 422s — so each line names exactly one runner.

- [ ] 2.1 RED — `backend/tests/test_api/test_tasks.py`: add the failing field-matrix cases. `status`
      on a frozen version is 200 and persisted; `labels` on a frozen version is 200 and persisted;
      `dependencies` on a frozen version is 409 `TASK_VERSION_FROZEN` with the current version number
      in the `detail` and the dependencies unchanged; `dependencies` on the current version is 200
      and persisted; `title`, `description` and `priority` are 422 `REQUEST_VALIDATION_FAILED` on both
      a frozen and a current task with no field changed; a body carrying both an illegal transition
      and a `dependencies` write on a frozen version answers 409, not 400.
      Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`.
- [ ] 2.2 GREEN — `backend/src/storico/api/schemas/task.py`: `UpdateTaskRequest` shrinks to `status`,
      `labels` and `dependencies`; `title`, `description` and `priority` are deleted, not ignored, and
      `extra="forbid"` stays.
- [ ] 2.3 GREEN — `backend/src/storico/api/routes/tasks.py`: in `update_task`, after the unchanged
      membership walk, resolve `current = await extraction_repo.find_current_version(existing.user_story_id)`
      and `frozen = current is None or existing.extraction_id != current.id`; if
      `"dependencies" in body.model_fields_set and frozen` raise
      `ApiError(409, TASK_VERSION_FROZEN, detail={"current_version": current.version_number if current else None, …})`
      **before** the state-machine check; keep the state machine and the `body.dependencies is not None`
      write, and drop the `title`/`description`/`priority` kwargs. Add the `ExtractionRepoDep`
      dependency.
- [ ] 2.4 GREEN — `backend/src/storico/api/error_codes.py`: add `TASK_VERSION_FROZEN` to the sorted
      `__all__` and its comment block.
- [ ] 2.5 TRIANGULATE — `backend/tests/test_api/test_tasks.py`: the presence edge — `{"dependencies": []}`
      on a frozen version is 409 and clears nothing; `{"dependencies": null}` on a frozen version is
      409; `{"status": "review"}` with no `dependencies` key on a frozen version is 200; a story with
      no `completed` version answers 409 with "no current version" in the `detail`; a frozen version
      plus an illegal transition writes nothing. Prove with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`.
- [ ] 2.6 RED (frontend) — `frontend/src/lib/__tests__/tasks-api.test.ts` and
      `frontend/src/components/react/__tests__/TaskEditor.test.tsx`: the failing cases — `fetch`'s body
      carries `status` and `labels` and no `title`, `description` or `priority`; `title` and
      `description` render read-only; no `priority` control is rendered; a frozen task's save body
      carries no `dependencies` key. Prove RED with
      `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx src/lib/__tests__/tasks-api.test.ts`.
- [ ] 2.7 GREEN (frontend) — `frontend/src/lib/tasks-api.ts`: `updateTask` narrows its accepted fields
      to `status | labels | dependencies` and sends only what it is given;
      `frontend/src/components/react/TaskEditor.tsx`: `title`/`description` render read-only, the
      `priority` control is removed, and `dependencies` is disabled and omitted from the payload while
      the new `frozen` prop is true.
- [ ] 2.8 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`:
      `TASK_VERSION_FROZEN` copy in `errorCodes` plus any read-only label the recut needs, neutral
      international Spanish; `frontend/src/lib/__tests__/error-codes.test.ts`:
      `EXPECTED_REGISTRY_COUNT` `38` → `39` and both locale counts `43` → `44`. Prove with
      `cd frontend && pnpm test`.
- [ ] 2.9 TRIANGULATE (frontend) — `frontend/src/components/react/__tests__/TaskEditor.test.tsx`:
      the frozen edge — a frozen task's save body carries no `dependencies` key, and a
      current-version task's save body carries exactly the keys the contract accepts; a
      `{"status": …}`-only save is never blocked and never warns. Prove with
      `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx`.
- [ ] 2.10 REFACTOR — rerun `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.
- [ ] 2.11 REFACTOR (frontend) — rerun
      `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx src/lib/__tests__/tasks-api.test.ts src/components/react/__tests__/KanbanBoard.test.tsx`.

## Phase 3: WU3 — The Reads

Commit: `feat(api): read only the current version and expose the version selector`.
Runner: `cd backend && conda run -n storico python -m pytest` (unit layer, `-m "not integration"`).
Backend only; the frontend consumers of these reads are Phase 6.

- [ ] 3.1 RED — `backend/tests/test_repositories/test_task_repo.py`: the failing current-version
      cases — story scope with v1 and v2 both `completed` returns only v2's 4 tasks and a `total` of
      4; a page falling past the end still carries the filtered total (the fallback `count_stmt`
      path); workspace scope with a superseded earlier version returns only current tasks with
      `total == len(items)`; the `workspace_ids` scope is filtered too; an explicit `extraction_id`
      reads exactly that version with no currency predicate. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_task_repo.py -m "not integration"`.
- [ ] 3.2 RED — `backend/tests/test_repositories/test_extraction_repo.py`: `list_versions(story_id)`
      returns every version ordered `version_number DESC` with no page window, and
      `find_current_version` equals the first `completed` entry of that list for a three-version
      story. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_extraction_repo.py -m "not integration"`.
- [ ] 3.3 GREEN — `backend/src/storico/domain/ports/task_repository.py`: `list_page(...)` gains the
      optional `extraction_id: UUID | None` and documents the current-version predicate; add
      `list_current_by_workspace(workspace_id) -> list[Task]`.
- [ ] 3.4 GREEN — `backend/src/storico/infrastructure/database/repositories/task_repository.py`: add
      the correlated highest-`completed` subquery to the story scope, the `extraction_id` arm, and
      the `NOT EXISTS` predicate to the workspace and `workspace_ids` scopes — all joined to the
      existing `scope` variable so `stmt` and `count_stmt` share it — plus
      `list_current_by_workspace`.
- [ ] 3.5 GREEN — `backend/src/storico/domain/ports/extraction_repository.py` and
      `backend/src/storico/infrastructure/database/repositories/extraction_repository.py`: add
      `list_versions(user_story_id) -> list[Extraction]` ordered `version_number DESC`, deliberately
      unbounded, with the docstring stating why the paginator's window must not truncate it.
- [ ] 3.6 GREEN — `backend/src/storico/api/routes/tasks.py`: `list_tasks` gains
      `extraction_id: UUID | None`; with `user_story_id` + `extraction_id` it resolves the version
      through the extraction repository, refuses a version that does not belong to that story with
      422 `REQUEST_VALIDATION_FAILED`, and passes `extraction_id` into `list_page`;
      `extraction_id` without `user_story_id` is 422; the workspace, story and unfiltered branches
      keep their existing membership refusals.
- [ ] 3.7 GREEN — `backend/src/storico/api/routes/export.py`: `export_tasks` serializes
      `repo.list_current_by_workspace(workspace.id)` instead of `list_by_workspace`, so the filter
      rides the serializing statement.
- [ ] 3.8 GREEN — `backend/src/storico/api/schemas/story.py`: add `StoryVersionResponse` with `id`,
      `version_number`, `status`, `model_used`, `provider`, `temperature`, `created_at`,
      `completed_at`, `error_info`, `is_current` and `has_output`;
      `backend/src/storico/api/schemas/extraction.py`: add `version_number: int | None`,
      `provider: str` and `temperature: float` to `ExtractionResponse` and `ExtractResponse`.
- [ ] 3.9 GREEN — `backend/src/storico/api/routes/stories.py`: add `GET /{story_id}/versions` using
      the **unchanged** `require_story_workspace_access` walk (404 for a missing story, 403
      `NOT_A_WORKSPACE_MEMBER` for a non-member — the same posture `GET /{story_id}` has today, with
      no membership-hiding flag), `extraction_repo.list_versions(story_id)`, `is_current` = the first
      `completed` entry of the ordered list, `has_output` = `status == completed`, returned as a bare
      unpaginated array.
- [ ] 3.10 TRIANGULATE — `backend/tests/test_api/test_tasks.py` (`extraction_id` from another story
      is 422 `REQUEST_VALIDATION_FAILED` and returns no task of story B; `extraction_id` without
      `user_story_id` is 422; a story whose only run is `failed` reads 200 `[]`),
      `backend/tests/test_api/test_stories.py` (three completed versions mark exactly v3
      `is_current`; v2 completed + v3 pending marks v2 `is_current`; 25 versions arrive in one
      payload; a missing story is 404 and a non-member 403, never a silent empty 200; a failed
      version carries `status`, `error_info`, `model_used`, `provider`, `temperature` and
      `has_output=false`), and `backend/tests/test_api/test_unfiltered_list_queries.py` (the
      no-parameter `GET /api/v1/tasks/` shows no superseded tasks). Prove with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py tests/test_api/test_stories.py tests/test_api/test_unfiltered_list_queries.py -m "not integration"`.
- [ ] 3.11 TRIANGULATE (cross-cutting) — `backend/tests/test_api/test_export.py`: the JSON and
      Markdown exports of a story whose v1 and v2 are both `completed` contain exactly v2's 4 tasks,
      and a story whose only run is `failed` contributes nothing while the file stays valid. Prove
      with `cd backend && conda run -n storico python -m pytest tests/test_api/test_export.py -m "not integration"`.
- [ ] 3.12 REFACTOR — `backend/src/storico/infrastructure/database/repositories/task_repository.py`:
      confirm `list_by_workspace` still serves its remaining callers, that no read path filters in
      Python, and that the page and its `total` still come from one statement; then
      rerun `cd backend && conda run -n storico python -m pytest tests/test_api tests/test_repositories -m "not integration"`.

## Phase 4: WU4 — The Gate and the Sanctioned Deletion

Commit: `feat(api): gate version mutations to the owner or an admin and delete a story with its record and cleanup`.
Runner: `cd backend && conda run -n storico python -m pytest` (unit layer); the Postgres-only cases
carry their own lines. Backend only; the delete dialog's version count is Phase 6.
Sequenced after Phase 3 because 4.13's snapshot consumes 3.5's `list_versions`.

- [ ] 4.1 RED — `backend/tests/test_unit/test_workspace_gate.py` **New** (path free): the truth table
      over `_is_owner_or_admin` — the workspace owner passes, a member with role `ADMIN` passes, a
      member with role `MEMBER` fails, and no other combination passes. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_unit/test_workspace_gate.py -m "not integration"`.
- [ ] 4.2 RED — `backend/tests/test_api/test_extraction.py`, `backend/tests/test_api/test_tasks.py`
      and `backend/tests/test_api/test_stories.py`: the failing gate cases — a `MEMBER` gets 403
      `WORKSPACE_OWNER_OR_ADMIN_REQUIRED` on extract, mark, unmark and story delete with no data
      changed; the owner and an `ADMIN` succeed on all four; a non-member keeps the unchanged
      403 `NOT_A_WORKSPACE_MEMBER` / 404 `EntityNotFound`; a `MEMBER` still reads the board, moves a
      card, edits `labels`, edits the story's four fields and reads versions (the repetition read
      becomes reachable in Phase 5); an exhausted allocation answers 409 `VERSION_ALLOCATION_CONFLICT`,
      never 500 and never 202, with no extraction row written. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.
- [ ] 4.3 RED — `backend/tests/test_api/test_stories.py` and
      `backend/tests/test_repositories/test_user_story_repo.py` (the file the design calls
      `test_story_repo.py`): the failing deletion cases — the owner deletes a story with v1 and v2
      and a record carries the actor, the timestamp and `[1, 2]`; a recording fake vector store
      receives exactly one `delete_by_story` for the story; a raising fake store answers 503
      `VECTOR_STORE_UNAVAILABLE` with the story, its versions, its tasks and no record intact; with
      no vector store configured the delete completes with a record and no vector call; a forced
      repository error in the record insert leaves the story present. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_stories.py tests/test_repositories/test_user_story_repo.py -m "not integration"`.
- [ ] 4.4 RED — `backend/tests/test_unit/test_story_deletions_migration.py` **New** (path free): pin
      `revision == "0029"` and `down_revision == "0028"` loaded by path with the
      `test_add_completed_at_migration.py` pattern, that `downgrade()` drops `story_deletions`, and
      that the model declares no foreign key to `stories` or `extractions`. Prove RED without Docker
      with `cd backend && conda run -n storico python -m pytest tests/test_unit/test_story_deletions_migration.py -m "not integration"`.
- [ ] 4.5 GREEN — `backend/src/storico/api/dependencies.py`: move the body of
      `require_story_workspace_access` into `resolve_story_access(...) -> StoryAccess` with the three
      statements and the refusals byte-for-byte unchanged, keep `require_story_workspace_access` as a
      thin caller returning `.story`, add `resolve_task_access(...) -> TaskAccess` (leading
      `task_repo.find_by_id`, reported as `("Task", task_id)`) and make
      `_validate_task_workspace_access` in `backend/src/storico/api/routes/tasks.py` a thin caller of
      it; then add `_is_owner_or_admin(workspace, role, user)`, `require_owner_or_admin`,
      `require_story_owner_or_admin` and `require_task_owner_or_admin`. The membership refusal fires
      first in the shared walk; `ApiError(403, WORKSPACE_OWNER_OR_ADMIN_REQUIRED)` is raised only for
      a member who is neither owner nor `ADMIN`.
- [ ] 4.6 GREEN — `backend/src/storico/api/routes/extraction.py`: replace
      `Depends(get_workspace_for_user)` with `Depends(require_owner_or_admin)` and add
      `version_number` to the 202 `ExtractResponse` from the pending version slice (a) minted.
- [ ] 4.7 GREEN — `backend/src/storico/api/error_codes.py`: add `VERSION_ALLOCATION_CONFLICT`,
      `VECTOR_STORE_UNAVAILABLE` and `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`;
      `backend/src/storico/api/errors.py`: add `version_allocation_conflict_handler` (409, `detail`
      from `str(exc)`, composed from the exception's own `user_story_id` if `str(exc)` is silent) and
      `vector_store_error_handler` (503), both registered in `register_exception_handlers` for their
      own classes so MRO resolves the subclass before `repository_error_handler`.
- [ ] 4.8 GREEN — `backend/src/storico/domain/entities/exceptions.py`: add
      `VectorStoreError(Exception)` next to the `LLMError` family;
      `backend/src/storico/domain/entities/story_deletion.py` **New** (path free): the frozen
      `StoryDeletion` carrying the story identity as values, `version_numbers`, `deleted_by` and
      `deleted_at`.
- [ ] 4.9 GREEN — `backend/src/storico/infrastructure/database/models/story_deletion.py` **New**
      (path free): the `story_deletions` model with no foreign key to `stories` or `extractions`,
      `version_numbers` as `sa.JSON` so it builds in the SQLite unit schema, and `deleted_by` as a
      `users.id` foreign key with `ON DELETE SET NULL`; register it in
      `backend/src/storico/infrastructure/database/models/__init__.py` (the drift gate compares
      models to the migrated schema).
- [ ] 4.10 GREEN — `backend/src/storico/infrastructure/database/alembic/versions/0029_story_deletions.py`
      **New** (path free): `revision = "0029"`, `down_revision = "0028"`, create `story_deletions`
      with its index and the actor foreign key, and a `downgrade()` that drops the table. It is
      additive, so unlike `0028` it needs no empty-database guard.
- [ ] 4.11 GREEN — `backend/src/storico/domain/ports/user_story_repository.py`: add
      `delete_with_record(user_story_id, record)`; `backend/src/storico/infrastructure/database/repositories/user_story_repository.py`:
      implement it as one transaction — the story `DELETE`, the record `INSERT`, one `commit` — that
      rolls back and raises `EntityNotFound` when the delete matched no row.
- [ ] 4.12 GREEN — `backend/src/storico/domain/ports/vector_store_port.py`: add
      `delete_by_story(*, workspace_id, user_story_id)` whose docstring states that, unlike
      `search_similar`/`store_extraction`, it raises `VectorStoreError` because its caller is
      destructive; `backend/src/storico/infrastructure/vector/qdrant_adapter.py`: implement it with a
      `FilterSelector` over the existing `workspace_id` and `user_story_id` payload keys and
      `wait=True`, wrapping driver failures in `VectorStoreError`.
- [ ] 4.13 GREEN — `backend/src/storico/application/services/story_deletion_service.py` **New**
      (path free): the ordering — snapshot `list_versions`, build the `StoryDeletion` with the
      destroyed version numbers, call `delete_by_story` when a vector store is configured (skipped
      when it is `None`, because no points exist to clean), then `delete_with_record`;
      `backend/src/storico/api/routes/stories.py`: `DELETE /{story_id}` uses
      `require_story_owner_or_admin` and calls the service.
- [ ] 4.14 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`: the
      three new codes in `errorCodes` with neutral international Spanish;
      `frontend/src/lib/__tests__/error-codes.test.ts`: `EXPECTED_REGISTRY_COUNT` `39` → `42` and both
      locale counts `44` → `47`. Prove with `cd frontend && pnpm test`.
- [ ] 4.15 TRIANGULATE — `backend/tests/test_api/test_stories.py`: the refusal edge on the gated
      delete — a non-member keeps the unchanged 403 `NOT_A_WORKSPACE_MEMBER`, an addressed story that
      does not exist is 404 `EntityNotFound`, and a `MEMBER`'s 403 leaves the story, its versions,
      their tasks and their points intact. Prove with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_stories.py -m "not integration"`.
- [ ] 4.16 TRIANGULATE (Postgres-only — run where the Docker daemon exists) —
      `backend/tests/test_integration/test_story_deletion_record.py` **New** (path free), each case
      `@pytest.mark.integration` with the `_docker_reachable()` skipif: the record survives the
      cascade because it holds no foreign key to `stories`; deleting the actor nulls `deleted_by`
      only; the story's extractions, tasks and marks cascade away.
      `cd backend && conda run -n storico python -m pytest tests/test_integration/test_story_deletion_record.py -m integration`
      — **requires a Docker daemon (Postgres 16 via testcontainers); without one every case skips and
      the cascade stays unverified.**
- [ ] 4.17 TRIANGULATE (Postgres-only — run where the Docker daemon exists) —
      `backend/tests/test_integration/test_migration_chain.py` (existing): `0029` reaches head and the
      models ↔ migrated-schema drift set is still empty.
      `cd backend && conda run -n storico python -m pytest tests/test_integration/test_migration_chain.py -m integration`
      — same Docker requirement, same honest skip.
- [ ] 4.18 REFACTOR — `backend/src/storico/application/services/story_deletion_service.py` and
      `backend/src/storico/infrastructure/database/alembic/versions/0029_story_deletions.py`: confirm
      `story_deletions` is the only new table, that the delete order is cleanup-then-relational inside
      one transaction, and that `PUT /api/v1/tasks/{task_id}` was not gated; then rerun
      `cd backend && conda run -n storico python -m pytest tests/test_api tests/test_repositories tests/test_unit -m "not integration"`.

## Phase 5: WU5 — The Invalidation Mark and the Repetition Read

Commit: `feat(api): expose the invalidation mark and the repetition read`.
Runner: `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py tests/test_repositories/test_task_invalidation.py tests/test_unit -m "not integration"`.
The table and model already exist (slice (a)); this unit owns the entity, port, repository, validator
and endpoints — not the DDL.

- [ ] 5.1 RED — `backend/tests/test_unit/test_invalidation_request.py` **New** (path free):
      `CreateInvalidationRequest` refuses `""`, `"   "` and `"\t\n"` (Python whitespace is wider than
      the column's `CHECK`) and accepts a non-blank reason bounded by the column's 500. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_unit/test_invalidation_request.py -m "not integration"`.
- [ ] 5.2 RED — `backend/tests/test_unit/test_task_title_normalizer.py` **New** (path free):
      `normalize_task_title` casefolds, collapses whitespace runs to one space and strips, table-driven
      over the `casefold` cases SQL `lower` would miss. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_unit/test_task_title_normalizer.py -m "not integration"`.
- [ ] 5.3 RED — `backend/tests/test_repositories/test_task_invalidation.py` (the file slice (a)
      creates at 1.2/4.1; add the query-level cases): `find_active_by_task` finds the single active
      row; `list_by_task` orders `marked_at DESC` with the active mark first; `revoke` sets only
      `revoked_by`/`revoked_at` on the resolved row and deletes nothing; `list_active_on_other_versions`
      returns only non-revoked marks of the story's other versions, each carrying its `version_number`
      and title; a same-version mark is excluded. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_task_invalidation.py -m "not integration"`.
- [ ] 5.4 RED — `backend/tests/test_api/test_tasks.py`: the failing endpoint cases — a valid mark is
      201 with reason, actor and timestamp and exactly one row; a blank reason is 422
      `REQUEST_VALIDATION_FAILED` and writes nothing; a second active mark is 409 `TASK_ALREADY_MARKED`
      with the live reason in the `detail` and still one row; marking a frozen version is 409
      `TASK_VERSION_FROZEN` with no row; a `MEMBER` is 403 `WORKSPACE_OWNER_OR_ADMIN_REQUIRED` with no
      row; `GET` returns the full history active-first with all six fields for every member and
      `200 []` for an unmarked task; revoke is 204 on the same row with `marked_by`, `marked_at` and
      `reason` intact, 409 on a frozen version with the row unchanged, 404 with no active mark; a
      re-mark after a revoke writes a second row and leaves the first revoked; the repetition read
      returns the match, `{"matches": []}` for no match / the task's own version / another story / a
      revoked mark, and creates, updates and revokes nothing. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`.
- [ ] 5.5 GREEN — `backend/src/storico/domain/entities/task_invalidation.py` **New** (path free): the
      frozen, slotted `TaskInvalidation`;
      `backend/src/storico/domain/ports/task_invalidation_repository.py` **New** (path free): the port
      (`create`, `find_active_by_task`, `list_by_task`, `revoke`) plus the `TaskInvalidationCandidate`
      read model and the join contract of `list_active_on_other_versions`.
- [ ] 5.6 GREEN — `backend/src/storico/infrastructure/database/repositories/task_invalidation_repository.py`
      **New** (path free): `create`, `find_active_by_task`, `list_by_task`, `revoke` as an `UPDATE` of
      the row `find_active_by_task` resolved, and the
      `task_invalidations JOIN tasks JOIN extractions` candidate read filtered by story,
      `extraction_id IS DISTINCT FROM` the excluded version and `revoked_at IS NULL`, ordered
      `version_number DESC, marked_at DESC`.
- [ ] 5.7 GREEN — `backend/src/storico/domain/services/task_title_normalizer.py` **New** (path free):
      `normalize_task_title(text)` = casefold + whitespace-run collapse + strip.
- [ ] 5.8 GREEN — `backend/src/storico/api/schemas/task.py`: `CreateInvalidationRequest` with the
      blank-reason `field_validator` and the 500 bound, `InvalidationResponse`, `RepetitionMatch` and
      `RepetitionResponse`.
- [ ] 5.9 GREEN — `backend/src/storico/api/routes/tasks.py`: add `POST /{task_id}/invalidations`
      (201), `GET /{task_id}/invalidations`, `DELETE /{task_id}/invalidations/current` (204) and
      `GET /{task_id}/invalidations/repetition`. Gate create and revoke with
      `require_task_owner_or_admin`; keep the two reads membership-only; reuse the frozen check from
      2.3; use `find_active_by_task` for the 409 and the 404; resolve the task's title server-side and
      match in Python with `normalize_task_title` over the candidate read — no fuzzy or vector
      comparison, and no write or propagation.
- [ ] 5.10 GREEN — `backend/src/storico/api/error_codes.py`: add `TASK_ALREADY_MARKED`.
- [ ] 5.11 TRIANGULATE — `backend/tests/test_api/test_tasks.py`: the pinned edges — a blank reason
      persists nothing for `""`, `"   "` and `"\t\n"`; a frozen version refuses both the mark and the
      revoke and leaves the row unchanged; the repetition read writes nothing and a one-character
      title difference yields no match with no similarity call. Prove with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`.
- [ ] 5.12 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`:
      `TASK_ALREADY_MARKED` in `errorCodes` with neutral international Spanish;
      `frontend/src/lib/__tests__/error-codes.test.ts`: `EXPECTED_REGISTRY_COUNT` `42` → `43` and both
      locale counts `47` → `48`. Prove with `cd frontend && pnpm test`.
- [ ] 5.13 REFACTOR — rerun
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py tests/test_repositories/test_task_invalidation.py tests/test_unit -m "not integration"`.

## Phase 6: WU6 — The Version-Aware UI

Commit: `feat(frontend): wire the version selector, the mark controls and the confirmations into the editor`.
Runner: `cd frontend && pnpm test` (vitest). Frontend only; every behavior task has its component or
store test in this unit.

- [ ] 6.1 RED — `frontend/src/lib/__tests__/workspace-role.test.ts` **New** (path free) and
      `frontend/src/lib/__tests__/versioning-api.test.ts` **New** (path free): the failing cases —
      `canManageVersions` is true for the owner and for a member with role `admin` and false for a
      `member` or a missing workspace/user; `listVersions`, `createInvalidation`, `listInvalidations`,
      `revokeInvalidation` and `fetchRepetition` hit their paths with their payloads. Prove RED with
      `cd frontend && pnpm test src/lib/__tests__/workspace-role.test.ts src/lib/__tests__/versioning-api.test.ts`.
- [ ] 6.2 GREEN — `frontend/src/lib/workspace-role.ts` **New** (path free) and
      `frontend/src/lib/versioning-api.ts` **New** (path free);
      `frontend/src/types/task.ts`, `frontend/src/types/story.ts` and
      `frontend/src/types/workspace.ts`: the version and mark types.
- [ ] 6.3 RED — `frontend/src/components/react/__tests__/VersionSelector.test.tsx` **New** (path
      free) and `frontend/src/components/react/__tests__/StoryDetail.test.tsx`: the failing cases —
      every version is listed with exactly the current one marked; a failed version is offered with
      its `error_info`, model and date and renders a localized "no output" state, never an empty
      board; the "Marcar como inválida" button opens the editor with the checkbox checked and the
      focus in the reason field and issues no request; cancelling issues no request; the extract
      confirmation names the frozen and the new version; cancelling the extract performs no request;
      no workspace selected shows the localized prompt with no request; a `MEMBER`'s 403 renders the
      code's localized copy; the story-delete dialog names the version count and cancel issues no
      request. Prove RED with
      `cd frontend && pnpm test src/components/react/__tests__/VersionSelector.test.tsx src/components/react/__tests__/StoryDetail.test.tsx`.
- [ ] 6.4 RED — `frontend/src/components/react/__tests__/TaskEditor.test.tsx` and
      `frontend/src/stores/__tests__/taskStore.unit.test.ts`: the failing cases — the "Inválida"
      checkbox with a mandatory reason textarea, an empty reason blocking the save with no request, a
      non-empty reason persisting the mark, unchecking revoking it, both confirmation dialogs with
      cancel issuing no request, the D16 notice showing the earlier version and reason with one copy
      action that persists nothing, a near-identical title not triggering the notice, a save failure
      rolling back with the dialog open and the edits intact, and the store categorizing 409
      `VERSION_ALLOCATION_CONFLICT` as `'version-conflict'` before the status codes and 401/403 as
      `unauthorized`. Prove RED with
      `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx src/stores/__tests__/taskStore.unit.test.ts`.
- [ ] 6.5 GREEN — `frontend/src/components/react/VersionSelector.tsx` **New** (path free);
      `frontend/src/components/react/StoryDetail.tsx`: the selector wiring, the "Marcar como inválida"
      button beside "Editar", the extract confirmation naming both version numbers, the
      `MEMBER`-hidden/disabled controls via `canManageVersions`, and the delete dialog's version
      count fetched on open with a neutral fallback sentence when that read fails;
      `frontend/src/components/react/StoriesList.tsx`: the same delete-dialog version count.
- [ ] 6.6 GREEN — `frontend/src/components/react/TaskEditor.tsx`: the "Inválida" checkbox, the
      mandatory reason textarea, the D16 notice with its copy action, the two confirmation dialogs and
      the submission sequence (mark → `POST`, unmark → `DELETE …/current`, then `PUT`) with optimistic
      update and rollback; `frontend/src/stores/taskStore.ts`: the `'version-conflict'` category and
      the version-aware extraction state; `frontend/src/stores/storyStore.ts`: the version state the
      delete dialog reads.
- [ ] 6.7 GREEN — `frontend/src/components/react/KanbanBoard.tsx`,
      `frontend/src/components/react/ExportPanel.tsx` and
      `frontend/src/components/react/__tests__/KanbanBoard.test.tsx`: confirm the filtered reads land
      as current-version-only cards (a story with two completed runs shows 4 cards and none from v1), a
      failed-only story contributes no cards and no error, and a status change on a frozen version is
      neither blocked nor warned.
- [ ] 6.8 GREEN (copy) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`: the selector,
      mark-controls, confirmation, D16 notice, "no output" and delete-dialog copy in both locales with
      identical key sets and neutral international Spanish (`tú`, no voseo), plus the corrected
      `landing.faq.a4` that no longer promises editing `title`/`description` or per-task deletion;
      `frontend/src/i18n/__tests__/api-docs-copy.test.ts` stays green because both retirement handlers
      use exact paths and `include_in_schema=False`.
- [ ] 6.9 TRIANGULATE (frontend) — `frontend/src/components/react/__tests__/TaskEditor.test.tsx`:
      the cancel edge — the extract confirmation, the mark confirmation and the unmark confirmation
      each issue zero requests and change nothing when cancelled;
      `frontend/src/components/react/__tests__/StoriesList.test.tsx`: cancelling the delete dialog
      issues no request, and a failed version-count read keeps the confirm enabled with the fallback
      sentence. Prove with `cd frontend && pnpm test`.
- [ ] 6.10 REFACTOR (frontend) — rerun `cd frontend && pnpm test` and confirm the i18n key-parity and
      neutral-Spanish suites are green.

## Phase 7: Slice Verification

- [ ] 7.1 Whole backend suite: `cd backend && conda run -n storico python -m pytest`.
- [ ] 7.2 Whole frontend suite: `cd frontend && pnpm test` (includes the neutral-Spanish and key-parity
      guards).
- [ ] 7.3 Integration layer, run where the Docker daemon exists:
      `cd backend && conda run -n storico python -m pytest -m integration`. Without a Docker daemon
      every case skips and the Postgres-only invariants (the story-deletion cascade, the record's
      survival, the `deleted_by` null-out, the partial-index shape, the migration chain) stay
      unverified — record that outcome instead of reporting green.
- [ ] 7.4 Repo-documented lint/format (`AGENTS.md` §0): from `backend/`,
      `conda run -n storico python -m ruff check src tests` and
      `conda run -n storico python -m ruff format --check src tests`.
- [ ] 7.5 Record in the verify report the honest split of evidence: what the SQLite unit layer proved,
      what the frontend vitest suite proved, what ran against Postgres, and what skipped without a
      Docker daemon.

## Slice Boundary

- **This slice depends on `extraction-versioning-schema` (a) and must ship in the same release as it.**
  (a) alone doubles a story's task sets on the board, because the current-version filter lands here;
  (b) alone cannot run at all, because it consumes `version_number`, `tasks.extraction_id`,
  `task_invalidations`, `find_current_version` and `VersionAllocationConflictError` from (a).
- **`extraction-versioning-prompt` (c) depends on both.** Slice (c) inherits one seam from this slice:
  the Qdrant `has_invalid_tasks` payload key it adds must keep D10's exclusion honest **after** a mark
  or a revoke, because (b) makes marks creatable and revocable and a revoked mark must stop excluding
  its point — (b) leaves `_store_rag` untouched, and (c) owns the payload-key content and the
  `search_similar` signature change.
- **READ THIS BEFORE CALLING TASKS 5.4 AND 5.9 DONE.** Slice (b) ships marks that do **not** move the
  vector flag: no task here calls `set_has_invalid_tasks`, and (b) is complete and green without it.
  The call sites live in **(c) WU3 tasks 3.6–3.8**, which edit this slice's handler file and its
  tests, and the refresh must run **before** the mark's relational write (the spec requires that a
  refresh failure leaves no mark persisted). If (c) 3.6–3.8 are skipped, every mark in production
  excludes nothing from few-shot retrieval and **nothing goes red** — D10 fails silently. Track this
  as the one cross-slice dependency that no test in this file can prove.
- **The D11 data wipe and the release bump are not tasks here.** The relational wipe plus the two
  Qdrant collections (`storico_extractions_dev`, `storico_extractions_prod`) is a separate destructive
  operation with its own confirmation, executed before the deploy that carries `0028` (slice (a)); the
  version bump is `make bump`, never a hand-edit and never a task in a change.
- **Out of this slice**: per-version export (the export follows the current version); exposing
  `prompt_rendered` or the snapshot through the API; the board's pre-existing `size=100` window; rate
  limiting; a story-scoped task creation path of any kind; per-task judge scores; side-by-side
  comparison; experiment grouping; batch extraction (a closed non-goal); and removing `priority` from
  the contract (a separate `BREAKING` release).
