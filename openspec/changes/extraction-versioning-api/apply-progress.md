# Apply Progress — extraction-versioning-api

Cumulative log. WU1 tranche A (backend only) — 2026-09-30, branch `feat/extraction-versioning-api-wu1`.

## Structured status consumed

`gentle-ai.sdd-status` v2 for `extraction-versioning-api`: `nextRecommended: apply`, `applyState:
ready`, `blockedReasons: []`, dependencies proposal/specs/design/tasks `all_done`,
`taskProgress` 77 total / 0 completed at start. `actionContext`: mode `repo-local`,
workspaceRoot `/Users/alvaldes/Developer/storico`, `allowedEditRoots` `["/Users/alvaldes/Developer/storico"]`.
Artifact store `openspec`. Consumed before any edit; no blocker.

## Review Workload Gate

Slice forecast: 400-line risk High, chained PRs recommended, decision needed — resolved by the
parent with the 2026-09-28 user delivery decision (`ask-on-risk — RESOLVED`, one PR per work unit,
`size:exception` only for WU2/WU4). This run = WU1 only, which fits the 400-line budget. No
exception used.

## Completed tasks (persisted checkboxes updated in tasks.md as each closed)

- [x] 1.1 RED — retirement cases for `DELETE /api/v1/tasks/{task_id}` (410 `TASK_DELETE_ENDPOINT_REMOVED`, detail names D12, row left intact and still linked to its version) and `POST /api/v1/tasks/` (410 `TASK_CREATION_ENDPOINT_REMOVED`, detail names D3, no row added). Also reconciled the other POST cases that pinned the pre-retirement contract (two 403 non-member cases → same 410, unknown-story 404 → 410, member 500 → 410), each preserving its nothing-persisted assertion. See "Deviations" below.
- [x] 1.2 RED — flipped slice (a)'s two pinned 500 cases (`TestCreateTask::test_create_task`, `::test_create_task_with_labels`) to pin the 410; added the route-shape cases: `DELETE /api/v1/tasks/{task_id}/invalidations/current` is not swallowed by the retirement (not 410, code absent — WU5 owns the real route) and `DELETE /api/v1/tasks/` still answers 405, not 410.
- [x] 1.3 GREEN — `routes/tasks.py`: `deprecated_delete_task` = `@router.api_route("/{task_id}", methods=["DELETE"], status_code=410, include_in_schema=False)`, runs the unchanged `_validate_task_workspace_access` walk, then raises `ApiError(410, TASK_DELETE_ENDPOINT_REMOVED, …)`; no `repo.delete` call remains. `deprecated_create_task` = `@router.api_route("/", methods=["POST"], status_code=410, include_in_schema=False)`, reads no body, runs no walk, raises `ApiError(410, TASK_CREATION_ENDPOINT_REMOVED, …)`. Exact paths, not `/{path:path}` — the two precedents (`extraction.py:68-91`, `projects.py:35-59`) were followed for the decorator/error shape, with the design's exact-path refinement.
- [x] 1.4 GREEN — deleted `CreateTaskRequest` from `api/schemas/task.py` (and the `Field` import it left unused); added `TASK_CREATION_ENDPOINT_REMOVED` / `TASK_DELETE_ENDPOINT_REMOVED` to the sorted `__all__` and the `# ── Route raise sites` block in `error_codes.py`.
- [x] 1.6 TRIANGULATE — non-member `DELETE /api/v1/tasks/{task_id}` → 403 `NOT_A_WORKSPACE_MEMBER` (`detail == "Not a member of this workspace"`, workspace id absent from the body) before the 410, with the row intact and still linked to its version; unknown task id → 404 `ENTITY_NOT_FOUND` (pinned by `test_delete_task_not_found`, which keeps passing unchanged).
- [x] 1.7 REFACTOR — no `CreateTaskRequest` reference and no `repo.delete(` left in `routes/tasks.py` (grep-checked); ruff check + format clean on all touched files; wider gate rerun (below).

## TDD Cycle Evidence

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| RED (1.1+1.2) | 6 POST retirement cases + `TestDeleteTask::test_delete_task` | `conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"` | **7 failed, 18 passed** (observed failing: 204/500/403/404 old shapes) |
| GREEN (1.3+1.4) | whole focused file | same command | **25 passed** |
| TRIANGULATE (1.6) | + non-member 403 edge | same command | **26 passed** |
| REFACTOR (1.7) | wider `tests/test_api` | `conda run -n storico python -m pytest tests/test_api -m "not integration"` | **350 passed** |
| Companion check | `tests/contract/test_api_schemas.py` | `conda run -n storico python -m pytest tests/contract/test_api_schemas.py -m "not integration"` | **34 passed** |

Lint: `ruff check` and `ruff format --check` clean on all six touched backend files (one format fix applied to a too-long test signature line).

## Files changed (WU1 backend boundary — 346 changed lines: 205+/141−)

- `backend/tests/test_api/test_tasks.py` (+133/−63)
- `backend/src/storico/api/routes/tasks.py` (+58/−54)
- `backend/src/storico/api/error_codes.py` (+10/−0)
- `backend/src/storico/api/schemas/task.py` (+1/−15)
- `backend/src/storico/api/schemas/__init__.py` (+1/−2) — **companion edit, see deviations**
- `backend/tests/contract/test_api_schemas.py` (+2/−7) — **companion edit, see deviations**

Not committed, not staged — the parent lands the work-unit commit. The pre-existing modifications
to `odd/tasks/extraction-versioning-090.md` and the untracked `backend/.gitignore` /
`.claude/skills/` were present before this run and were not touched.

## Deviations from design / task letter

1. **`NoReturn` → `None`.** The design's handler sketch annotates the two retirement handlers
   `-> NoReturn`; FastAPI rejects that as a response field (`Invalid args for response field!`),
   and the repo's two precedents use `-> None`. Both handlers are `-> None`, matching the
   precedents the design cites.
2. **Two companion edits outside the four declared surfaces**, both mechanically entailed by task
   1.4's "delete `CreateTaskRequest` (and any import it leaves unused)":
   `api/schemas/__init__.py` (the stale re-export import + `__all__` entry — without it the package
   import fails and the whole suite is red), and `tests/contract/test_api_schemas.py`
   (`test_create_task_request_forbids_extra` imported the deleted class; its comment block was
   updated to reference only `CreateUserStoryRequest`). Without these, slice verification 7.1
   cannot go green. Disclosed to the parent; the PR boundary for WU1 is backend-only and includes
   exactly these six files.
3. **The other POST test cases were reconciled in RED**, not only the two (a)-pinned 500s named by
   1.2: `test_create_task_is_forbidden_for_a_non_member`,
   `test_create_task_is_forbidden_in_another_users_workspace`,
   `test_create_task_rejects_an_unknown_story_id` and
   `test_a_member_post_answers_the_refusal_too_and_persists_nothing` all pinned the
   pre-retirement contract (403/404/500) and would have failed the REFACTOR gate. Each was
   rewritten to pin the retirement (410 for every caller, nothing persisted), per the design's
   recorded settlement that the create handler reads no body and runs no walk — the one place the
   design does not carry "both handlers keep membership-only access".

## Known cross-stack coupling (NOT this run's regression)

`frontend/src/lib/__tests__/error-codes.test.ts` pins `EXPECTED_REGISTRY_COUNT: 36` and locale
counts 41; the two new backend codes make the real registry 38. **That test now legitimately fails
and was deliberately not touched** — the frontend mirror is task 1.5 and REFACTOR 1.8, assigned to
the second writer (tranche B). No frontend file was edited in this run, and no frontend test was
executed.

## Remaining unchecked tasks (exact lines from tasks.md)

- [ ] 1.5 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`: add
- [ ] 1.8 REFACTOR (frontend) — rerun

(Both belong to tranche B, with Phases 2–7 untouched: 68 tasks pending.)

---

# Apply Progress — WU1 tranche B (frontend mirror) — 2026-09-30, branch `feat/extraction-versioning-api-wu1`

Closes WU1. Backend tranche A above is preserved verbatim; nothing in it was changed.

## Structured status consumed

`gentle-ai.sdd-status` v2 for `extraction-versioning-api` from the parent: `nextRecommended: apply`,
`applyState: ready`, `blockedReasons: []`, `taskProgress` 77 total / 6 completed at the start of this
run, `actionContext` mode `repo-local`, workspaceRoot and `allowedEditRoots`
`["/Users/alvaldes/Developer/storico"]`. All edits stayed inside the three allowed frontend files
plus the two SDD artifacts; no backend file was touched.

## Completed tasks (persisted checkboxes updated in tasks.md as each closed)

- [x] 1.5 GREEN (frontend mirror) — added `TASK_CREATION_ENDPOINT_REMOVED` and
      `TASK_DELETE_ENDPOINT_REMOVED` to the `errorCodes` family in both `frontend/src/i18n/en.json`
      and `frontend/src/i18n/es.json`, inserted after `EXTRACTION_NOT_FOUND`, worded to match the two
      existing retirement entries (`PROJECT_ENDPOINT_REMOVED`, `EXTRACTION_ENDPOINT_REMOVED`) and to
      carry the D3/D12 replacement the backend detail strings name (creation → extract the story
      again; deletion → a task is only destroyed together with its story). Spanish is neutral
      international with `tú` ("extrae", "nacen", no voseo). Updated the mirror test's
      `EXPECTED_REGISTRY_COUNT` 36 → 38 and its count-note comment (41 → 43 keys); the per-locale
      expectation is derived (`EXPECTED_REGISTRY_COUNT + ROUTE_ERROR_CODES.length`), so both locale
      counts move with the one constant.
- [x] 1.8 REFACTOR (frontend) — reran the three gate files (real counts below); no further cleanup
      was needed.

## TDD Cycle Evidence

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| RED (before 1.5) | `error-codes.test.ts` as tranche A left it | `cd frontend && pnpm test src/lib/__tests__/error-codes.test.ts` | **2 failed, 6 passed (8)** — registry extraction reads 38 names vs `EXPECTED_REGISTRY_COUNT` 36, and the mirror case reports the two codes missing from both locales |
| GREEN (1.5) | same file after the edit | same command | **8 passed** |
| REFACTOR (1.8) | the three gate files | `cd frontend && pnpm test src/lib/__tests__/error-codes.test.ts src/i18n/__tests__/neutral-spanish.test.ts src/i18n/__tests__/no-duplicate-keys.test.ts` | **3 files passed, 23 passed, 0 failed** |

## Files changed (tranche B — 8+/3− = 11 changed lines; WU1 total ≈ 357, inside the ≈260–340 + mirror estimate)

- `frontend/src/i18n/en.json` (+2/−0)
- `frontend/src/i18n/es.json` (+2/−0)
- `frontend/src/lib/__tests__/error-codes.test.ts` (+4/−3) — one constant, the count-note comment, no logic change

Not committed, not staged — the parent lands the work-unit commit. The untracked `backend/.gitignore`,
`.claude/skills/`, and `odd/tasks/extraction-versioning-090.md` were not touched.

## Deviations from design / task letter

None. The only judgment call: the count-note comment inside `error-codes.test.ts` was updated
alongside the constant so it does not lie about the map's size (36+5 → 38+5); no comment, test or
blank line was deleted.

## Remaining unchecked tasks (69; exact sections from tasks.md)

- Phase 2: WU2 — The Field Matrix and the Version-Aware Client (2.1–2.11, all unchecked)
- Phase 3: WU3 — The Reads (3.1–3.12, all unchecked)
- Phase 4: WU4 — The Gate and the Sanctioned Deletion (4.1–4.18, all unchecked)
- Phase 5: WU5 — The Invalidation Mark and the Repetition Read (5.1–5.13, all unchecked)
- Phase 6: WU6 — The Version-Aware UI (6.x, all unchecked)
- Phase 7 (verification tasks, if listed beyond Phase 6 — all unchecked)

No WU1 task remains unchecked.

## WU1 PR boundary — CLOSED

All eight WU1 tasks (1.1–1.8) are `- [x]`. The work unit now spans backend tranche A (346 lines) plus
this frontend mirror (11 lines). Suggested commit message (tasks.md):
`refactor(api): retire manual task creation and single-task deletion with 410 Gone`.

## Risks

- None new. The mirror test derives both locale counts from `EXPECTED_REGISTRY_COUNT`, so WU2's
  `TASK_VERSION_FROZEN` (38 → 39) lands as a one-constant bump plus two locale keys, same shape as
  this tranche.

## WU1 PR boundary

Backend half done (this run): two 410 retirements, schema deletion, two registry codes, full test
coverage. Pending for the same PR per tasks.md: the frontend mirror (1.5, 1.8) — `errorCodes` copy
in `en.json`/`es.json` and `EXPECTED_REGISTRY_COUNT` 36 → 38 / locale counts 41 → 43 — which tranche
B must land before the work-unit PR can go green. Suggested commit message (tasks.md): `refactor(api):
retire manual task creation and single-task deletion with 410 Gone`.

## Risks

- The 410 detail strings are developer-facing English; the user-facing copy arrives with 1.5.
- Until 1.5 lands, the frontend mirror test is red — expected, recorded above.
- `DELETE /api/v1/tasks/{task_id}/invalidations/current` currently answers the router's plain 404;
  WU5 registers the real revoke route on that exact path, and the route-shape test will then pin
  the live handler instead of the absence.

---

# Apply Progress — WU2 tranche T1 (backend field matrix) — 2026-09-30, branch `feat/extraction-versioning-api-wu2`

Implements tasks 2.1–2.5 only (the backend half of WU2). WU1 progress above is preserved verbatim.
Tasks 2.6–2.9 (frontend) and 2.10–2.11 (refactor reruns) remain for the later tranches of this unit.

## Structured status consumed

`gentle-ai.sdd-status` v2 for `extraction-versioning-api` from the parent: `nextRecommended: apply`,
`applyState: ready`, `blockedReasons: []`, `taskProgress` 77 total / 8 completed at start,
`actionContext` mode `repo-local`, workspaceRoot `/Users/alvaldes/Developer/storico`,
`allowedEditRoots` `["/Users/alvaldes/Developer/storico"]`. All edits stayed inside the four allowed
backend files plus the two SDD artifacts; no frontend file was touched. Review Workload Gate: the
parent prompt carried the resolved delivery path (owner's 2026-09-28 decision; `size:exception`
accepted for WU2), so work proceeded under the exception.

## Completed tasks (persisted checkboxes updated in tasks.md as each closed)

- [x] 2.1 RED — new `TestUpdateTaskFieldMatrix` in `backend/tests/test_api/test_tasks.py`: status on
      frozen → 200 persisted; labels on frozen → 200 persisted; dependencies on frozen → 409
      `TASK_VERSION_FROZEN` with `detail.current_version == 2` and dependencies unchanged;
      dependencies on current → 200 persisted; `title`/`description`/`priority` parametrized → 422
      `REQUEST_VALIDATION_FAILED` on both frozen and current with a no-field-changed assertion;
      mixed body (illegal `todo → done` + dependencies) on frozen → 409, not 400. Proven RED: **8
      failed, 31 passed**. Also reconciled `TestUpdateTask::test_update_task` in RED — it pinned the
      pre-matrix contract (title/description/priority in the body, 200); it now pins a status-only
      body with the untouched fields asserted unchanged. See deviations.
- [x] 2.2 GREEN — `UpdateTaskRequest` shrunk to `status`, `labels`, `dependencies`; the three removed
      fields deleted, `extra="forbid"` kept; docstring names the D5/D21 matrix and the 409.
- [x] 2.3 GREEN — `routes/tasks.py`: added `ExtractionRepoDep`; in `update_task` after the unchanged
      membership walk: `current = await extraction_repo.find_current_version(existing.user_story_id)`,
      `frozen = current is None or existing.extraction_id != current.id`, and the
      `"dependencies" in body.model_fields_set and frozen` guard raises
      `ApiError(409, TASK_VERSION_FROZEN, detail={"detail": …, "current_version": …})` **before** the
      state-machine check; the state machine and the `body.dependencies is not None` write are kept;
      the `title`/`description`/`priority` kwargs are gone. The `current is None` arm's detail says
      the story "has no current version" and carries `current_version: null`.
- [x] 2.4 GREEN — `error_codes.py`: `TASK_VERSION_FROZEN` in the sorted `__all__` (between
      `TASK_DELETE_ENDPOINT_REMOVED` and `UNSUPPORTED_EXPORT_FORMAT`) plus a comment block entry
      mirroring WU1's shape, naming D5/D21 and the presence-not-value rule.
- [x] 2.5 TRIANGULATE — presence edges, all green: `{"dependencies": []}` on frozen → 409 with seeded
      `["old-dep"]` surviving (clears nothing); `{"dependencies": null}` on frozen → 409;
      `{"status": "review"}` with no dependencies key on a frozen `in_progress` task → 200; story
      with only a pending version → 409 with "no current version" in `detail.detail` and
      `current_version: null`; frozen + illegal transition (`todo → done`, no dependencies key) →
      400 `INVALID_STATE_TRANSITION` with status still `todo` in persistence.

## TDD Cycle Evidence

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| RED (2.1) | 10 new contract cases (6 parametrized 422s + 4 frozen 409s) | `conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"` | **8 failed, 31 passed** (the 422s fail as 3 parametrized cases covering 6 assertions; frozen 409s fail as 200) |
| GREEN (2.2–2.4) | whole focused file | same command | **39 passed** |
| TRIANGULATE (2.5) | presence edges included in the batch | same command | **39 passed** |
| Wider gate | `tests/test_api` | `conda run -n storico python -m pytest tests/test_api -m "not integration"` | **363 passed** (350 at WU1 close + 13 new = 363 ✓) |
| Lint | `ruff check` + `ruff format --check` | `conda run -n storico python -m ruff check src tests && … format --check src tests` | **All checks passed; 253 files already formatted** |

## Files changed (backend half — 399 changed lines: 370+/29−)

- `backend/tests/test_api/test_tasks.py` (+314/−18) — 314 authored lines of the ≈420–520 unit
  forecast consumed; the unit's remaining budget belongs to the frontend tranches (2.6–2.9), which
  the forecast places at ≈100–200 lines.
- `backend/src/storico/api/routes/tasks.py` (+41/−7)
- `backend/src/storico/api/error_codes.py` (+7/−0)
- `backend/src/storico/api/schemas/task.py` (+8/−4)

Not committed, not staged, branch not switched — the parent lands the one atomic WU2 commit after
the frontend tranches. The pre-existing `odd/tasks/extraction-versioning-090.md` modification and the
untracked `backend/.gitignore` / `.claude/skills/` were present before this run and untouched.

## Deviations from design / task letter

1. **`TestUpdateTask::test_update_task` reconciled in RED** (same pattern as WU1's deviation 3): it
   PUT `{"title", "description", "status", "priority"}` and asserted 200 with the new values — the
   pre-matrix contract. Under the shrunk schema that body is a 422, so the REFACTOR gate could never
   go green with it as-is. It now PUTs `{"status": "in_progress"}` and asserts `title`,
   `description` and `priority` unchanged — the same "PUT updates the task" positive case under the
   field matrix. The removed-field refusals are pinned by the parametrized matrix case.
2. **Detail shape**: the design sketch writes `detail={"current_version": …, …}`; the second key is a
   `detail` string carrying the human-readable reason (developer-facing English), including the
   "no current version" sentence the 2.5 edge requires. `current_version` is the version number when
   a current version exists, `null` otherwise — exactly the design's conditional.
3. **Stale repo-root docs** (`spec-api-endpoints.md`, `spec-tasks-api-endpoints.md`) still describe
   `UpdateTaskRequest` with the removed fields. They are pre-existing generated references outside
   this unit's four edit surfaces; not touched, flagged here for the archive pass.

## Known cross-stack coupling (NOT this run's regression)

Adding `TASK_VERSION_FROZEN` makes `frontend/src/lib/__tests__/error-codes.test.ts` legitimately red
(registry 38 → 39, locale counts 43 → 44 missing copy in `en.json`/`es.json`). That is task 2.8's
job (T3 tranche) and was deliberately not touched. Additionally, until 2.7 lands,
`TaskEditor.tsx`/`lib/tasks-api.ts` still send `title`/`description`/`priority`, so every editor
save now 422s against this backend — the atomicity the `size:exception` exists for; the parent must
land the frontend tranches before the unit commit.

## Remaining unchecked tasks (exact lines from tasks.md)

- [ ] 2.6 RED (frontend) — `frontend/src/lib/__tests__/tasks-api.test.ts` and
- [ ] 2.7 GREEN (frontend) — `frontend/src/lib/tasks-api.ts`: `updateTask` narrows its accepted fields
- [ ] 2.8 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`:
- [ ] 2.9 TRIANGULATE (frontend) — `frontend/src/components/react/__tests__/TaskEditor.test.tsx`:
- [ ] 2.10 REFACTOR — rerun `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.
- [ ] 2.11 REFACTOR (frontend) — rerun

(Plus Phases 3–7: 64 further tasks pending.)

## Risks

- The backend now refuses the editor's current payloads (422) until 2.6–2.9 land; the unit is
  intentionally half-red cross-stack until then.
- `find_current_version` adds one statement to every `PUT /tasks/{id}` (~2s against the dev pooler);
  accepted by design (D21 tradeoff) — note the frozen check runs even for `status`-only bodies
  because `frozen` is computed before the presence guard. The design's code sketch computes
  `current`/`frozen` unconditionally before the guard, so this matches the design; a
  presence-conditional lookup would be a design change, not an optimization, and was not made.

---

# Apply Progress — WU2 corrective tranche T1b (presence-guarded frozen lookup) — 2026-09-30, branch `feat/extraction-versioning-api-wu2`

Corrective placement change on top of T1: pays the `find_current_version` lookup only when the body
carries the `dependencies` key. Belongs to task 2.3's implementation — **no new task ID was
invented**; tasks 2.1–2.5 stay `- [x]` exactly as T1 left them, and no checkbox was moved by this
tranche. WU2 T1 progress above is preserved verbatim.

## Structured status consumed

`gentle-ai.sdd-status` v2 for `extraction-versioning-api` from the parent: `nextRecommended: apply`,
`applyState: ready`, `blockedReasons: []`, `taskProgress` 13/77, `actionContext` mode `repo-local`,
workspaceRoot and `allowedEditRoots` `["/Users/alvaldes/Developer/storico"]`. Delivery path already
resolved (`size:exception` accepted for WU2). Edits stayed inside the three allowed surfaces
(`test_tasks.py`, `routes/tasks.py`, this progress file); no frontend, schema, registry or
membership-walk file was touched.

## Behavioural equivalence verified before coding

- The 409 requires `"dependencies" in body.model_fields_set`, so no payload without that key can
  observe the difference.
- With the lookup inside the presence guard, the raise still precedes the state-machine check: an
  illegal `status` plus a `dependencies` write on a frozen version still answers 409, not 400
  (pinned unmodified by T1's `test_a_mixed_body_on_a_frozen_version_answers_409_not_400`).
- `current is None` → frozen still answers 409 with the "no current version" detail, only on a
  dependencies write (pinned unmodified by T1's
  `test_a_story_with_no_completed_version_refuses_the_dependencies_write`).

## TDD Cycle Evidence

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| RED | `test_a_status_only_body_on_the_current_version_skips_the_frozen_lookup` + mirror `test_a_dependencies_write_still_reaches_the_frozen_lookup` | `conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"` | **1 failed, 40 passed** — the status-only case fails on the call counter (`calls == []` got 1 wasted lookup) while its 200/persistence assertions hold; the mirror passes (lookup runs exactly once, 409 fires) |
| GREEN | whole focused file | same command | **41 passed** |
| REFACTOR | wider `tests/test_api` | `conda run -n storico python -m pytest tests/test_api -m "not integration"` | **365 passed** (363 at T1 close + 2 new = 365 ✓) |
| Lint | `ruff check` + `ruff format --check` | `conda run -n storico python -m ruff check src tests && … format --check src tests` | **All checks passed; 253 files already formatted** (one transient F821 in the new tests — missing `UUID` import — fixed before the gate passed) |

The counter-based assertion is real, not vacuous: the RED run shows it failing against the
unconditional code with the captured wasted call. If the guard were removed **entirely** (lookup
deleted), the status-only case would still pass but the mirror case would fail with a 200 and an
empty counter — the pair pins the lookup to exactly the payloads that can use its verdict.

## Files changed (this tranche)

- `backend/src/storico/api/routes/tasks.py` — `find_current_version` resolution and `frozen`
  computation moved inside `if "dependencies" in body.model_fields_set:`; raise ordering and both
  `detail` variants byte-identical. No change to the schema, error registry, membership walk or
  state machine.
- `backend/tests/test_api/test_tasks.py` (+106/−0 plus one import widening to `from uuid import
  UUID, uuid4`) — two cases in `TestUpdateTaskFieldMatrix`; **no existing T1 case was edited**.

## Deviation note (design sketch vs implemented form)

`design.md`'s sketch (lines 152–153) computed the lookup unconditionally; the implemented form is
presence-guarded, which is what `design.md`'s Tradeoff paragraph (line 182) prices — "one extra
statement (`find_current_version`) before a dependency write, against a pooler where a statement is
~2s" — and its Why paragraph requires (a `MEMBER` keeping the board alive sends exactly
`{"status": …}`). Behavioural equivalence asserted by a call-count case. `design.md` was not
edited: the sketch is planning history and this record is where the next reader looks. This also
supersedes the third Risk bullet T1 recorded ("the frozen check runs even for `status`-only bodies
… matches the design"): that accepted cost no longer exists.

## Remaining unchecked tasks (unchanged by this tranche)

- [ ] 2.6 RED (frontend) — `frontend/src/lib/__tests__/tasks-api.test.ts` and
- [ ] 2.7 GREEN (frontend) — `frontend/src/lib/tasks-api.ts`: `updateTask` narrows its accepted fields
- [ ] 2.8 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`:
- [ ] 2.9 TRIANGULATE (frontend) — `frontend/src/components/react/__tests__/TaskEditor.test.tsx`:
- [ ] 2.10 REFACTOR — rerun `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.
- [ ] 2.11 REFACTOR (frontend) — rerun

(Plus Phases 3–7: 64 further tasks pending.)

## Risks

- None new. The backend halves of the 2.1–2.5 matrix pass unmodified; the cross-stack coupling T1
  recorded (frontend tranches 2.6–2.9 pending) is unchanged by this tranche.

## Tranche T2a — task 2.6 RED (frontend cases only, no production code changed)

Scope: WU2 frontend RED per the accepted `size:exception`; this tranche writes tests only. No
production file, no i18n file, no dependency, no install, no commit. Branch `feat/extraction-versioning-api-wu2`.

**Proof command (RED, run 2026-09-30):**

```
cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx src/lib/__tests__/tasks-api.test.ts
```

Real counts: **2 files failed; 6 failed / 36 passed of 42 total.**
Per file: `src/lib/__tests__/tasks-api.test.ts` → 22 tests, **1 failed**, 21 passed;
`src/components/react/__tests__/TaskEditor.test.tsx` → 20 tests, **5 failed**, 15 passed.

### New cases, what each pins, and how it fails today

`tasks-api.test.ts` — describe `updateTask — WU2 field matrix`:

- **RED** `never sends the removed fields (title, description, priority)` — pins that the PUT body
  carries no `title`/`description`/`priority` even when the caller passes the full legacy field set
  (cast through `Parameters<typeof tasksApi.updateTask>[1]` so the case keeps compiling after 2.7's
  signature shrink). Fails today: `updateTask` still does `toSnakeCase(fields)` and forwards all three.
- **Guard (passes today, pinned deliberately)** `sends only what the caller passes — no dependencies
  key grows on a status+labels save` — today `toSnakeCase` trivially satisfies it; the risk is that
  2.7's explicit body rebuild defaults a `dependencies: []` in. Note: the existing
  `can update only status` case already pins the status-only shape; this one adds `labels` to the mix.
- **Guard (passes today, pinned deliberately)** `forwards a dependencies key only when the caller
  passes one` — the same rebuild risk from the other side.

`TaskEditor.test.tsx` — describe `field policy and frozen seam` (all render an explicit `frozen`
prop — required in T2b's contract, so the WU3 seam stays visible at the call site):

- **RED** `renders title and description as read-only text, not editable controls` — no
  `textbox` role answers to Title/Description, and the content stays visible as text. Fails today:
  both render as editable `Input`/`Textarea`.
- **RED** `disables the dependencies control while frozen` — uses a task with **no** existing
  dependency so the select is genuinely enabled today via the empty-candidates rule; the only way
  this turns green is `frozen` gating the control. First draft used `mockTask` (which already
  depends on the sole sibling) and passed today for the wrong reason — caught and reworked before
  accepting the RED run.
- **RED** `omits the dependencies key from the save body while frozen` — payload has no
  `dependencies` key at all (never `[]`), so the editor can never trigger `TASK_VERSION_FROZEN`.
  Fails today: the editor always sends `dependencies`.
- **RED** `sends exactly the contract keys on a current-version save (frozen false)` — key set is
  exactly `[dependencies, labels, status]`. Fails today: `[dependencies, description, labels,
  status, title]`.
- **RED** `never blocks or warns on a status-only save of a frozen task` — save goes through, no
  failure banner, dialog closes. Fails today at the dependencies-key assertion.
- **Guard (passes today, pinned deliberately)** `renders no priority control at all (D21)` — the
  current editor has no priority control; the case is a regression guard against the control
  returning, since D21 keeps `priority` only in `TaskResponse` and the JSON export.

### Task 2.9 is half-done by design

The frozen edge of 2.9 is written here as failing cases (the last three TaskEditor cases above, plus
`disables … while frozen`). Its own proof is the **green rerun** of
`cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx`, which belongs to T2b —
so 2.9 stays unchecked in `tasks.md`. 2.6 is checked: its own completion criterion is RED cases
written and proven failing, which this run demonstrates.

### Finding for T2b

Existing `TaskEditor.test.tsx` renders (outside the new describe) omit the `frozen` prop; when T2b
makes it required, those calls will fail any typecheck while still running under vitest (no
typecheck in `pnpm test`). T2b should add `frozen={false}` to the existing renders in the same commit.
No dependency was installed and no file outside the two allowed test files was touched.

### Files changed (this tranche)

- `frontend/src/lib/__tests__/tasks-api.test.ts` — new describe block, 3 cases (1 RED, 2 guards).
- `frontend/src/components/react/__tests__/TaskEditor.test.tsx` — new describe block, 6 cases
  (5 RED, 1 guard).

## Remaining unchecked tasks (2.6 closed; 2.9 still open as designed)

- [ ] 2.7 GREEN (frontend) — `frontend/src/lib/tasks-api.ts`: `updateTask` narrows its accepted fields
- [ ] 2.8 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`:
- [ ] 2.9 TRIANGULATE (frontend) — `frontend/src/components/react/__tests__/TaskEditor.test.tsx`:
- [ ] 2.10 REFACTOR — rerun `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.
- [ ] 2.11 REFACTOR (frontend) — rerun

(Plus Phases 3–7: 64 further tasks pending; taskProgress now 14/77.)

## Risks (cumulative)

- Cross-stack coupling (T1): the suite is half-red by design until 2.7–2.9 land in T2b.
- New (T2a): `error-codes.test.ts` remains red on the registry count (38 → 39) until 2.8 — untouched here, as instructed.

---

# Apply Progress — WU2 tranche T2b (tasks 2.7 + 2.9: the frontend goes GREEN) — 2026-09-30, branch `feat/extraction-versioning-api-wu2`

Implements 2.7 (client + editor recut) and 2.9 (frozen-edge triangulation). T1/T1b/T2a progress above
is preserved verbatim. No backend file, no i18n file, no dependency, no install, no commit.

## Structured status consumed

`gentle-ai.sdd-status` v2 for `extraction-versioning-api` from the parent: `nextRecommended: apply`,
`applyState: ready`, `blockedReasons: []`, `taskProgress` 14/77, `actionContext` mode `repo-local`,
workspaceRoot and `allowedEditRoots` `["/Users/alvaldes/Developer/storico"]`. Delivery path already
resolved (owner's accepted `size:exception` for WU2). All edits stayed inside the four allowed
frontend files plus the two SDD artifacts.

## TDD Cycle Evidence

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| RED (T2a, before this tranche) | the six WU2 frontend cases | `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx src/lib/__tests__/tasks-api.test.ts` | **6 failed / 36 passed of 42** (recorded by T2a) |
| GREEN (2.7) | same two files after the implementation | same command | **41 passed / 1 failed of 42** — the 1 failure is the pre-existing `updates task fields via PUT` in the frozen `tasks-api.test.ts`, see "Blocked reconciliation" |
| TRIANGULATE (2.9) | `TaskEditor.test.tsx` alone | `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx` | **20 passed / 0 failed** — all five T2a frozen-edge cases green (no-`dependencies`-key while frozen, exact contract keys on a current save, status-only save of a frozen task never blocks or warns, dependencies disabled while frozen, read-only title/description) |
| Typecheck gate | whole frontend | `cd frontend && pnpm exec tsc --noEmit` | **exit 0, clean** |
| Full suite | `pnpm test` | `cd frontend && pnpm test` | **612 passed / 3 failed of 615** — 2 failures are the known task-2.8 coupling (`error-codes.test.ts`, registry 38 → 39 + missing `TASK_VERSION_FROZEN` locale copy), 1 is the blocked reconciliation below. `StoryDetail.test.tsx` and `KanbanBoard.test.tsx` green. |

## Completed tasks (persisted checkboxes updated in tasks.md)

- [x] 2.7 GREEN — `lib/tasks-api.ts`: `updateTask` now takes a `TaskUpdateFields` type
      (`status | labels | dependencies`) and builds the PUT body explicitly — a key reaches the body
      only when the caller passed it (`!== undefined`), so `dependencies` is never materialized as
      `[]`/`undefined`, and the removed legacy fields are discarded even if a caller still names
      them. The `toSnakeCase`/`toCamelCase` import (dead after the change) is gone. The loose
      `Record<string, unknown>` side of the intersection exists only so stale callers keep
      compiling — the frozen `tasks-api.test.ts` literal `{ title: 'X' }` (422-propagation case)
      and the store's `Partial<Task>` forward must both still typecheck, and this file is a
      no-edit surface this tranche. Documented in the type's docstring.
- [x] 2.7 GREEN — `TaskEditor.tsx`: `frozen` is a **required prop** (docstring names WU3's
      `is_current` computation); `title`/`description` render as read-only `<p>` text straight from
      `task` (no title/description state, no `Textarea` import, dead `title_required` validation
      removed); the dependencies select is `disabled={frozen || availableSiblings.length === 0}`
      and the dependency chips' remove buttons are `disabled={frozen}`; the save payload is built
      as `{ status, labels }` plus `dependencies` only when `!frozen`, so a frozen save can never
      trigger `TASK_VERSION_FROZEN`, while `status` and `labels` stay live in every state.
      `priority`: **no control existed before and none exists now** — see the declared no-op below.
- [x] 2.7 call site — `StoryDetail.tsx` passes `frozen={false}` explicitly, with a comment naming
      WU3 as the tranche that computes it from the version selector's `is_current`. No speculative
      source wired.
- [x] 2.9 TRIANGULATE — the frozen edge is green (table above); no new assertions were written,
      T2a's cases are the proof.

## The `priority` item in 2.7 is a declared no-op (plan-premise error)

Task 2.7's letter says "the `priority` control is removed". T2a measured the premise as wrong and
this tranche confirms it: `TaskEditor.tsx` never rendered a priority control (the only `priority`
occurrences in the file were the `Task` type's field and the removed title-state block's
comment-free code — no control, no state). Nothing was removed because there is nothing to remove.
`priority` remains in `TaskResponse` and the JSON export, exactly as the design says. The passing
T2a case `renders no priority control at all (D21)` is a **regression guard**, not new behaviour.

## New locale keys needed for the read-only recut

**None.** The read-only fields reuse the existing `taskEditor.title_label` / `description_label`
keys as their labels; no new copy was introduced and `en.json`/`es.json` were not touched (their
key sets remain identical). The dead `taskEditor.title_required` key stays in both locales —
removing it is a locale-file change this tranche is forbidden to make; flag for 2.8 or archive.

## Blocked reconciliation — one pre-existing case in a frozen file (NOT mine to edit)

`src/lib/__tests__/tasks-api.test.ts > updateTask > updates task fields via PUT` (a **pre-existing**
case, not one of T2a's) pins the old PUT body:

```ts
expect(api.put).toHaveBeenCalledWith('/api/v1/tasks/t1', {
  title: 'Updated',
  description: 'New desc',
  labels: ['fe'],
  dependencies: ['dep1'],
});
```

This is **directly contradictory** with T2a's frozen RED case `never sends the removed fields
(title, description, priority)`: no implementation can satisfy both. The parent's hard constraint
forbids me to touch `tasks-api.test.ts` at all, so I stopped rather than edit. The minimal
reconciliation (for the parent or an authorized follow-up) is to drop `title` and `description`
from both the call and the assertion in that one case, keeping `labels`/`dependencies`. Until it
lands, the proof runner reads **41 passed / 1 failed of 42** with that single known failure.

## Files changed (T2b only; the file diff vs HEAD also contains T2a's uncommitted RED block, ≈+120 lines of `TaskEditor.test.tsx`)

- `frontend/src/lib/tasks-api.ts` (+28/−14) — narrowed `TaskUpdateFields`, explicit body build, dead import removed.
- `frontend/src/components/react/TaskEditor.tsx` (+37/−39) — required `frozen`, read-only title/description, frozen-gated dependencies UI, narrowed payload.
- `frontend/src/components/react/StoryDetail.tsx` (+3/−0) — explicit `frozen={false}` + WU3 comment.
- `frontend/src/components/react/__tests__/TaskEditor.test.tsx` (vs HEAD +172/−34, of which T2b ≈+52/−30) — 12 render call sites gained `frozen={false}`; three pre-existing tests adapted (below).

### Deviation disclosure — three pre-existing TaskEditor tests adapted (beyond "call sites only")

The parent authorized call-site edits in this file and forbade touching T2a's assertions (none
were touched — all six RED cases are byte-identical). But three **pre-existing** tests exercised
the removed editable-title contract and could not pass under the recut their own assignment
mandates. Each was adapted minimally with its intent preserved, and each has a comment naming the
recut:

1. `shows the localized required-title error in Spanish…` → renamed `shows a localized validation
   error in Spanish, never the hardcoded English`: the title-required path is unreachable by
   design (title is read-only), so the same intent (localized message, no hardcoded English, store
   never called) is pinned on the reachable empty-label path ('La etiqueta no puede estar vacía').
2. `optimistically updates, applies server response, and closes on success`: no title typing; the
   payload assertion is now the narrowed `{ labels, dependencies, status }`; the server-response,
   rollback, `updatingTaskId` and dialog-close assertions are unchanged.
3. `resets form when dialog opens with a different task`: resets via a typed label instead of a
   typed title (read-only), asserting the label disappears and the new task's title shows as
   read-only text; the first dialog is unmounted before the rerender so the assertion sees only
   the new instance.

If the parent judges any of these adaptations out of bounds, the exact reversions are localized to
those three cases.

## Remaining unchecked tasks (exact lines from tasks.md)

- [ ] 2.8 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`:
- [ ] 2.10 REFACTOR — rerun `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.
- [ ] 2.11 REFACTOR (frontend) — rerun

(Plus Phases 3–7: 64 further tasks pending; taskProgress now 16/77.)

## Risks (cumulative)

- **Blocked reconciliation (new)**: the stale `updates task fields via PUT` case keeps the proof
  runner at 1 failed until the parent authorizes the one-case fix in `tasks-api.test.ts`. WU2's
  atomic commit should not land with it red.
- Known cross-stack coupling (T2a/T1): `error-codes.test.ts` remains red on the registry count
  (38 → 39) until 2.8 — untouched here, as instructed.
- The two legacy call shapes that still compile through `TaskUpdateFields`' record side (the
  frozen `{ title: 'X' }` case, the store's `Partial<Task>` forward) are silently narrowed at the
  body level; if a caller passes *only* removed fields, the PUT body is `{}` — legal per the
  backend's optional-field schema but a no-op worth knowing about.

## T2c — client type hole closed, stale PUT-body case reconciled (WU2)

Session preflight: WU2 under the owner's accepted `size:exception`; chain strategy
feature-branch-chain (stacks on PR #31); strict TDD active; native status consumed by the
parent (`nextRecommended: apply`, `applyState: ready`, 16/77, `blockedReasons: []`).

### Before/after counts per runner

| Runner | Before T2c | After T2c |
| --- | --- | --- |
| `pnpm test src/lib/__tests__/tasks-api.test.ts src/components/react/__tests__/TaskEditor.test.tsx` | 41/42 (1 failed: stale `updates task fields via PUT`) | **42/42** |
| `pnpm exec tsc --noEmit` | clean (permissive type hid the hole) | **clean** |
| `pnpm test` (full suite) | — | **613/615**; the only red is `error-codes.test.ts` (registry 38 → 39, task 2.8, known coupling — untouched here) |

TDD evidence (strict TDD): RED was measured before any edit — the proof runner read 41/42
with exactly one failure, the pre-existing stale case; the type gate's RED is structural
(narrowing the export makes the stale literals uncompilable, which is the contract WU2
enforces). GREEN: 42/42 + clean tsc after the three file edits. No new production behavior
was added, so no fresh RED test was required beyond the existing failing case.

### The type shape settled on, and where the narrowing lives

`frontend/src/lib/tasks-api.ts`:

```ts
export type TaskUpdateFields = {
  status?: TaskStatus;
  labels?: string[];
  dependencies?: string[];
};
```

The `& Record<string, unknown>` right side is **gone**. A caller that names `title`,
`description` or `priority` now fails to compile; the doc comment above the type states
that deliberate runtime-discard probes must admit the stale literal through a local cast,
never through a permissive export. The body construction in `updateTask` was already
presence-based (`!== undefined` per key) and is unchanged — presence is the write at every
layer.

The narrowing for the store's `Partial<Task>` forward lives in
`frontend/src/stores/taskStore.ts` (line ~434), as an explicit pick:

```ts
const writeFields: TaskUpdateFields = {};
if (updates.status !== undefined) writeFields.status = updates.status;
if (updates.labels !== undefined) writeFields.labels = updates.labels;
if (updates.dependencies !== undefined) writeFields.dependencies = updates.dependencies;
const serverTask = await api.updateTask(taskId, writeFields);
```

The store's public signature stays `Partial<Task>` (its optimistic merge still applies the
full partial), and no key the caller never passed is materialized — each key is picked in
only when the caller passed it. `lib/api.ts:238 updateTask` untouched, as instructed.

### The stale case's before/after

`frontend/src/lib/__tests__/tasks-api.test.ts`, case `updates task fields via PUT`:

- **Before**: call `{ title: 'Updated', description: 'New desc', labels: ['fe'],
  dependencies: ['dep1'] }`, asserted body carried all four keys — the superseded contract.
- **After**: call `{ labels: ['fe'], dependencies: ['dep1'] }` (contract fields only);
  asserted body is exactly `{ labels: ['fe'], dependencies: ['dep1'] }` — no `title`,
  `description` or `priority` anywhere. The mocked response and the `result.title`
  assertion are unchanged, so the case still proves the server shape maps through.

### T2a's six cases: unchanged — confirmed

The diff over this session touches exactly two cases in that file: the stale case above and
the 422-propagation case (below). The six WU2 field-matrix cases — `never sends the removed
fields`, `sends only what the caller passes`, `forwards a dependencies key only when the
caller passes one`, plus the three TaskEditor-side pins in `TaskEditor.test.tsx` — are
byte-identical. The legacy-fields case already carried the honest shape the parent asked
for: `as unknown as Parameters<typeof tasksApi.updateTask>[1]` on the stale literal, so no
edit was needed there; the strict production type and the deliberate cast now coexist
exactly as specified.

### Deviation to disclose (one case beyond the named two)

`updateTask propagates 422 validation error with status` (error-propagation describe,
~line 372) passed `{ title: 'X' }` as a bare literal, which does not compile under the
strict type — leaving it would have failed the `tsc --noEmit` CI gate the parent required
clean. The case is inside an allowed file but outside the two named cases, so this is
reported as a deviation rather than silently absorbed: the fix is the **same test-local
cast** the parent prescribed for the legacy-fields case
(`{ title: 'X' } as unknown as Parameters<typeof tasksApi.updateTask>[1]`) plus a comment
stating the type forbids it and the cast admits it deliberately. Zero semantic change: the
case still pins 422 propagation, not body shape. If the parent judges this out of bounds,
the exact reversion is one literal + one comment.

No forbidden file was touched: `TaskEditor.tsx`, `StoryDetail.tsx`,
`TaskEditor.test.tsx`, `lib/api.ts`, `error-codes.test.ts`, i18n JSON, backend files,
planning artifacts — all untouched. TaskEditor's observable body is unchanged (it always
passes `status` and `labels` explicitly, and `dependencies` only when unfrozen), and all
20/20 of its cases still pass. No call site forced a stop.

### Files changed (T2c only)

- `frontend/src/lib/tasks-api.ts` — strict `TaskUpdateFields`, truthful doc comment.
- `frontend/src/stores/taskStore.ts` — `TaskUpdateFields` type import + explicit
  presence-preserving pick at the `api.updateTask` call (6 lines + comment).
- `frontend/src/lib/__tests__/tasks-api.test.ts` — stale case reconciled; 422-case literal
  cast (disclosed deviation).
- `openspec/changes/extraction-versioning-api/apply-progress.md` — this section (append).

Tasks 2.7/2.9 were already `- [x]`; no checkbox change is warranted by T2c, and 2.8/2.10/2.11
stay `- [ ]`.

### Remaining unchecked tasks (exact lines from tasks.md)

- [ ] 2.8 GREEN (frontend mirror) — `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json`:
- [ ] 2.10 REFACTOR — rerun `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.
- [ ] 2.11 REFACTOR (frontend) — rerun

(Plus Phases 3–7: 64 further tasks pending; taskProgress remains 16/77 — T2c closes the
last open defect of tasks 2.7/2.9, it does not complete new tasks.)

### Risks (cumulative, superseding the T2b risk list where they overlap)

- Resolved this tranche: the stale-case red is gone (42/42), and both legacy call shapes
  the T2b risk list named — the frozen `{ title: 'X' }` test literal and the store's
  `Partial<Task>` forward — now go through deliberate casts / an explicit pick, not a
  permissive export.
- Known cross-stack coupling (unchanged): `error-codes.test.ts` red on the registry count
  (38 → 39) until 2.8.
- The store pick means a caller passing *only* removed fields still produces an empty PUT
  body `{}` (legal per the backend's optional-field schema, a no-op) — now visible at
  compile time nowhere, by design; only a cast can reach that state.

## T3 — task 2.8 GREEN: the locale mirror closes the unit's last red (WU2)

Task 2.8 is the GREEN step of the mirror: the backend registry gained
`TASK_VERSION_FROZEN` in T2 (measured: `error_codes.py.__all__` = 39 names), and
`error-codes.test.ts` was red on the registry count and on the missing key in both
locales until this tranche. No new production code preceded the failing tests — the
RED was already measured in the suite (parent: 613/615 with exactly these failures).

### Plan-premise correction (one constant moves, not two)

`tasks.md` 2.8 said "both locale counts `43` → `44`" as if the per-locale counts were
independent constants. The file's actual shape (measured before editing):
`EXPECTED_REGISTRY_COUNT = 38` at `error-codes.test.ts:66`, and the per-locale
expectation is **derived** as `EXPECTED_REGISTRY_COUNT + ROUTE_ERROR_CODES.length`
(lines ~120-125). So exactly **one** number moved — `38` → `39` — and both locale
counts followed by derivation. No second constant was invented to make the plan's
sentence literally true. The adjacent "Count note" comment's arithmetic
(`38 + 5 = 43 keys`) was updated to `39 + 5 = 44` with a note that WU2 added
`TASK_VERSION_FROZEN`, so the comment does not lie next to the constant it explains.

### The two strings added (verbatim), position convention

Inserted in both files directly after `TASK_DELETE_ENDPOINT_REMOVED`, matching the
registry's own alphabetical neighborhood (`TASK_DELETE_ENDPOINT_REMOVED`,
`TASK_VERSION_FROZEN`, `UNSUPPORTED_EXPORT_FORMAT`) and the family's two-sentence
shape: refusal explanation, then the way forward.

**en.json** — `errorCodes.TASK_VERSION_FROZEN`:

> Task dependencies can only be edited on the story's current version, and the version you are viewing has been superseded. Switch to the current version of the story to edit them.

**es.json** — `errorCodes.TASK_VERSION_FROZEN` (neutral international Spanish, tú):

> Las dependencias de una tarea solo se pueden editar en la versión actual de la historia, y la versión que estás viendo ya fue reemplazada. Cambia a la versión actual de la historia para editarlas.

Voseo check (ADR-008 list): no "Seleccioná/Revisá/Guardá/tenés/podés/sos/acá/dejalo/intentalo"
— verb forms present are `estás`, `fue reemplazada`, `Cambia`, all standard tú. The
sentence names the current-version requirement, states that the viewed version has
been superseded, and points to switching via the version selector path the user
actually took. The backend `detail` still carries the human sentence + `current_version`;
this is the headline only, as assigned.

### The recut needed no new label keys — confirmed

T2b's finding held: the read-only fields reuse existing labels, so `TASK_VERSION_FROZEN`
is the only key added. The "any read-only label the recut needs" clause of 2.8 is a no-op.

### `title_required` deleted from both locale files

Grep before deleting: `grep -rn title_required frontend/src` (including `.tsx` and test
files) — exactly two hits, the key's own definitions in `i18n/en.json:333` and
`i18n/es.json:333`. Zero references in any `.ts`/`.tsx`. It is copy for a title
validation that can no longer fire (title is read-only text under the D5/D21 matrix),
i.e. a UI lie. Deleted from both files in the same tranche so the key-parity test
stays green. Nothing was restored; `tsc --noEmit` confirms no typed translation
helper referenced it.

### Files changed (T3 only)

- `frontend/src/i18n/en.json` — `TASK_VERSION_FROZEN` added; `title_required` removed (net +1 key).
- `frontend/src/i18n/es.json` — same two changes (net +1 key).
- `frontend/src/lib/__tests__/error-codes.test.ts` — `EXPECTED_REGISTRY_COUNT` 38 → 39;
  count-note comment arithmetic updated (39 + 5 = 44, WU2 note). No other line changed;
  the locale expectations derive from the one constant, as predicted.
- `openspec/changes/extraction-versioning-api/tasks.md` — 2.8 → `- [x]`.
- `openspec/changes/extraction-versioning-api/apply-progress.md` — this section (append).

### Runner results (real counts)

- `pnpm test src/lib/__tests__/error-codes.test.ts src/i18n/__tests__/neutral-spanish.test.ts src/i18n/__tests__/no-duplicate-keys.test.ts` → **3 files / 23 tests passed**.
- `pnpm test` (full suite) → **54 files / 615 tests passed** — the unit's exit condition is met; zero failures.
- `pnpm exec tsc --noEmit` → clean.

### TDD Cycle Evidence

| Cycle | Task | RED | GREEN | TRIANGULATE | REFACTOR |
| --- | --- | --- | --- | --- | --- |
| mirror | 2.8 | Failing `error-codes.test.ts` (registry count 38 ≠ 39; missing key in both locales) — pre-existing, parent-measured 613/615 | Copy added in both locales + `EXPECTED_REGISTRY_COUNT` 39; gates 23/23, suite 615/615 | Count-pinning case already triangulates (exact length on registry and both locales); n/a | 2.10/2.11 are the parent's reruns, left unchecked |

### Remaining unchecked tasks (exact lines from tasks.md)

- [ ] 2.10 REFACTOR — rerun `cd backend && conda run -n storico python -m pytest tests/test_api -m "not integration"`.
- [ ] 2.11 REFACTOR (frontend) — rerun
      `cd frontend && pnpm test src/components/react/__tests__/TaskEditor.test.tsx src/lib/__tests__/tasks-api.test.ts src/components/react/__tests__/KanbanBoard.test.tsx`.

(Plus Phases 3–7 pending; taskProgress now 17/77.)

### Workload / PR boundary

T3 authored ≈ +10/−4 lines across three files (well inside the 400-line budget); WU2
remains under the owner's accepted `size:exception` as a whole work unit. Boundary
unchanged: WU2 frontend slice stacking on WU1 (PR #31) per `feature-branch-chain`.

### Structured status consumed

Native `gentle-ai.sdd-status` v2: `nextRecommended: apply`, `applyState: ready`,
16/77 complete, `blockedReasons: []`, `actionContext` repo-local with
`workspaceRoot`/`allowedEditRoots` = `/Users/alvaldes/Developer/storico`. All edits
inside allowed roots and the parent's three-file surface. 2.10/2.11 stay `- [ ]`
(parent's REFACTOR reruns).

---

## Parent close-out of WU2 (tasks 2.10 and 2.11 run by the orchestrator)

The two REFACTOR items are verification, not implementation, so the parent ran them
and marked them. Measured results, not reported ones:

| Gate | Command | Result |
| --- | --- | --- |
| 2.10 | `pytest tests/test_api -m "not integration"` | **365 passed** |
| Full backend unit suite | `pytest -m "not integration"` | **1066 passed, 33 deselected** (WU1 baseline was 1051 → +15 cases) |
| Lint | `ruff check src tests` | All checks passed |
| Format | `ruff format --check src tests` | 253 files already formatted |
| 2.11 | `pnpm test TaskEditor.test.tsx tasks-api.test.ts KanbanBoard.test.tsx` | **47 passed (3 files)** |
| Frontend suite | `pnpm test` | **615 passed (54 files)** |
| Typecheck | `pnpm exec tsc --noEmit` | clean (exit 0) |

### The workload number, measured against the accepted exception

`git diff --numstat` for the whole unit (base = WU1 branch tip):

| Half | Production code | Tests | Total |
| --- | --- | --- | --- |
| Backend | 62+/11− (73) | 401+/19− (420) | 493 |
| Frontend | 81+/56− (137) | 246+/42− (288) | 670 |
| **WU2** | **143+/67− = 210** | **647+/61− = 708** | **918** |

The owner's `size:exception` for WU2 was accepted against a forecast of **≈420–520
lines**. The unit is **918**. That is a 77% overrun of the number the decision was made
with, so it is surfaced rather than absorbed — and it is not a code problem: only 210
lines are production code, the other 708 are the field-matrix tests that make the
contract observable (16 new backend cases including the parametrized 422s and the
call-count guard, plus the editor/client cases). Splitting the PR is not available for
the usual reason: backend and client are atomic, and a backend-only half 422s every
editor save. Deleting tests to reach the number is forbidden by the harness rule the
plan itself records ("the budget constrains how work is sliced, never the code").

Writers' own intermediate tallies (~399 at T1, ~509 after T2b) were per-tranche and
excluded the frontend test volume; the 918 above is the unit total at close.

---

# Apply Progress — WU3 tranche W3-T1 (tasks 3.1, 3.3, 3.4: the current-version predicate) — 2026-09-30, branch `feat/extraction-versioning-api-wu3`

Closes D-a-5 item 2 at the repository layer: reads filter to the story's current version. WU1/WU2
progress above is preserved verbatim. One session interruption occurred after implementation but
before this report; the work tree was verified intact on resume (ports +22, repository +89/−4,
tests +164/−7) and the gate re-measured before closing.

## Structured status consumed

`gentle-ai.sdd-status` v2 for `extraction-versioning-api`: `nextRecommended: apply`, `applyState:
ready`, `taskProgress` 19/77 at start, `blockedReasons: []`, `actionContext` mode `repo-local`,
workspaceRoot and `allowedEditRoots` `["/Users/alvaldes/Developer/storico"]`. All edits stayed
inside the parent-authorized surfaces (the three tranche files plus the fixture-reconciliation
files explicitly authorized on resume: `tests/_helpers.py`, `tests/test_api/test_tasks.py`,
`tests/test_api/test_unfiltered_list_queries.py`) and the two SDD artifacts. Review Workload Gate:
WU3 ships as ONE PR under the owner's `size:exception` accepted 2026-09-30 for WU3 only (recorded
in `tasks.md`); WU5/WU6 keep their split.

## Completed tasks (persisted checkboxes updated in tasks.md)

- [x] 3.1 RED — new `TestCurrentVersionPredicate` in
      `backend/tests/test_repositories/test_task_repo.py`, six cases: story scope with v1+v2 both
      `completed` → only v2's 4 tasks and `total == 4`; a page past the end (`limit=2, offset=10`)
      → `([], 4)` — the filtered total via the fallback `count_stmt` path; workspace scope with a
      superseded story plus a plain story → 5 current tasks with `total == len(items)`;
      `workspace_ids` scope filtered too; explicit `extraction_id` reads exactly v1's 4 tasks (no
      currency predicate, so the selector can show a superseded version); and
      `list_current_by_workspace` (the export read) carries the predicate unpaginated.
- [x] 3.3 GREEN — `domain/ports/task_repository.py`: `list_page` gains
      `extraction_id: UUID | None = None` (defaulted, so existing callers keep compiling — routes
      wire it in 3.6), the docstring states the current-version predicate contract, and
      `list_current_by_workspace(workspace_id) -> list[Task]` is added to the port.
- [x] 3.4 GREEN — `infrastructure/database/repositories/task_repository.py`: all three predicate
      shapes implemented and **joined to the existing `scope` clause**, so `stmt` and `count_stmt`
      share one filtered question (details below) — plus `list_current_by_workspace`.

## Where the predicate is attached, per scope (the `scope`/`count_stmt` plumbing)

`list_page` builds one `scope` expression and applies the same object to `stmt` and to
`count_stmt`; `fetch_page` runs `count_stmt` only when a page falls past the end. Every predicate
below is composed **into `scope` before either statement is built**, so the window count
(`count(*) OVER ()`), the past-the-end fallback count, and the page rows are filtered together —
a page of 4 can never report 12.

| Scope | Predicate shape | Attachment point |
| --- | --- | --- |
| Story, no `extraction_id` | correlated scalar subquery: `extraction_id == select(ExtractionModel.id).where(user_story_id, status == COMPLETED).order_by(version_number.desc()).limit(1).scalar_subquery()` (the highest `completed` run; an empty subquery is NULL and matches nothing, so a story with no completed run reads no tasks) | `scope = and_(scope, subquery)` inside the `user_story_id` branch of `list_page`, before `stmt`/`count_stmt` are built |
| Story + explicit `extraction_id` | `scope = and_(scope, TaskModel.extraction_id == extraction_id)` — no currency predicate by design (reading a named version is the point) | same branch, same point |
| Workspace / `workspace_ids` | `NOT EXISTS` form via the new `_current_version_only(scope)` helper: `extraction_id == e.id AND e.status == completed AND NOT EXISTS(higher-numbered completed version of e.user_story_id)` — needs no `MAX`, served by `uq_extractions_story_version` | the helper wraps the base scope clause (`ProjectModel.workspace_id == …` / `.in_(…)`) before `stmt`/`count_stmt` are built; the same helper composes the clause for `list_current_by_workspace` |

Currency stays derived (`status = 'completed'` plus highest `version_number`) — no stored flag, no
trigger, no matview, no new column, per slice (a)'s decision. `extraction_id` without
`user_story_id` raises `ValueError` (the route-level 422 is task 3.6's job).

## TDD Cycle Evidence

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| RED (3.1) | the six `TestCurrentVersionPredicate` cases | `conda run -n storico python -m pytest tests/test_repositories/test_task_repo.py -m "not integration"` | **6 failed, 15 passed** (pre-existing cases in the file unaffected at RED) |
| GREEN (3.3+3.4) | whole focused file | same command | **21 passed** |
| Wider gate (first run) | `tests/test_api tests/test_repositories` | `conda run -n storico python -m pytest tests/test_api tests/test_repositories -m "not integration"` | **11 failed, 480 passed** — all eleven the pending-extraction fallout diagnosed below, none a predicate defect |
| Fixture reconciliation | helper + three call sites (authorized on resume) | same wider gate | **491 passed, 0 failed** |
| Lint | ruff check + format on all touched files | `conda run -n storico python -m ruff check src tests && conda run -n storico python -m ruff format --check src tests` | **All checks passed; 253 files already formatted** (the format gate the interrupted run left pending is now closed) |

## Fixture reconciliation (what changed and why `seed_extraction`'s default did not)

The 11 fallout cases all seeded tasks hanging off a **pending** extraction — a state the domain
does not really allow a task to be read from, since a task is the output of a completed run. No
assertion was weakened or deleted; every fix seeds realism:

1. **`tests/_helpers.py` — `seed_task`**: when it mints its own extraction (`extraction is None`
   branch) it now mints it `status=COMPLETED` with `completed_at`. This closed 3 of the 11 in one
   place (`test_list_tasks`, `test_list_tasks_by_story`,
   `test_tasks_span_the_requested_workspaces_only`). **`seed_extraction`'s default is untouched** —
   tests that need a pending/failed run on purpose mint it explicitly, and changing the default
   would have moved the ground under tests that assert on non-terminal runs.
2. **`tests/test_api/test_tasks.py`** (call sites the helper alone cannot reach, because N tasks on
   one story each minting their own version would leave only the highest visible):
   `_seed_tasks` mints **one** completed version before the loop and attaches every task to it; the
   two inline pagination tests (`?page=1&size=2` totals) mint one completed version per story
   (`version_a`, `version_b`).
3. **`tests/test_api/test_unfiltered_list_queries.py`**: its `_seed` seeds its own extraction and
   passes it to `seed_task`, so that call site completes the extraction (`status=COMPLETED` +
   `completed_at`); the pinned row counts (one task, one extraction per workspace) are unchanged.

## Files changed (this tranche)

- `backend/src/storico/domain/ports/task_repository.py` (+22/−0) — `extraction_id` param +
  predicate contract docstring + `list_current_by_workspace`.
- `backend/src/storico/infrastructure/database/repositories/task_repository.py` (+89/−4) —
  `_current_version_only` helper, three scope arms, `list_current_by_workspace`.
- `backend/tests/test_repositories/test_task_repo.py` (+164/−7) — the six RED cases; four
  pre-existing `list_page` tests in the file re-anchored onto a completed version (disclosed; each
  keeps its original assertions — totals, paging arithmetic, scope exclusion — and only the seeding
  gained realism).
- `backend/tests/_helpers.py` (+14/−2) — the helper fix above.
- `backend/tests/test_api/test_tasks.py` (+46/−8) — call-site realism fixes above.
- `backend/tests/test_api/test_unfiltered_list_queries.py` (+12/−1) — call-site realism fix above.

Tranche total ≈ 347 changed lines (including the authorized reconciliation files), inside the WU3
single-PR exception. Not committed, not staged, branch not switched.

## Deviations / disclosed judgment calls

1. **Four pre-existing tests in `test_task_repo.py` re-anchored** (`test_list_page_by_story_…`,
   `test_list_page_mid_page_…`, `test_list_page_past_the_end_…`,
   `test_list_page_by_workspace_…`): each pinned list_page mechanics over tasks that the new
   predicate makes invisible (pending extractions). Their assertions are byte-identical; only the
   seeding attaches tasks to a completed version. Reported, not quiet.
2. **`extraction_id` without `user_story_id` raises `ValueError` in the repository** (port
   docstring states it); the route-level 422 `REQUEST_VALIDATION_FAILED` is task 3.6's surface.
3. `list_by_story` and `list_by_workspace` (unpaginated) remain unfiltered — per the design, the
   unpaginated workspace read is superseded by `list_current_by_workspace` at the route (task 3.7),
   and task 3.12 confirms `list_by_workspace`'s remaining callers.

## Known fallout — closed under explicit authorization (11 cases)

All eleven were "task seeded on a pending extraction, then read through a version-aware list":
`test_tasks.py` `TestListTasks::test_list_tasks`, `::test_list_tasks_by_story` and seven
`TestListTasksPagination` cases (totals of 2–3 read as 0–1); `test_unfiltered_list_queries[tasks]`
(total 0 vs 3); `test_list_by_workspaces.py::test_tasks_span_the_requested_workspaces_only`
(total 0 vs 2). The SQL itself was already correct on the first gate run (HTTP 200s, statement
counts intact) — the fixtures described an impossible state. Closed by the reconciliation above;
the wider gate is green.

## Remaining unchecked tasks (exact lines from tasks.md)

- [ ] 3.2 RED — `backend/tests/test_repositories/test_extraction_repo.py`: `list_versions(story_id)`
- [ ] 3.5–3.12 — the selector read, route wiring, schemas, export filter, triangulation and refactor
      (Phase 3's other eight tasks).

(Plus Phases 4–7. Phase 3 has 3.1, 3.3, 3.4 checked — nothing else.)

## Risks

- None new in the repository. `find_by_id` (single-task reads) is deliberately unfiltered — the
  frozen-check and the editor read individual tasks by id, and gating those is the API layer's job.
- The statement-shape guards (`test_unfiltered_list_queries.py`, `test_list_page_pins_the_order_
  rule_in_sql`) still pass: the predicate rides the existing statement, no statement was added.
- The export route still reads the unfiltered `list_by_workspace` until task 3.7 swaps it to
  `list_current_by_workspace` — the predicate exists but is not yet reachable over HTTP for
  exports.

---

## W3-T2 — `list_versions` at the extraction repository (tasks 3.2, 3.5) — 2026-09-30

Strict TDD, one cycle. The section above (W3-T1) is preserved verbatim; its "Remaining unchecked
tasks" list is superseded by this section for 3.2 only.

### Completed tasks (persisted checkbox evidence)

- 3.2 RED and 3.5 GREEN are checked in `tasks.md`; no other line was touched.
- Re-read after checking: lines 342 and 355 carry `- [x]`; every other Phase 3 line is still `- [ ]`.

### TDD Cycle Evidence

| Cycle | Task | Command | Result |
|-------|------|---------|--------|
| RED | 3.2 | `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_extraction_repo.py -m "not integration"` | **2 failed, 24 passed** — both new cases fail with `AttributeError: 'SQLAlchemyExtractionRepository' object has no attribute 'list_versions'` |
| GREEN | 3.5 | same focused command | **26 passed** |
| GREEN (wider) | 3.5 | `cd backend && conda run -n storico python -m pytest tests/test_repositories -m "not integration"` | **128 passed** |
| GREEN (full unit suite) | — | `cd backend && conda run -n storico python -m pytest -m "not integration"` | **1074 passed, 33 deselected** (40.09s) |
| REFACTOR | — | `conda run -n storico python -m ruff check src tests` and `python -m ruff format --check src tests` | **All checks passed; 253 files already formatted** |

No production code existed before the RED run (strict TDD order held). TRIANGULATE for this slice is
task 3.10/3.11 (API layer), not this tranche; no separate triangulation was due here.

### What was implemented

- `list_versions(user_story_id) -> list[Extraction]` on the port
  (`domain/ports/extraction_repository.py`) and the adapter
  (`infrastructure/database/repositories/extraction_repository.py`): one `select(ExtractionModel)`
  filtered by `user_story_id`, ordered `version_number DESC` in SQL, mapped through the existing
  `self._to_domain`, deliberately with no `limit`/`offset` parameters and no `fetch_page` call. No
  new imports were required in either file.
- Two tests in `tests/test_repositories/test_extraction_repo.py`, in the file's existing
  versioning-section seeding style (`_versioned` + `create_next_version` + targeted marks, and the
  statement-capture listener pattern of `test_list_page_pins_the_order_rule_in_sql`):
  1. `test_list_versions_returns_every_version_newest_first_with_no_page_window` — four versions on
     one story (v1/v2 completed, v3 failed, v4 pending) plus one completed version on a second
     story; asserts all four come back ordered 4→3→2→1 with the pending and failed runs present,
     the other story's run absent, and — on the statement the database received — exactly one
     query, `ORDER BY extractions.version_number DESC`, and **no `LIMIT` at all**.
  2. `test_find_current_version_agrees_with_list_versions_first_completed` — three versions
     (completed, failed, completed); asserts `find_current_version`'s id and `version_number`
     equal the first `completed` entry of `list_versions` (v3).

### Docstring wording choice for "why unbounded"

Both docstrings say (port and adapter, same sentence family): *"Deliberately unbounded: the version
list is the pagination *input* for the version selector, not a paginated resource, and the
paginator's 20/100 window would truncate a long history silently — exactly the failure this read
exists to avoid. A story's version count is bounded by hand-run extractions, so no window is
applied here, and a `pending` or `failed` run is part of the history the user must see, never
filtered out."* The "pagination *input*, not a paginated resource" phrasing is the design
settlement's own framing (design.md, selector decision); the "20/100 window" names the concrete
numbers the paginator would have imposed.

### How agreement was pinned while `find_current_version` stays a `LIMIT 1` query

- The pin is test 2 above: for a three-version story, `find_current_version` must return the same
  row (id equality, not just number equality) as the first `completed` entry of `list_versions`.
  Both docstrings state what that guarantees: the board asks `find_current_version` on every task
  write (the frozen check) and the selector derives `is_current` from the list; if the two ever
  diverged, the board and the selector would disagree about which version is live.
- `find_current_version` was **not touched** — its statement is still the `LIMIT 1` highest-
  completed query from slice (a). The docstrings of the new method explicitly forbid the
  "unification" of loading the list and filtering in Python, on the hot-path ground recorded in the
  parent prompt. No production code paths were changed beyond the one added method.

### Full-suite number and the delta against the parent's quoted 1080

- Measured by the parent after this tranche: **1074 passed, 33 deselected** (re-run to confirm, and
  matching the child's own run and `--collect-only` recount).
- **Resolved by the parent: the 1080 was never a measurement.** It was a projection the parent wrote
  into the W3-T2 prompt without running the suite first, and the child was right to dispute it rather
  than absorb it. The arithmetic that does reproduce reality: WU2's green head measured **1066**, W3-T1
  added **6** test functions and W3-T2 added **2** — 1066 + 6 + 2 = **1074**, exactly what the worktree
  reports. There is no unexplained delta anywhere in this unit.
- My tranche adds exactly 2 tests, so the pre-existing count in the current worktree is 1072.
- The gap predates W3-T2 and is inside W3-T1's uncommitted work: the whole uncommitted tests/ diff
  adds exactly 8 test functions over HEAD (6 from W3-T1, 2 from W3-T2), and
  `git diff tests/ | grep '^-'` over `test_extraction_repo.py` shows **zero** removed test
  functions or assertions. I removed nothing and weakened nothing.
  > Rule this closes: a parent quotes a number it ran, or says "unmeasured". A child that finds a
  > quoted baseline irreproducible should do exactly what happened here — measure collection twice and
  > report — not assume its own work broke something.

### Deviations from the letter of the task (disclosed, none silent)

1. `test_the_port_exposes_no_delete_and_no_whole_row_writer` pins the port's exact abstract-method
   set, so task 3.5's sanctioned addition of `list_versions` required adding the name to that pinned
   set (and one docstring sentence recording it as the design's sanctioned widening, not a silent
   one). This is a surface pin tracking a sanctioned surface change, not a weakened assertion; the
   `delete`/`save` prohibitions in the same test are untouched and still pass.
2. The parent's assignment described seeding via "the file's existing seeding style"; the
   versioning section's style (`create_next_version` + marks) was used rather than the paging
   section's `_seed_extraction` helper, because `list_versions` is a versioning read and that is the
   section that already seeds pending/failed/completed states.

### Remaining unchecked tasks (exact next lines from tasks.md)

- [ ] 3.6 GREEN — `backend/src/storico/api/routes/tasks.py`: `extraction_id` parameter on `list_tasks`
- [ ] 3.7 GREEN — `backend/src/storico/api/routes/export.py`: export serializes `list_current_by_workspace`
- [ ] 3.8 GREEN — `StoryVersionResponse` + the three response scalars
- (then 3.9, 3.10, 3.11, 3.12; Phases 4–7 unchanged)

### Workload / PR boundary

WU3 ships as ONE PR under the owner-accepted `size:exception` (2026-09-30, recorded in tasks.md).
This tranche's authored diff: ~+145 lines across the three allowed files (2 tests ≈ +124 with
docstrings, port method ≈ +22, adapter method ≈ +26, minus shared context) — within the tranche
estimate; the PR boundary stays WU3-whole per the accepted exception.

---

# Apply Progress — WU3 tranche W3-T3 (tasks 3.6, 3.7, and the 3.11 export cases) — 2026-09-30, branch `feat/extraction-versioning-api-wu3`

Wires the `extraction_id` read into `GET /api/v1/tasks/` and moves the export onto the filtered
statement. W3-T1 (task repository current-version predicate) and W3-T2 (`list_versions`) remain in
the worktree uncommitted and untouched; every earlier section above is preserved verbatim.

## Structured status consumed

`gentle-ai.sdd-status` v2 for `extraction-versioning-api` from the parent: `nextRecommended: apply`,
`applyState: ready`, `blockedReasons: []`, `taskProgress` 24/77, `actionContext` mode `repo-local`,
workspaceRoot and `allowedEditRoots` `["/Users/alvaldes/Developer/storico"]`. Delivery path already
resolved: **`size:exception` explicitly accepted by the owner on 2026-09-30 for WU3 only** (one PR
over budget, recorded in tasks.md). All edits stayed inside the four allowed files plus the two SDD
artifacts.

## Completed tasks (persisted checkboxes updated in tasks.md as each closed)

- [x] 3.6 GREEN — `routes/tasks.py`: `list_tasks` gains `extraction_id: UUID | None` and the
      `ExtractionRepoDep`. The shape refusal (`extraction_id` without `user_story_id`) is raised at
      the **top of the handler, before every branch** — see ordering below. The story branch, after
      the unchanged `require_story_workspace_access` walk, resolves
      `extraction_repo.find_by_id(extraction_id)` and refuses `None` or a foreign
      (`version.user_story_id != user_story_id`) with 422 `REQUEST_VALIDATION_FAILED`, then passes
      `extraction_id` into `list_page`. The workspace and unfiltered branches keep their existing
      membership refusals byte-for-byte: WU1's 410 handlers, WU2's presence-guarded frozen check,
      and the state machine are untouched.
- [x] 3.7 GREEN — `routes/export.py`: `export_tasks` serializes
      `repo.list_current_by_workspace(workspace.id)` instead of `list_by_workspace`, so the
      current-version predicate rides the serializing statement; docstring states the filter.
- [x] 3.11 TRIANGULATE — `tests/test_api/test_export.py`: new `TestExportCurrentVersionFilter` —
      JSON and Markdown exports of a story whose v1 (2 tasks) and v2 (4 tasks) are both `completed`
      contain exactly v2's 4 tasks and no v1 title; a story whose only run is `failed` (with a task
      seeded on the failed version, so the assertion proves the filter and not mere absence)
      contributes nothing in both formats while the file stays valid (JSON parses; Markdown keeps
      `# Tasks Export` and the healthy story's section).

## The 422-before-repository ordering (the seam the parent flagged)

The refusal for `extraction_id` without `user_story_id` sits at the top of `list_tasks`, before the
workspace/story/unfiltered branch dispatch and therefore before any repository call — including the
`member_repo` walk. The proof is structural: `task_repository.list_page` raises `ValueError` for
that same shape, and a `ValueError` escaping to the framework falls to the generic 500 handler; a
422 carrying `REQUEST_VALIDATION_FAILED` on **both** the workspace branch (`?workspace_id=…&extraction_id=…`)
and the unfiltered branch (`?extraction_id=…`) can only come from the route's own guard. Pinned by
`test_extraction_id_without_user_story_id_refuses_before_the_repository`.

The story-branch 422 for a foreign/nonexistent version fires **after** the membership walk (the
design's ordering: membership → `find_by_id(X)` → refuse → `list_page`), and its body discloses
nothing about the foreign story (asserted: neither its id nor a task title appears in the response).

## RED evidence (real counts)

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| RED (3.10 partial + 3.11) | the 5 new `TestListTasksVersionReads` cases + 3 new `TestExportCurrentVersionFilter` cases | `conda run -n storico python -m pytest tests/test_api/test_tasks.py::TestListTasksVersionReads tests/test_api/test_export.py::TestExportCurrentVersionFilter -m "not integration"` | **7 failed, 1 passed** — the foreign-refusal, unknown-refusal, 422-before-repository and superseded-version cases fail against the unwired route; the failed-only-story read already passes because W3-T1's repository predicate rides through `list_page` (route-level triangulation guard, not a new behaviour); all 3 export cases fail with the unfiltered `list_by_workspace` |
| GREEN (3.6 + 3.7) | both focused files | `conda run -n storico python -m pytest tests/test_api/test_tasks.py tests/test_api/test_export.py -m "not integration"` | **4 failed, 54 passed** → after the fixture reconciliation below, **58 passed** |
| Wider gate | `tests/test_api` | `conda run -n storico python -m pytest tests/test_api -m "not integration"` | **373 passed** (365 at W3-T2 close + 8 new = 373 ✓) |
| Full suite | everything | `conda run -n storico python -m pytest -m "not integration"` | **1082 passed, 33 deselected** — the parent's 1074 + exactly the 8 new cases |
| Lint | `ruff check` + `ruff format --check` | `conda run -n storico python -m ruff check src tests && … format --check src tests` | **All checks passed; 253 files already formatted** (two files reformatted by `ruff format` before the gate passed) |

## What still calls the unfiltered `list_by_workspace`

In `routes/export.py`, exactly one `list_by_workspace` call remains after 3.7:
`story_repo.list_by_workspace(workspace.id)` in the Markdown branch. That is the **story**
repository's own method, fetching the stories whose `raw_text` becomes the section headers — not the
task read, and not the unfiltered task statement this task retires. It was left as-is rather than
silently swapped. `task_repository.list_by_workspace` itself still serves its remaining callers
(3.12's confirmation belongs to W3-T4).

## Deviations from design / task letter

1. **Four pre-existing `TestExportTasks` cases reconciled (reported by name, intent preserved).**
   `test_export_json`, `test_export_markdown`, `test_export_json_tasks_have_all_fields` and
   `test_export_markdown_labels_and_deps` seeded their tasks on an extraction minted with
   `seed_extraction(db_session, story_id)` and no `status` — i.e. a **pending** run. Under the
   unfiltered export that was invisible; under the current-version export those tasks are
   correctly absent, so all four failed for fixture reasons, not contract reasons. The fixture now
   mints a `completed` extraction (`status=ExtractionStatus.COMPLETED, completed_at=…`) in
   `_create_tasks` and in `test_export_markdown_labels_and_deps`, with a comment naming the
   reconciliation. Each case still proves what it was written to prove: content-type, filename
   header, JSON field shape, Markdown section rendering, dependency resolution to titles. This is
   the same fixture reconciliation pattern W3-T1 applied to `test_tasks.py`; no assertion was
   weakened or deleted.
2. **The route's shape refusal precedes the membership walk.** The design's Data Flow names the
   ordering for the story branch only (membership → version resolution); for
   `extraction_id`-without-`user_story_id` it is silent. Raising the 422 at the top of the handler
   (before branch dispatch) is the only placement that guarantees no repository call ever sees the
   invalid shape on **any** branch, including `workspace_id`. A malformed query answering 422
   discloses nothing about any workspace, so the non-member case is unaffected in information terms.

## Files changed (this tranche; diff vs HEAD, which also carries W3-T1's uncommitted fixture work in test_tasks.py)

- `backend/src/storico/api/routes/tasks.py` (+44/−6 vs HEAD, all this tranche) — the parameter, the
  shape guard, the version resolution and refusal, the `extraction_id` pass-through, docstring.
- `backend/src/storico/api/routes/export.py` (+5/−2) — the filtered read + docstring sentence.
- `backend/tests/test_api/test_tasks.py` (+182/−8 vs HEAD, of which this tranche ≈ +160: the
  `TestListTasksVersionReads` class, 5 cases; the remainder is W3-T1's uncommitted fixture
  reconciliation, untouched)
- `backend/tests/test_api/test_export.py` (+142/−3) — `TestExportCurrentVersionFilter`, 3 cases,
  plus the two fixture reconciliations above and the `seed_task`/`datetime`/`ExtractionStatus`
  imports they need.

Tranche authored total ≈ 355 changed lines. Within the owner-accepted WU3 `size:exception` (one PR
over the 400-line budget); not generalized to WU5/WU6.

## Workload / PR boundary

WU3 ships as ONE PR under the accepted `size:exception`. Remaining WU3 work: 3.8, 3.9, 3.10's
`test_stories.py`/`test_unfiltered_list_queries.py` halves (W3-T4/T5), 3.12 refactor rerun.

## Remaining unchecked tasks (exact lines from tasks.md; 3.10 confirmed still unchecked)

- [ ] 3.8 GREEN — `backend/src/storico/api/schemas/story.py`: add `StoryVersionResponse` with `id`,
- [ ] 3.9 GREEN — `backend/src/storico/api/routes/stories.py`: add `GET /{story_id}/versions` using
- [ ] 3.10 TRIANGULATE — `backend/tests/test_api/test_tasks.py` (`extraction_id` from another story
- [ ] 3.12 REFACTOR — `backend/src/storico/infrastructure/database/repositories/task_repository.py`:

(3.10's tasks.py half landed with this tranche; its stories/unfiltered halves stay with W3-T4/T5,
so the checkbox stays unchecked as instructed. Phases 4–7 unchanged.)

## Risks

- The shape 422 fires before membership validation, so a non-member sending
  `?extraction_id=…` gets 422 rather than 403 — a deliberate ordering choice
  (see deviations), disclosed rather than absorbed.
- `list_tasks` now resolves the version with one `find_by_id` statement only when `extraction_id`
  is supplied; the default story read pays no extra statement (the current-version predicate lives
  in the repository's own query).

---

# Apply Progress — WU3 tranche W3-T4 (tasks 3.8, 3.9: the selector response schema and the `GET /stories/{id}/versions` read) — 2026-09-30, branch `feat/extraction-versioning-api-wu3`

The version-selector read the frontend consumes in Phase 6. W3-T1 (task-repo current-version
predicate), W3-T2 (`list_versions`) and W3-T3 (`extraction_id` read + export filter) remain in the
worktree uncommitted and untouched; every earlier section above is preserved verbatim. Task 3.10
and 3.12 stay unchecked as instructed.

## Structured status consumed

`gentle-ai.sdd-status` v2 for `extraction-versioning-api` from the parent: `nextRecommended: apply`,
`applyState: ready`, `blockedReasons: []`, `taskProgress` 27/77, `actionContext` mode `repo-local`,
workspaceRoot and `allowedEditRoots` `["/Users/alvaldes/Developer/storico"]`. Delivery path already
resolved: **`size:exception` explicitly accepted by the owner on 2026-09-30 for WU3 only** (one PR
over the 400-line budget, recorded in tasks.md). All edits stayed inside the allowed surfaces plus
the companion edits disclosed below; no frontend file, no repository/port file, no error-code file
and no i18n file was touched.

## Completed tasks (persisted checkboxes updated in tasks.md as each closed)

- [x] 3.8 GREEN — `api/schemas/story.py`: new `StoryVersionResponse` with **exactly** `id`,
      `version_number`, `status` (ExtractionStatus), `model_used`, `provider`, `temperature`,
      `created_at`, `completed_at` (nullable), `error_info` (nullable, default `None`),
      `is_current`, `has_output` — `from_attributes=True` like the other response schemas.
      `api/schemas/extraction.py`: `ExtractionResponse` **and** `ExtractResponse` gain
      `version_number: int | None`, `provider: str`, `temperature: float` — all three **required
      keys** on the contract (`version_number` nullable; `None` only on the pre-0028 shape), so
      every construction site must pass what the row actually carries.
- [x] 3.9 GREEN — `api/routes/stories.py`: `GET /{story_id}/versions` added. The unchanged
      `require_story_workspace_access` walk runs first (404 missing story / 403
      `NOT_A_WORKSPACE_MEMBER`, no membership-hiding flag, never a silent empty 200), then
      `extraction_repo.list_versions(story_id)` (the W3-T2 unbounded `version_number DESC` read),
      and each entry is decorated with the two derived booleans: `is_current` = the entry is the
      first `completed` element of the ordered list (implemented as `v.id == current_id` where
      `current_id` is that first completed entry's id — equivalent because ids are unique per
      version), `has_output` = `status == completed`. A story with no completed version yields a
      200 array with **no** `is_current` entry — the legal frozen state. Returned as a bare
      unpaginated array (`-> list[StoryVersionResponse]`), never a `PaginatedResponse` — wrapping
      it would be the truncation W3-T2's docstring forbids. The route declares its own
      `ExtractionRepoDep = Annotated[...]` next to the file's existing `StoryRepoDep`/
      `ProjectRepoDep`/`MemberRepoDep`, per the repo's per-module dependency convention. Existing
      routes were not reordered (`/{story_id}` matches one segment; `/{story_id}/versions` cannot
      be shadowed).

## TDD Cycle Evidence (strict TDD)

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| RED (3.9's own proof) | 2 new `TestStoryVersionsEndpoint` cases in `tests/test_api/test_stories.py` | `conda run -n storico python -m pytest tests/test_api/test_stories.py -m "not integration"` | **2 failed, 21 passed** — both fail 404, the route does not exist |
| Companion-forcing proof | existing extraction + contract files, schemas widened but routes not yet passing the scalars | `conda run -n storico python -m pytest tests/test_api/test_extraction.py tests/contract/test_api_schemas.py -m "not integration"` | **17 failed, 58 passed** — the required scalars make every hand-built `ExtractionResponse(...)`/`ExtractResponse(...)` site raise (ValidationError → 500). This is the mechanical proof the companion edits were forced |
| GREEN (3.8 + 3.9 + companions) | stories + extraction + contract files | `conda run -n storico python -m pytest tests/test_api/test_stories.py tests/test_api/test_extraction.py tests/contract/test_api_schemas.py -m "not integration"` | **98 passed** |
| Wider gate | `tests/test_api tests/contract tests/test_repositories` | `conda run -n storico python -m pytest tests/test_api tests/contract tests/test_repositories -m "not integration"` | **547 passed** |
| Full suite | everything | `conda run -n storico python -m pytest -m "not integration"` | **1084 passed, 33 deselected** — the parent's 1082 + exactly the 2 new test functions; no other delta |
| Lint | ruff | `conda run -n storico python -m ruff check src tests && … format --check src tests` | **All checks passed; 253 files already formatted** |

The two 3.9-proof cases (kept deliberately inside 3.9's own GREEN proof; 3.10's stories
triangulation edges stay for the next tranche):

1. `test_lists_every_version_newest_first_and_derives_the_flags` — v1/v2 completed, v3 pending:
   bare array ordered `[3, 2, 1]`; exactly v2 is `is_current` (the first *completed* entry — the
   case distinguishes that rule from "the highest entry", since v3 is highest but pending);
   `has_output` `[False, True, True]`; every entry carries the exact 11-key set; the pending entry
   has `completed_at: null`.
2. `test_a_story_with_no_completed_version_has_no_current_entry` — a story whose only run failed:
   200 single-entry array, `is_current` false, `has_output` false. (The failed entry's full field
   disclosure — `status`, `error_info`, `model_used`, `provider`, `temperature` — is 3.10's edge,
   not asserted here.)

## The OpenAPI surface the new route adds

`GET /api/v1/stories/{story_id}/versions`, one method, 200 response
`{"type": "array", "items": {"$ref": "#/components/schemas/StoryVersionResponse"}}`. Verified
against the live `app.openapi()`: `StoryVersionResponse` carries exactly the 11 properties above,
with `required: [id, version_number, status, model_used, provider, temperature, created_at,
completed_at, is_current, has_output]` (`error_info` nullable with default). The widening is also
visible on the existing 202 and extraction reads: `ExtractResponse` and `ExtractionResponse`
declare `version_number` (`anyOf [integer, null]`), `provider` (string) and `temperature`
(number), all three in each schema's `required` list.

## The `routes/extraction.py` companion edit, and the three beyond it (disclosed, none silent)

Task 3.8's sanctioned companion: `ExtractResponse(...)` is constructed literally at
`routes/extraction.py:268`, so widening that schema forced the call site to pass the three values.
It now passes `version_number=pending.version_number` (the number `create_next_version` minted and
returned — the entity is its only source), `provider=provider` and
`temperature=resolved_temperature` — exactly what the just-created extraction has, with the
background run handed the same resolved values. The handler was not restructured.

**Three further companion edits were mechanically forced and are disclosed as the tranche's
deviation.** The parent's premise that "`ExtractionResponse` uses `from_attributes=True`, so
adding the fields is enough for the reads that build it from the entity" does not hold for this
repo: `from_attributes` is set on the schema but all four reads build it **by hand**, and the
required scalars made them raise. Measured RED: 17 existing tests failed on the widened schema
alone (table above). The sites, each passing the entity's own values, nothing else changed:

- `routes/extraction.py:304` (`extraction_status`) — `version_number`/`provider`/`temperature`
  from the loaded extraction.
- `routes/extractions.py:143` (the `list_extractions` comprehension) and `:182`
  (`get_extraction`) — same three values from each entity `e`. **This file is outside the
  tranche's declared surfaces**; the edit is six lines of added kwargs across two construction
  sites, entailed by the sanctioned widening exactly the way WU1's `schemas/__init__.py`
  companion was. Without it the extraction list/read routes 500 and slice verification 7.1 cannot
  go green.

`tests/contract/test_api_schemas.py` was **not** touched: nothing there pins exact field sets or
required-ness for these two schemas (only per-field presence and annotations), so no pin blocked
the widening and no pin was updated. `schemas/__init__.py` needs no change (it exports the
module, not the classes) — confirmed, not assumed.

## Files changed (this tranche; diff vs HEAD — none of these files carry earlier-tranche edits)

- `backend/src/storico/api/schemas/story.py` (+27/−0) — `StoryVersionResponse` + import.
- `backend/src/storico/api/schemas/extraction.py` (+12/−0) — the three scalars on both schemas,
  with the contract note.
- `backend/src/storico/api/routes/stories.py` (+63/−0) — `ExtractionRepoDep`, the route, import.
- `backend/src/storico/api/routes/extraction.py` (+10/−0) — sanctioned `ExtractResponse`
  companion at `:268` + the forced `extraction_status` companion.
- `backend/src/storico/api/routes/extractions.py` (+6/−0) — forced companions at `:143`/`:182`
  (outside the declared surfaces; disclosed above).
- `backend/tests/test_api/test_stories.py` (+107/−1) — `TestStoryVersionsEndpoint`, 2 cases, plus
  the imports they need (`UTC`, `ExtractionStatus`, `seed_extraction`).

Tranche total: 225+/1− = 226 changed lines. Within the owner-accepted WU3 `size:exception` (one PR
over the 400-line budget); not generalized to WU5/WU6. Not committed, not staged, branch not
switched. The pre-existing `odd/tasks/extraction-versioning-090.md` modification and the
untracked `backend/.gitignore` / `.claude/skills/` were not touched.

## Remaining unchecked tasks (exact lines from tasks.md; 3.10 and 3.12 confirmed unchecked)

- [ ] 3.10 TRIANGULATE — `backend/tests/test_api/test_tasks.py` (`extraction_id` from another story
- [ ] 3.12 REFACTOR — `backend/src/storico/infrastructure/database/repositories/task_repository.py`:

(3.10's `test_tasks.py`/`test_stories.py`/`test_unfiltered_list_queries.py` triangulation and
3.12's repository confirmation are the next tranche's work; Phases 4–7 unchanged. taskProgress is
now 29/77.)

## Workload / PR boundary

WU3 ships as ONE PR under the accepted `size:exception`. Remaining WU3 work: 3.10's stories and
unfiltered halves, 3.12's refactor rerun. Suggested commit message (tasks.md): `feat(api): read
only the current version and expose the version selector`.

## Risks

- The extraction reads (`GET /api/v1/extractions…`, the 202 body) now always carry the three
  scalars; a client asserting an exact key set would see new keys. No such pin exists in the repo
  (grep-verified) and the frontend reads these responses additively.
- `is_current` is derived per request from the ordered list; the agreement with
  `find_current_version` (the frozen check's authority) is pinned at the repository layer by
  W3-T2's `test_find_current_version_agrees_with_list_versions_first_completed`.
- `GET /{story_id}/versions` answers the router's plain 404 shape for a missing story
  (`EntityNotFound` handler), same as `GET /{story_id}` today — 3.10 pins the posture explicitly.

---

# Apply Progress — WU3 tranche W3-T5 (tasks 3.10, 3.12: the read surfaces pinned against each other) — 2026-09-30, branch `feat/extraction-versioning-api-wu3`

The last code tranche of WU3. W3-T1 (predicate), W3-T2 (`list_versions`), W3-T3 (`extraction_id`
read + export filter) and W3-T4 (selector schema + route) remain in the worktree uncommitted and
untouched; every earlier section above is preserved verbatim. Task 3.10's `test_tasks.py` half
landed with W3-T3 (its RED run) — this tranche inventoried it rather than duplicating it.

## Structured status consumed

`gentle-ai.sdd-status` v2 for `extraction-versioning-api` from the parent: `nextRecommended:
apply`, `applyState: ready`, `blockedReasons: []`, `taskProgress` 29/77 at start,
`actionContext` mode `repo-local`, workspaceRoot and `allowedEditRoots`
`["/Users/alvaldes/Developer/storico"]`. Delivery path already resolved: **`size:exception`
explicitly accepted by the owner on 2026-09-30 for WU3 only** (one PR over the 400-line budget,
recorded in tasks.md). All edits stayed inside the two allowed test files plus the two SDD
artifacts; `task_repository.py` was read and confirmed but **not edited** (see 3.12 below).

## The bullet → test-function inventory (3.10)

Filled only the gaps; nothing was duplicated. **No `test_tasks.py` edit was needed this tranche** —
W3-T3 had already covered all three of its bullets:

| File | Bullet | Evidence (test function) | Covered by |
| --- | --- | --- | --- |
| `test_tasks.py` | foreign `extraction_id` → 422 `REQUEST_VALIDATION_FAILED`, no task of story B | `TestListTasksVersionReads::test_a_foreign_extraction_id_refuses_and_leaks_nothing` | W3-T3 (pre-existing) |
| `test_tasks.py` | `extraction_id` without `user_story_id` → 422 | `TestListTasksVersionReads::test_extraction_id_without_user_story_id_refuses_before_the_repository` (workspace + unfiltered branches both pinned) | W3-T3 (pre-existing) |
| `test_tasks.py` | story whose only run is `failed` → 200 `[]` | `TestListTasksVersionReads::test_a_story_whose_only_run_is_failed_reads_an_empty_page` (seeds a task on the failed version, so it proves the predicate, not absence) | W3-T3 (pre-existing) |
| `test_stories.py` | three `completed` versions mark exactly v3 `is_current` | `TestStoryVersionsEndpoint::test_three_completed_versions_mark_exactly_the_highest_current` — **added (W3-T5)** | W3-T5 |
| `test_stories.py` | v2 `completed` + v3 `pending` marks v2 `is_current` | `TestStoryVersionsEndpoint::test_lists_every_version_newest_first_and_derives_the_flags` (asserts exactly `[2]`, against v3 being the highest entry) | W3-T4 (pre-existing) |
| `test_stories.py` | 25 versions arrive in one payload | `TestStoryVersionsEndpoint::test_twenty_five_versions_arrive_in_one_untruncated_payload` — **added (W3-T5)**; measured result below | W3-T5 |
| `test_stories.py` | missing story → 404, non-member → 403, never a silent empty 200 | `TestStoryVersionsEndpoint::test_a_missing_story_is_404_and_a_non_member_is_403` — **added (W3-T5)**; foreign story seeded through `SQLAlchemyUserStoryRepository` in a workspace `authed_user` does not belong to, so the walk is exercised for real | W3-T5 |
| `test_stories.py` | `failed` version carries `status`, `error_info`, `model_used`, `provider`, `temperature`, `has_output=false` | `TestStoryVersionsEndpoint::test_a_failed_version_discloses_its_run_metadata_and_has_no_output` — **added (W3-T5)** (W3-T4's failed case asserted only the two booleans) | W3-T5 |
| `test_unfiltered_list_queries.py` | no-parameter `GET /api/v1/tasks/` shows no superseded tasks; `total` agrees with the rows | `test_the_unfiltered_task_list_shows_no_superseded_tasks` — **added (W3-T5)** | W3-T5 |

No existing test was edited, weakened or deleted; the four W3-T5 story cases and one unfiltered
case are pure additions (all pre-existing assertions intact).

## The 25-version payload result, stated as a count

`test_twenty_five_versions_arrive_in_one_untruncated_payload` seeds 25 versions on one story
(v1–v24 `completed`, v25 `pending`) and asserts the HTTP response is **25 entries** in one bare
array, ordered `[25, 24, …, 1]`, with exactly v24 marked `is_current` and
`has_output == [False] + [True] * 24`. A 20-row window would have returned 20 entries and dropped
five — the count assertion is the unbounded proof at the HTTP edge, and the flag derivation across
all 25 entries stops truncation from hiding behind a passing `is_current`.

## 3.12 REFACTOR — the three confirmations, each with how it was measured

A **pure confirmation: `task_repository.py` was not edited** (no defect found — no Python-side
filter, no `total` off the shared scope), and no new repository test was needed.

1. **`list_by_workspace` still serves its remaining callers — measured: it has zero.** Grep over
   `src/` and `tests/` for the *task* repository's `list_by_workspace`: the only `src/` hits are
   `routes/tasks.py:223` (a comment about the retired per-workspace loop) and
   `routes/export.py:120` — which is the **story** repository's own `list_by_workspace` (the
   Markdown section headers, not the task read; `story_repo`, a different port). No route, service
   or test calls `SQLAlchemyTaskRepository.list_by_workspace` (`task_service.py:89` calls
   `list_by_story`). Since 3.7 moved the export to `list_current_by_workspace`, the method is
   uncalled. **Per the task letter it is left in place** — deleting an unused public repository
   method is an owner decision, not this tranche's cleanup.
2. **No read path filters in Python — measured by reading every read path.**
   `task_repository.py`: the story scope is a correlated scalar subquery in SQL; the workspace and
   `workspace_ids` scopes are the `_current_version_only` `NOT EXISTS` clause in SQL; an explicit
   `extraction_id` is a SQL equality arm; `fetch_page`/`with_total` page and count in SQL;
   `_to_domain` maps rows and filters nothing. `routes/tasks.py` `list_tasks`: the only
   Python-side logic is the empty-`workspace_ids` early return (no statement issued) and the shape
   refusals — no row filtering. `routes/export.py`: the Python loops in `_markdown` group and
   render the already-filtered result set (serialization, not selection); the JSON path
   serializes `list_current_by_workspace`'s output directly. Confirmed by the passing
   statement-shape guards: `test_unfiltered_list_reads_its_table_once` (exactly one statement per
   table) and `test_list_page_pins_the_order_rule_in_sql`.
3. **The page and its `total` come from one statement — measured in code and by tests.**
   `with_total(stmt)` appends `count(*) OVER ()` to the page statement itself, whose `WHERE` is the
   same `scope` object the fallback `count_stmt` shares (both are built from one composed scope per
   branch, verified in `list_page`'s three arms); `fetch_page` executes the page statement once and
   reads the total off `rows[0][-1]`, running `count_stmt` only on the past-the-end fallback.
   Behavioral evidence: W3-T1's past-the-end case (`limit=2, offset=10` → `([], 4)` — the
   *filtered* total via the fallback path) and `test_unfiltered_list_reads_its_table_once`.

## TDD Cycle Evidence (strict TDD)

| Cycle | Test(s) | Command | Result |
| --- | --- | --- | --- |
| TRIANGULATE (3.10) | the 5 new cases + all pre-existing version reads | `conda run -n storico python -m pytest tests/test_api/test_tasks.py tests/test_api/test_stories.py tests/test_api/test_unfiltered_list_queries.py -m "not integration"` | **81 passed** — the triangulation cases pin already-implemented behavior across the three files at once; no RED was due (the implementation landed in W3-T1–T4 with their own RED proofs) |
| Wider gate | `tests/test_api tests/test_repositories` | same modules, `-m "not integration"` | **508 passed** — W3-T1's 491 + W3-T2's 2 + W3-T3's 8 + W3-T4's 2 + this tranche's 5 = 508 ✓ |
| Full suite | everything | `conda run -n storico python -m pytest -m "not integration"` | **1089 passed, 33 deselected** — the parent's 1084 + exactly the 5 new test functions of this tranche; no other delta |
| Lint | `ruff check` + `ruff format --check` | `conda run -n storico python -m ruff check src tests && … format --check src tests` | **All checks passed; 253 files already formatted** |

## Files changed (this tranche)

- `backend/tests/test_api/test_stories.py` (+96/−0) — 4 cases in `TestStoryVersionsEndpoint` (the
  three-completed, 25-version, 404/403-posture and failed-disclosure edges), reusing the class's
  `_create_story` helper and the file's existing foreign-workspace seeding pattern.
- `backend/tests/test_api/test_unfiltered_list_queries.py` (+45/−0) —
  `test_the_unfiltered_task_list_shows_no_superseded_tasks` (two completed versions on one story
  inside the multi-workspace fold; older version's titles absent, `total == len(items) == 4`).
- `backend/src/storico/infrastructure/database/repositories/task_repository.py` — **not edited**;
  3.12 was a confirmation with no defect found.

Tranche total ≈ 141 added lines. Within the owner-accepted WU3 `size:exception` (one PR over the
400-line budget; not generalizable to WU5/WU6). Not committed, not staged, branch not switched.

## Phase 3 — CLOSED

All twelve Phase 3 tasks (3.1–3.12) are `- [x]` in `tasks.md`; re-read confirmed 31/77 checked,
nothing outside Phase 3 moved by this tranche. Suggested commit message (tasks.md): `feat(api):
read only the current version and expose the version selector`.

## Remaining unchecked tasks (exact next lines from tasks.md)

- [ ] 4.1 RED — `backend/tests/test_unit/test_workspace_gate.py` **New** (path free): the truth table
- (Phase 4: 4.1–4.18; Phase 5: 5.1–5.13; Phase 6: 6.x; Phase 7 — all unchecked.)

## Risks

- None new. The 422-before-membership ordering for `extraction_id` without `user_story_id` was
  disclosed in W3-T3 and stands; the 403/404 posture of the versions read is now explicitly pinned.
- `list_by_workspace` (task repo) is now dead code kept deliberately; the archive pass should
  surface the owner decision to whoever closes the slice.

---

## Parent close-out of WU3 (delivery, CI numbers, ratified size)

Parent-run verification, not child-reported:

| Gate | Command | Result |
| --- | --- | --- |
| Full unit suite | `pytest -m "not integration"` | **1089 passed, 33 deselected** |
| Read-path gate | `pytest tests/test_api tests/test_repositories -m "not integration"` | **508 passed** |
| Lint / format | `ruff check src tests` · `ruff format --check src tests` | clean · 253 files already formatted |
| Frontend (untouched by WU3) | `pnpm test` · `pnpm exec tsc --noEmit` | **615 passed** · exit 0 |
| CI backend (Postgres) | run `36804148960` | **1104 passed, 18 skipped** |
| CI frontend | same run | **615 passed**, Astro build ok |
| Vercel | same run | pass |

**The CI delta is the Postgres proof.** 1104 − 1089 = **15 cases that cannot run on this machine**
(no Docker, no `psql`), the same 15 WU2 ran. The correlated subquery, the `NOT EXISTS` predicate and
the `uq_extractions_story_version` index assumption are only genuinely exercised there, so the local
SQLite suite is not the evidence that the filter is correct against the real planner — CI is.

**Commits.** `6b0f519` `feat(api): read only the current version and expose the version selector`
(18 files, 1213+/31−) and `ffa7157` `docs(odd): record WU3's five tranches, the resumed writer and
the wrong forecast`. Pushed to `origin/feat/extraction-versioning-api-wu3`; **PR #33** opened against
`feat/extraction-versioning-api-wu2` (base, because #32 is unmerged), all checks green.

**Size ratified against measurement, not forecast.** 1,244 code+test lines (331 production / 913
tests) against the ≈600–750 the exception was granted on. The owner was given the measured number,
the production/test split and the plan's own two-PR chain alternative (≈900 + ≈344, chained because
the selector needs `list_versions`), and ratified the single PR. Recorded in `tasks.md`'s delivery
section as a `[Ratified 2026-09-30, after measurement]` note.

**Standalone finding recorded for the next units.** `git diff | grep '^-' | grep -c assert` returned
**0** on `test_tasks.py`, `test_export.py`, `test_task_repo.py` and `test_stories.py` — the fastest
proof available that a fixture-heavy unit went green without loosening a single check.
