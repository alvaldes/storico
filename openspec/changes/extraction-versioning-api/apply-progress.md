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
