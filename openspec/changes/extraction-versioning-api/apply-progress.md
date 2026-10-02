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
