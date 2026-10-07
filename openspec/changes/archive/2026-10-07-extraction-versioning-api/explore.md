# Exploration: extraction-versioning-api

> **Change**: `extraction-versioning-api` — slice (b) of three
> **Depends on**: `extraction-versioning-schema` (a)
> **Shared evidence base**: `../archive/2026-09-30-extraction-versioning-schema/explore.md` (the D16–D23
> re-verification ledger, every claim with `file:line` at `main` `ecea3e2`)
> **Created**: 2026-09-28

This slice owns the HTTP contract, the permission gate and the UI. The shared ledger already
confirms every code claim this slice needs; this file records only the slice-specific consequences,
so the phase artifacts do not re-derive them.

## What (a) leaves this slice to finish

(a) ships the schema and the identity rules and **stops there**. Four things are half-finished by
design and are (b)'s responsibility:

1. **Reads still return every version.** `GET /tasks`, the board and the export still filter by
   `user_story_id`, so a story with two completed runs shows two task sets at once. (b) applies
   `find_current_version(user_story_id)` (a)'s port method to the read paths. This is why (a) is
   not independently deployable.
2. **The manual task route answers 500.** `tasks.extraction_id` is `NOT NULL` from `0028`, and
   `POST /api/v1/tasks/` (`api/routes/tasks.py:89-114`) cannot supply it. (a) pins that refusal in
   `tests/test_api/test_tasks.py` on purpose; (b) retires the route.
3. **The mark has no door.** `task_invalidations` exists with its invariants (reason `CHECK`, one
   active mark per task via the partial unique index) but has no entity, no port, no endpoint.
4. **An exhausted allocation retry has no status code.** (a) raises
   `VersionAllocationConflictError` (a `RepositoryError` subclass); today that lands on
   `repository_error_handler` as a 500. (b) registers its own handler **before** that one — FastAPI
   matches handlers by class, so a subclass needs its own registration to win — and chooses the
   status.

## Contract facts this slice must respect (all verified in the shared ledger)

| Fact | Evidence | Consequence for (b) |
| --- | --- | --- |
| `UpdateTaskRequest` accepts `title, description, status, priority, labels, dependencies` with `extra="forbid"` | `api/schemas/task.py:25-35` | D5+D21 shrink it to `status, labels, dependencies(when current)`. Because `extra="forbid"` is already in force, rejecting `title`/`description`/`priority` means **removing the fields**, and an existing client sending them then gets 422 — that is the C10 contract change, not a silent ignore |
| The frontend task editor already sends five fields including `status` | `TaskEditor.tsx` → `stores/taskStore.ts:399-434` → `lib/tasks-api.ts:74-81` | The UI must stop sending `title`/`description` in the same change that removes them from the schema, or the editor breaks on save |
| `priority` is in `TaskResponse` and in the JSON export only | `api/schemas/task.py:48`; `api/routes/export.py:38-72,118-123` | D21: stays in the response and the export, is rejected on write, and is absent from the editor |
| No dependency expresses "owner **or** ADMIN" | `api/dependencies.py:209` `get_workspace_for_user` (membership only), `:243` `require_admin` (`role != ADMIN`), `:261` `require_owner` (chains `require_admin`, then `owner_id`) | The gate is **new code**, not a combination of the two existing gates. Note `require_owner` = ADMIN **and** owner, so it is *narrower* than D13's rule, not a synonym |
| Extract is open to any member today, and the role is already discarded | `api/routes/extraction.py:154`, role dropped at `:178` | D13 restricts a **deployed** capability on purpose (C2), and the discarded role becomes the signal the new gate consumes |
| `DELETE /stories/{story_id}` needs membership only, and the cascade is live | `api/routes/stories.py:290-309` + `require_story_workspace_access` (`dependencies.py:280`); cascade from `0014` | D15 closes a door that is **already open and already destructive**: today a `MEMBER` can destroy every extraction and task of a story with no confirmation and no record |
| 410 Gone mechanism exists twice | `api/routes/extraction.py:68-91` `deprecated_extract`, `api/routes/projects.py:35-59` `deprecated_projects` | D17's `DELETE /tasks/{id}` uses the same `api_route(..., status_code=410)` + `ApiError(error_code=…)` shape; codes live in `api/error_codes.py`, envelope `{detail, error_code}` via `api/errors.py:81-86` |
| `ExtractionRepository.delete` has one test and zero production callers | `domain/ports/extraction_repository.py:53-56`, impl `:123-134`, test `test_extraction_repo.py:416,420` | (a) removes the port method; (b) does not reintroduce any delete path |
| The i18n copy already promises no single-task deletion | `frontend/src/i18n/en.json:132`, `es.json:132` (`landing.faq.a4`) | D17 makes the landing page honest; (b) must keep `en.json`/`es.json` key-identical (ADR-008, `frontend/src/i18n/__tests__/neutral-spanish.test.ts`) |
| The task state machine is enforced in `PUT /tasks/{id}` today | `api/routes/tasks.py:277` → `application/services/task_service.py:30,37`, table at `domain/validators/state_machine.py:28-36` | D5 keeps `status` editable on frozen versions, so the state machine must **not** be gated by version currency |
| A failed version has a complete input snapshot and absent output | (a) spec "Each Version Freezes Its Run Snapshot at Render Time"; `prompt_config` key sets at `api/routes/extraction.py:236-239` vs `infrastructure/tasks/extraction_task.py:438-442` | The selector must offer a failed version with its `error_info`, model, date and rendered prompt, and must render "no output" honestly (D22) |
| Task identity is `uuid7` with no natural key; no title normalization helper exists | `models/task.py:22,48-51`; the only `casefold()` on titles is dependency resolution at `api/routes/export.py:45,49` | D16's notice needs a normalizer (`casefold` + whitespace collapse) that the backend has never had. It is a **new** helper, and it must not be confused with story dedupe, which is exact-string `(actor, feature, benefit)` (`domain/services/story_import.py`) |

## Decisions this slice takes that the source spec delegates

The spec says outright: *"Los nombres de los endpoints de la marca los define el change de
OpenSpec"* and *"Aviso de repetición (D16): el nombre lo define el change"*. So this change names
them; the naming is not an open question.

## Boundaries of this slice

**In:** field policy on `PUT /tasks/{task_id}`, the marks endpoints, the owner-or-`ADMIN` gate for
extract / mark / unmark / story-delete, the story-delete confirmation and record plus its Qdrant
cleanup, `410 Gone` on `DELETE /tasks/{id}`, retirement of `POST /tasks/`, the version selector
read path, the task editor changes, both confirmation dialogs, the D16 notice, the current-version
filter on all reads, and the HTTP mapping of an exhausted allocation retry.

**Out (slice (c)):** the prompt's context blocks, the snapshot's key content, the Qdrant payload
keys and the `search_similar` signature change, `usage` capture, the 1000-story bench.
**Out (0.9.0 entirely):** side-by-side comparison, experiment grouping, batch extraction (closed
non-goal), per-task judge scores, a `priority` editor, removing `priority` from the contract.

**One coupling to keep visible:** D15 requires cleaning that story's points from Qdrant on delete.
The payload keys that make a point identifiable per project/version arrive with (c). (b) must
either filter on the payload keys that already exist (`user_story_id`, `workspace_id` — verified at
`infrastructure/vector/qdrant_adapter.py:257-265`) or state the dependency on (c) rather than
leaving orphan points behind silently; D10 says orphan points stay retrievable as few-shots for
**other** stories, which is exactly the failure D15 warns about.
