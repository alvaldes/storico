# Proposal: Extraction Versioning — HTTP Contract, Permission Gate and UI

> **Slice (b) of 3** for Storico feature 0.9.0. Siblings: `extraction-versioning-schema` (a, the
> root dependency) and `extraction-versioning-prompt` (c). Evidence:
> `explore.md` in this change, plus the shared ledger `../extraction-versioning-schema/explore.md`
> (D16–D23 re-verified with every claim at `file:line`, measured at `main` `ecea3e2`). Source spec:
> vault note *"Storico — versionado de extracción y tareas inválidas"* (D1–D23, all closed; no open
> questions).

## Intent

Slice (a) gave a run a version number and gave every task a producing run. Nothing reads, writes,
protects or renders any of it yet. This slice makes the version the thing the product shows: reads
and the export follow the current version, `PUT /tasks/{task_id}` enforces D5's field matrix in the
backend, the invalidation mark gets its endpoints and its confirmations, extract/mark/unmark and
story delete move behind owner-or-`ADMIN`, and both single-task delete paths close with `410 Gone`
instead of contradicting published copy. This is also where slice (a) stops being unshippable: the
current-version filter that makes a second run stop doubling the board lives here.

### Problem Statement

1. **Reads still return every version.** `GET /tasks`, the board and the export filter by
   `user_story_id`, so a story with two completed runs shows two task sets at once, and no version
   selector exists. `find_current_version(user_story_id)` is in the port with no product caller
   (slice (a)'s own "not independently deployable" note).
2. **The write contract still accepts everything.** `UpdateTaskRequest` accepts `title`,
   `description`, `status`, `priority`, `labels`, `dependencies` with `extra="forbid"`
   (`api/schemas/task.py:25-35`). D5 and D21 need three of those gone, and because `extra="forbid"`
   is already in force, "reject" means **removing the fields** — a client that still sends them gets
   422. That is the contract change C10 records, not a silent ignore.
3. **The mark has no door.** `task_invalidations` ships in (a) with its invariants (non-blank
   reason, one active mark per task) and no entity, no port and no endpoint. A table nobody can write
   to is not D6.
4. **The permission gate D13 needs does not exist.** Extract is open to any member today
   (`api/routes/extraction.py:154`, the role discarded at `:178`), and no dependency expresses
   "owner **or** `ADMIN`": `get_workspace_for_user` is membership-only (`api/dependencies.py:209`),
   `require_admin` is role-only (`:243`), `require_owner` is `ADMIN` **and** owner (`:261`) —
   *narrower* than D13's rule, not a synonym.
5. **A destructive door is already open.** `DELETE /stories/{story_id}` needs membership only
   (`api/routes/stories.py:290-309` via `require_story_workspace_access`, `api/dependencies.py:280`)
   and the cascade has been live since migration `0014`: a `MEMBER` can destroy every extraction and
   every task of a story today, with no confirmation and no record.
6. **Both single-task delete paths are wrong.** `DELETE /api/v1/tasks/{task_id}` is a real delete
   with zero frontend callers (`api/routes/tasks.py:320`) that contradicts the landing page's
   published promise at `frontend/src/i18n/en.json:132` / `es.json:132`
   ("Storico does not delete a single task"). `POST /api/v1/tasks/` has no product path — tasks are
   only ever born from a run (D3) — and, because (a) makes `tasks.extraction_id` `NOT NULL`, it now
   cannot insert at all: it answers 500 on purpose, pinned by test.
7. **An exhausted allocation retry has no status code.** (a) raises
   `VersionAllocationConflictError` (a `RepositoryError` subclass) and hands the mapping to this
   slice; today it lands on `repository_error_handler` as a 500 (`api/errors.py:143-158`).
8. **The UI knows nothing about versions.** No selector, no honest rendering of a failed version
   with its `error_info` and its absent output, no confirmation that names the version being frozen,
   and no D16 repetition notice.

## Scope

### In Scope

- **Field policy (D5, D21)** on `PUT /api/v1/tasks/{task_id}`, enforced in the backend:
  `status` and `labels` accepted always, `dependencies` only while the version is current; `title`,
  `description` and `priority` rejected in every case. The state machine stays ungated (it governs
  `status`, which never freezes).
- **Marks endpoints (D6, D7)**: create a mark with a mandatory reason, read the mark record, revoke
  the active mark. Owner-or-`ADMIN` only, current version only. Naming is this change's decision
  (the source spec delegates it).
- **D16 repetition notice**: a read endpoint that matches the task's normalized title
  (`casefold` + whitespace collapse) against marks recorded on **other versions of the same story**,
  returns the reason, and writes nothing and propagates nothing. Name is this change's decision.
- **D13 gate (C2)**: extract, mark and unmark become owner-or-`ADMIN`, with a new dependency
  predicate because none of the three existing ones expresses it.
- **D15 story delete**: owner-or-`ADMIN`, an explicit confirmation whose dialog names the versions
  it takes, a durable record of who deleted when and which version numbers were destroyed, and the
  Qdrant cleanup of that story's points. This closes a door that is already open and already
  destructive (Problem 5), on a feature that does not exist yet.
- **D17 `410 Gone`** on `DELETE /api/v1/tasks/{task_id}`, using the existing
  `api_route(..., status_code=410)` + `ApiError(error_code=…)` shape
  (`api/routes/extraction.py:68-91`, `api/routes/projects.py:35-59`; envelope `{detail, error_code}`
  from `api/errors.py:81-86`).
- **Retirement of `POST /api/v1/tasks/`** (D3), with the same `410 Gone` treatment and the same
  reasoning, replacing the 500 slice (a) left pinned.
- **The current-version filter** on `GET /tasks`, the board and the export — in SQL, not in Python —
  plus the version selector read and `version_number`/`provider`/`temperature` in the extraction
  response contract (slice (a)'s three seams).
- **The HTTP mapping of an exhausted allocation retry**, registered for its own class so the
  subclass's handler wins over `repository_error_handler`.
- **UI**: the version selector, the recut `TaskEditor`, the "Marcar como inválida" entry point, the
  failed-version rendering, both confirmations, the D16 notice, the delete-story dialog naming the
  version count, and the error-code/i18n copy in both locales.
- **Migration `0029`** for the story-deletion record (the only storage this slice needs; the chain
  continues from (a)'s `0028`).

### Out of Scope

**Owned by slice (a) — do not build it here:** migration `0028` and the schema, the version number
allocation and its bounded retry, `find_current_version` itself, the render/generate split and the
render-time snapshot write, the `task_invalidations` table and its database invariants, the removal
of `ExtractionRepository.delete` and of `extract_and_persist`.

**Owned by slice (c) — do not build it here:** the prompt's context blocks (D9), the snapshot key
*content* (`prompt_config.few_shots`, `project_context`, `story_text`, `negative_examples_omitted`,
`usage`), the Qdrant payload keys (`project_id`, `version_number`, `has_invalid_tasks`), the
`search_similar` signature change and D10's two exclusions, token-usage capture, and the 1000-story
bench (D20, D23).

**Outside 0.9.0 entirely, recorded so they are not reopened:** per-task judge scores and the
LLM-as-a-Judge; side-by-side comparison of two versions; grouping runs into experiments;
**batch extraction** (a closed non-goal — `POST /batch` does not exist and will not); comparison
metrics views and timing middleware; fuzzy or vectorial propagation of the invalid mark (D16 decides
an identical-text notice, not copied judgement); any `priority` editor (D21); and removing
`priority` from the contract — `TaskResponse`, the JSON export and the column — which is a separate
`BREAKING` release (D21 follow-up).

**This slice's own non-goals:** per-version export (the export follows the current version); exposing
`prompt_rendered` or the snapshot through the API (D20 reads it offline with a query); the board's
pre-existing `size=100` window (the filter changes *which* tasks are in it, not its width); rate
limiting; and a story-scoped task creation path of any kind.

## Capabilities

### New Capabilities

**None.** This slice adds no capability; it gives the two capabilities slice (a) introduces their
contract.

### Modified Capabilities

| Capability | This slice adds | Base |
| --- | --- | --- |
| `extraction-versioning` | The HTTP contract: field policy, version exposure in the responses, the selector read, the current-version filter on every read, both `410 Gone` retirements, the allocation-conflict status, and D15's gate + record + vector cleanup as the single sanctioned deletion | Introduced by slice (a) |
| `task-invalidation` | The marks endpoints, the reason validator, the current-version rule, the owner-or-`ADMIN` gate, the confirmations and the D16 repetition read | Introduced by slice (a) |
| `task-editor` | `title`/`description` read-only, `priority` out of the editor, the mark controls with a mandatory reason and the D16 notice, the field policy the component must respect, and the frozen-version dependency lock | Live: `openspec/specs/task-editor/spec.md` |
| `kanban-board` | The board reads the current version only, and a frozen version's cards remain draggable (the state never freezes) | Live: `openspec/specs/kanban-board/spec.md` |
| `export-download` | The export serializes the current version only | Live: `openspec/specs/export-download/spec.md` |
| `extraction-workflow` | Extraction restricted to owner/`ADMIN` with the 403 surfaced as an authorization error, the extract confirmation, and the new version number in the 202 response | Live: `openspec/specs/extraction-workflow/spec.md` |

*Spec-phase note:* in `openspec/changes/extraction-versioning-api/specs/`, the deltas for
`extraction-versioning` and `task-invalidation` are `ADDED Requirements` when (a) has not archived
yet and `MODIFIED Requirements` when it has; the spec phase resolves that against the base at
authoring time. The four live capabilities are `MODIFIED Requirements` either way.

> **Resolved by measurement 2026-09-30, and the resolution is the opposite of what this note assumed.**
> Slice (a) is archived and both capabilities now live in `openspec/specs/`. An earlier correction to this
> paragraph concluded that therefore (b)'s deltas must be `MODIFIED`. That was wrong and is retracted
> here. Counted, not reasoned: (b) declares **7** requirements in `extraction-versioning` and **4** in
> `task-invalidation`; the store holds **8** and **6**. **Zero name collisions** — so every one of (b)'s
> requirements is a new obligation on an existing capability, which is exactly what `ADDED Requirements`
> means in OpenSpec. `MODIFIED` would be wrong: it requires the existing header verbatim, and none of
> (b)'s headers matches a stored one. (c) is the same shape: 7 new requirements on
> `extraction-versioning`, 0 on `task-invalidation`.
>
> **What the collision check did surface, and it is an authoring note rather than a blocker:** two of
> (b)'s requirements restate (a)'s invariants *at the API layer*, with different wording.
> `Revoking Updates the Row and Never Deletes It` (the endpoint: 204, 404 when there is no active mark,
> 409 `TASK_VERSION_FROZEN`, owner/`ADMIN` gate) contains the sentence "The mark row MUST never be
> deleted by revocation", which `task-invalidation` already guarantees as `Revoking Is an Update, Never a
> Delete` (the storage invariant). `Creating a Mark Requires a Reason, the Current Version and the Gate`
> likewise overlaps `The Mark Belongs to the Version It Was Made On` and `The Reason Is Mandatory as a
> Database Invariant`. Both layers legitimately need to say it — one binds the schema, one binds the
> route — but when (b) archives, `openspec/specs/` will hold **two requirements asserting the same
> never-delete rule**. Keep them deliberately: (b)'s text should state the HTTP contract and cite the
> stored invariant rather than re-derive it, so a future change does not have to edit the same obligation
> in two places and can tell which layer each one governs.

## Decisions This Change Makes

The source spec delegates the endpoint names to this change in two places: *"Los nombres de los
endpoints de la marca los define el change de OpenSpec"* and *"Aviso de repetición (D16): el nombre
lo define el change"*. These are decisions, not open questions.

| Surface | Decision |
| --- | --- |
| `PUT /api/v1/tasks/{task_id}` | Body shrinks to `status`, `labels`, `dependencies`; `extra="forbid"` stays. `title`/`description`/`priority` → **422** `REQUEST_VALIDATION_FAILED`. `dependencies` on a non-current version → **409** `TASK_VERSION_FROZEN` |
| `DELETE /api/v1/tasks/{task_id}` | **410 Gone**, code `TASK_DELETE_ENDPOINT_REMOVED`, detail pointing at D12; `include_in_schema=False`; deletes nothing |
| `POST /api/v1/tasks/` | **410 Gone**, code `TASK_CREATION_ENDPOINT_REMOVED`, detail pointing at D3; `CreateTaskRequest` deleted with it |
| `POST /api/v1/tasks/{task_id}/invalidations` | Create the mark. Body `{"reason": "…"}` → **201** with the mark. Blank/whitespace-only reason → 422. Already active mark → **409** `TASK_ALREADY_MARKED`, detail carrying the active reason. Non-current version → 409 `TASK_VERSION_FROZEN` |
| `GET /api/v1/tasks/{task_id}/invalidations` | The task's mark record, `marked_at` descending, active first; each row carries `id`, `reason`, `marked_by`, `marked_at`, `revoked_by`, `revoked_at` |
| `DELETE /api/v1/tasks/{task_id}/invalidations/current` | Revoke the active mark → **204**. An **UPDATE** on the row (slice (a)'s rule): the mark ceases to be active, the record is never deleted. No active mark → 404 |
| `GET /api/v1/tasks/{task_id}/invalidations/repetition` | D16's notice. Marks on **other** versions of the same story whose normalized title equals this task's; `{"matches": [{version_number, reason, marked_at}]}`. The title is resolved server-side from the task id, so the normalizer lives in one place and no client can probe arbitrary text. Read-only: writes and propagates nothing |
| `GET /api/v1/stories/{story_id}/versions` | The selector read. **Unpaginated** (a story's version count is bounded by hand-run extractions, and the paginator's 20/100 window would truncate it silently) and ordered `version_number DESC`; per version: `id`, `version_number`, `status`, `model_used`, `provider`, `temperature`, `created_at`, `completed_at`, `error_info`, `is_current`, `has_output` |
| `GET /api/v1/tasks/?user_story_id=` | Current version by default; optional `extraction_id=` reads one specific version (must belong to that story). No completed version → empty list, not an error |
| `GET /api/v1/tasks/?workspace_id=` | Current-version-only SQL predicate; the page and its `total` come from the same filtered statement |
| `GET /api/v1/workspaces/{w}/export/tasks/` | Current-version-only |
| `POST /api/v1/workspaces/{w}/extract/` | `require_owner_or_admin`; body unchanged; 202 response gains `version_number` |
| `DELETE /api/v1/stories/{story_id}` | `require_story_owner_or_admin`, then vector cleanup, then the story delete plus its record in one transaction |

New registry entries in `api/error_codes.py` (the frontend's `lib/error-codes.ts` + i18n
`errorCodes` family map them to copy in both locales): `TASK_DELETE_ENDPOINT_REMOVED`,
`TASK_CREATION_ENDPOINT_REMOVED`, `TASK_VERSION_FROZEN`, `TASK_ALREADY_MARKED`,
`VERSION_ALLOCATION_CONFLICT`, `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`.

The empty-reason rule needs **no** new code: it is a request-validation 422
(`REQUEST_VALIDATION_FAILED`), which is exactly the residual slice (a) handed over — its database
`CHECK` covers spaces and this slice's validator strips all Python whitespace.

## Approach

1. **The field policy is decided per field, not per request.** Only the presence of `dependencies`
   is state-sensitive, so the check keys on `model_fields_set` (what the client actually sent), never
   on `None`: `[]` explicitly means "clear the dependencies" and is still a write to a frozen version
   → 409. A payload of `{"status": "done"}` on a frozen version must keep working — that is D5's
   whole point, and the board (drag-and-drop) is the caller that proves it.
2. **The reason is validated where it is written.** A `field_validator` strips all whitespace and
   rejects the empty result, and the field is bounded by the column's 500. `POST` with a blank reason
   persists nothing and returns 422; the editor's client-side check is a convenience, not the rule.
3. **"Frozen" is derived, never guessed.** The route resolves the task's `extraction_id` and compares
   it with `find_current_version(story_id)`; a task on a `pending` or `failed` version, or on a story
   with no completed version, is not on the current version and answers 409. `TASK_VERSION_FROZEN`
   carries the current version's number in the detail so the copy can name it.
4. **The gate is one predicate and three thin wrappers.** `_is_owner_or_admin(workspace, role, user)`
   is the rule (`role == ADMIN or workspace.owner_id == user.id`); the wrappers are shaped like the
   existing membership walkers so every route keeps its current-shaped 404/403 behaviour:
   `require_owner_or_admin` (chained on `get_workspace_for_user`, for extract),
   `require_story_owner_or_admin` (the story→project→workspace walk plus the rule, for D15), and
   `require_task_owner_or_admin` (the task→story→project→workspace walk plus the rule, for the marks
   endpoints). `require_story_workspace_access` stays for reads and for `PUT /stories/{id}`, and the
   `410` handlers keep membership-only access so a non-member learns nothing new.
   **Not** in the gate: `PUT /tasks/{task_id}` (a `MEMBER` keeps moving cards and editing labels —
   D13's own "efecto neto") and the repetition read.
5. **Story delete is destructive, so its order is explicit.** (i) read the story's version numbers and
   snapshot them; (ii) delete that story's points from Qdrant (filtering on the payload keys that
   already exist — `user_story_id` and `workspace_id`, `qdrant_adapter.py:257-265` — so this does not
   wait on slice (c)'s new keys); (iii) delete the story and insert the record in one transaction.
   A Qdrant failure aborts **before** the relational delete with a 502/503 and the story survives to
   be retried: D15's stated failure is orphan points still retrievable as few-shots for **other**
   stories (D10), and that failure only happens if the relational delete lands first. When no vector
   store is configured (the dev degradation path that returns `None`), the cleanup is skipped because
   no points exist to clean.
6. **The deletion record must outlive the story.** Migration `0029` adds `story_deletions` (actor,
   timestamp, story identity as *values*) and the destroyed version numbers. It must **not** carry an
   FK to `stories` or to `extractions` with `ON DELETE CASCADE`: the record would be destroyed by the
   very delete it records. The actor FK follows the repo's convention
   (`projects.created_by`, `ON DELETE SET NULL`) so the record survives account deletion.
7. **The 410s replace methods; they do not remove them.** Retiring a published `DELETE` outright is a
   `BREAKING CHANGE` and would hand this feature a **MAJOR** bump; `410 Gone` keeps 0.9.0 MINOR and
   leaves the path answering with the reason written down. The same reasoning governs
   `POST /api/v1/tasks/`: it is a published method with no product path, so it becomes a 410 rather
   than a 404/405, and the two tests slice (a) pinned on its refusal flip to pin the 410. The landing
   copy at `en.json:132` / `es.json:132` already promises no single-task deletion, so D17 makes the
   product honest rather than changing what it says.
8. **The current-version filter belongs in SQL.** Filtering after a paginated query would drop tasks
   while `total` keeps counting them — the silent truncation this feature exists to avoid, and the
   board and export both cap their window. New repository reads carry the predicate: for a story,
   `tasks.extraction_id = current_version.id`; for a workspace, "this task's extraction is the
   highest-numbered `completed` version of its story", expressed with `EXISTS`/`NOT EXISTS` so a
   single statement still serves the page and its count.
9. **The selector reads versions, not task lists.** A story-scoped, unpaginated version list keeps the
   selector honest at any version count and avoids widening `GET /extractions/` (which stays as it
   is). A failed version appears with its `error_info`, model and date, and the UI renders "no output"
   rather than an empty board that looks like a successful run of zero tasks; `has_output` exists so
   the client does not have to infer that from an empty task list.
10. **The response contract gains three scalars, not the snapshot.** `ExtractionResponse` and
    `ExtractResponse` gain `version_number`, `provider` and `temperature` (slice (a)'s seam).
    `prompt_rendered` stays out of the API: D20 measures it offline with a query, and the selector
    does not need the composed prompt.
11. **`VersionAllocationConflictError` gets its own handler → 409
    `VERSION_ALLOCATION_CONFLICT`.** Registered for its own class in `register_exception_handlers`,
    which is what makes it win: the handler lookup walks the exception's MRO, so the subclass's
    handler is found before `repository_error_handler`. 409 over 503 because the database is healthy
    and the request simply lost a race the user may re-run; 503 plus `Retry-After` would advertise an
    infrastructure outage. The detail names the story and says the run may be retried.
12. **The UI changes are four components and one rule.** `VersionSelector.tsx` (new) is rendered by
    `StoryDetail.tsx` and drives which version's tasks the page shows; `TaskEditor.tsx` renders
    `title`/`description` read-only, drops `priority`, disables `dependencies` on a frozen version,
    keeps `status` and `labels` live, and owns the "Inválida" checkbox + mandatory reason textarea
    plus the D16 notice; `StoryDetail.tsx` gains the "Marcar como inválida" button beside "Editar"
    (same editor, checkbox pre-checked, focus on the reason, nothing applied until save) and the
    extract confirmation that names the version being frozen and the new version; the existing
    story-delete `AlertDialog` in `StoryDetail.tsx` and `StoriesList.tsx` is rewired through
    `storyStore.deleteStory` and must name the version count. The delete control is hidden/disabled
    for a `MEMBER`, but the server gate is the authority.
13. **The version-aware client is one new module.** `frontend/src/lib/versioning-api.ts` carries the
    version list, the marks and the repetition read; `lib/tasks-api.ts` stops sending
    `title`/`description` **in the same work unit that removes them from the schema**, or the editor
    breaks on save; `lib/error-codes.ts` and the `errorCodes` family in both locales learn the six new
    codes.
14. **Copy honesty is part of the change.** `landing.faq.a4` (`en.json:132` / `es.json:132`) promises
    "edit any of them — title, description, labels, or dependencies", which D5 now contradicts: the
    same edit that closes D17 fixes the second false promise, in both locales. All new copy is
    neutral international Spanish (tú, no voseo) and `en.json`/`es.json` keep identical key sets, as
    `frontend/src/i18n/__tests__/neutral-spanish.test.ts` enforces (ADR-008).
15. **Sequencing.** (a) and (b) ship in one release: (b) is where (a)'s current-version filter lands,
    and (b) reads `version_number`, `extraction_id`, the marks table and
    `VersionAllocationConflictError` from (a). `0029` continues the chain from `0028`, and the deploy
    keeps ADR-005's maintenance window.
16. **Review workload forecast.** This slice touches the task/story/extraction/export routes, the
    dependencies module, two schema modules, the error registry, a migration, two repositories, the
    frontend editor + selector + stores + i18n, and tests on both sides. It is expected to exceed the
    400-line budget on its own. Candidate work units: (1) field policy + the two 410s (backend
    contract, its own tests and the client that must stop sending the removed fields), (2) the
    current-version filter + the selector read + the response scalars, (3) the gate + story delete +
    `0029` + the Qdrant cleanup and its record, (4) the marks endpoints + D16 read + the entire UI and
    i18n. The delivery decision stays with `ask-on-risk`: on budget risk, stop and ask — no chain
    strategy is preselected here.

## Affected Areas

| Area | Impact | Description |
| --- | --- | --- |
| `backend/src/storico/api/schemas/task.py` | Modified | `UpdateTaskRequest` shrinks to `status`/`labels`/`dependencies`; `CreateTaskRequest` removed with its 410 |
| `backend/src/storico/api/schemas/extraction.py` | Modified | `version_number`, `provider`, `temperature` on `ExtractionResponse` and `ExtractResponse` |
| `backend/src/storico/api/routes/tasks.py` | Modified | Field policy on `PUT`; `DELETE /{task_id}` → 410; `POST /` → 410; the three mark endpoints and the D16 read |
| `backend/src/storico/api/routes/stories.py` | Modified | `DELETE /{story_id}` gated, cleaned, recorded; `GET /{story_id}/versions` |
| `backend/src/storico/api/routes/extraction.py` | Modified | Gate on extract; `version_number` in the 202 response |
| `backend/src/storico/api/routes/export.py` | Modified | Current-version-only serialization |
| `backend/src/storico/api/dependencies.py` | Modified | `_is_owner_or_admin` + the three wrappers |
| `backend/src/storico/api/error_codes.py` | Modified | Six new registry entries |
| `backend/src/storico/api/errors.py` | Modified | `VersionAllocationConflictError` handler (409) |
| `backend/src/storico/domain/entities/task_invalidation.py` | New | The mark entity slice (a) deliberately left to this slice |
| `backend/src/storico/domain/ports/task_invalidation_repository.py` | New | Create / revoke / read / repetition matching |
| `backend/src/storico/infrastructure/database/models/story_deletion.py` | New | The deletion record (no FK to `stories`) |
| `backend/src/storico/infrastructure/database/alembic/versions/0029_*.py` | New | `story_deletions` (+ version numbers) |
| `backend/src/storico/infrastructure/database/repositories/task_invalidation_repository.py` | New | Persistence, the revoke update, the normalized-title match |
| `backend/src/storico/infrastructure/database/repositories/{task,extraction}_repository.py` | Modified | Current-version reads (story and workspace scope); nothing deleted |
| `backend/src/storico/infrastructure/vector/qdrant_adapter.py` | Modified | Story-scoped point deletion on existing payload keys (slice (c) owns new keys) |
| `backend/src/storico/domain/services/{task_service,story_*}.py` · `infrastructure/…/story_deletion*` | Modified/New | Field policy guards, the deletion record, the cleanup ordering |
| `backend/tests/**` | Modified | `test_tasks.py` (410s, policy, marks), `test_stories.py` (gate, record, cleanup), `test_extraction.py` (gate, 409 allocation), `test_export.py` (filter), repository tests, new unit/integration cases |
| `frontend/src/components/react/VersionSelector.tsx` | New | The D4 selector |
| `frontend/src/components/react/{TaskEditor,StoryDetail,StoriesList}.tsx` | Modified | Read-only `title`/`description`, no `priority`, mark controls, both confirmations, version count in the delete dialog |
| `frontend/src/components/react/{KanbanBoard,ExportPanel}.tsx` | Modified | Consume the filtered reads; frozen-version cards stay draggable |
| `frontend/src/lib/versioning-api.ts` | New | Versions, marks, repetition read |
| `frontend/src/lib/{tasks-api,stories-api,error-codes}.ts` · `stores/{taskStore,storyStore}.ts` | Modified | Stop sending removed fields; version and mark state; new codes |
| `frontend/src/types/**` · `frontend/src/i18n/{en,es}.json` | Modified | Version/mark types; all new copy in both locales, plus the `landing.faq.a4` correction |
| `frontend/src/**/__tests__/**` | Modified | Editor, selector, store and i18n parity/neutral-Spanish tests |

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| The editor 422s on every save because the schema shrank before the client stopped sending `title`/`description` | High | Schema and client change in one work unit; a test asserts the exact payload the editor sends |
| `dependencies` absent vs. `[]` is misread and a frozen version accepts a write (or a `MEMBER`'s status edit is refused) | Medium | Check `model_fields_set`, never `None`; scenarios for `{"status": …}` on frozen and `{"dependencies": []}` on frozen |
| Story delete destroys the record along with the story | Medium | `0029` has no FK to `stories`/`extractions`; the version numbers are copied as values before the cascade |
| Qdrant cleanup fails or is skipped and orphan points keep surfacing as few-shots for other stories (D15 + D10) | Medium | Cleanup runs before the relational delete and aborts it on failure; no-adapter environments have no points to clean |
| The cleanup's filter depends on keys slice (c) adds | Low | Filter on `user_story_id` + `workspace_id`, which already exist; (c) only widens the payload |
| The current-version filter lands in Python and the board/export silently truncate an already-capped window | Medium | The predicate is in SQL and `total` comes from the same statement; a test asserts page and total agree |
| A `MEMBER` hitting extract/mark/unmark/story-delete sees a raw 403 | High | New code `WORKSPACE_OWNER_OR_ADMIN_REQUIRED` mapped in `lib/error-codes.ts` and both locales; controls hidden/disabled for a `MEMBER` |
| `VersionAllocationConflictError` keeps answering 500 | Medium | Its own handler in `register_exception_handlers`; a test forces the conflict and asserts 409 + code |
| A reviewer reads the revoke `DELETE` as a contradiction of D12 or of the task `DELETE` 410 | Medium | The distinction is stated: the revoke updates the row and the record survives; the task `DELETE` names a task, which is never deleted |
| Removing `title`/`description`/`priority` is read as a UI preference rather than a contract change | Medium | Problem 2 and the decision table say 422 out loud (C10), and the `410`s say why nothing is *removed* |
| Slice (a) deployed alone shows two task sets per story | High | (a) and (b) ship in one release; the filter lands here |
| New copy lands in one locale only, or in voseo | Medium | `neutral-spanish.test.ts` and the key-parity test are part of the change |
| Review budget exceeded without a delivery decision | High | Step 16's four work units and the `ask-on-risk` pause; no chain strategy is preselected |

## Rollback Plan

- Backend: restore `title`/`description`/`priority` in `UpdateTaskRequest` (the frozen-version
  dependency guard goes with them), restore the `DELETE /tasks/{id}` handler and the
  `POST /tasks/` route, drop the mark endpoints and the D16 read, restore the membership-only gates
  on extract and story delete, remove the current-version predicates from the reads, and revert the
  three response scalars.
- Migration `0029`: `downgrade()` drops `story_deletions`. It is a record, not data the product
  reads; reverting it loses the audit trail of deletes performed while the release was live.
- Frontend: revert `TaskEditor`'s read-only fields and the mark controls, remove
  `VersionSelector.tsx`, restore the previous delete dialog handling, and revert the i18n keys and
  the `landing.faq.a4` copy.
- **Not reversible:** a story destroyed under D15 and its Qdrant points are gone. Rolling back the
  code does not bring back the versions (C7), and the landing-page promise at `en.json:132` /
  `es.json:132` must not be re-broken by a revert — the copy stays.
- The `410` paths revert to their previous handlers, which restores the contradiction D17 fixed; the
  revert itself should keep the landing copy and the endpoint in step.

## Dependencies

- **Slice (a) must land first, in the same release**: `version_number`, `tasks.extraction_id`,
  `task_invalidations`, `find_current_version`, and `VersionAllocationConflictError` all come from it.
  This slice cannot be deployed before (a).
- **Migration `0029` continues the chain from (a)'s `0028`**; nothing else may claim `0029`.
- **Slice (c) reads what this slice exposes**: the mark read path is what a later `has_invalid_tasks`
  payload key and the negative-example block will consume; (b) leaves `_store_rag` untouched.
- **ADR-005's window**: `0029` runs between `docker stop` and `docker run`, so a failed
  migration leaves the API down on purpose.
- **Existing assets this slice reuses**: the `AlertDialog` primitive already used by `StoryDetail.tsx`
  and `DeleteAccountDialog.tsx`; the `{detail, error_code}` envelope; the `410` mechanism; the
  `@base-ui/react`-based UI kit; the i18n parity and neutral-Spanish tests.
- Source decisions: D3, D4, D5, D6, D7, D13, D15, D16, D17, D21, D22 at the surface, plus C1, C2,
  C4, C7, C8, C9, C10 as the accepted consequences.
- **No new runtime dependency, no new setting.**

## Success Criteria

- [ ] `PUT /api/v1/tasks/{task_id}` rejects `title`, `description` and `priority` with 422 in every
      case, and `dependencies` with 409 `TASK_VERSION_FROZEN` when the version is not current.
- [ ] `status` and `labels` are editable on a frozen version: a Kanban drag on an old version's card
      succeeds, and the state machine is not gated by version currency.
- [ ] A mark with an empty or whitespace-only reason persists nothing and returns 422; a valid mark
      round-trips with its reason, actor and timestamp.
- [ ] Marking and unmarking work on the current version and return 409 `TASK_VERSION_FROZEN` on a
      frozen one; revoking leaves the row readable as revoked, and re-marking creates a second row.
- [ ] A `MEMBER` receives 403 `WORKSPACE_OWNER_OR_ADMIN_REQUIRED` on extract, mark, unmark and story
      delete; the workspace owner and an `ADMIN` succeed on all four.
- [ ] `GET /tasks` (by story and by workspace), the board and the export show only the current
      version's tasks; a second completed run does not double the board, and the paginated `total`
      matches the filtered rows.
- [ ] The selector lists every version of a story, marks the current one, and offers a failed version
      with its `error_info`, model and date while rendering its absent output honestly.
- [ ] `DELETE /api/v1/tasks/{task_id}` answers 410 and deletes nothing;
      `POST /api/v1/tasks/` answers 410 and no task can be created outside a run.
- [ ] Deleting a story as the owner or an `ADMIN` records who deleted, when and which version numbers
      were destroyed, and removes that story's Qdrant points; a Qdrant failure aborts the delete
      without destroying the story.
- [ ] An exhausted allocation retry answers 409 `VERSION_ALLOCATION_CONFLICT`, not 500.
- [ ] The extract confirmation names the version being frozen and the new version; mark and unmark
      confirm; the "Marcar como inválida" button opens the editor with the checkbox checked and the
      focus in the reason field, and nothing is applied on cancel.
- [ ] The D16 notice appears when the normalized title matches a mark from another version of the
      same story, shows that reason with the version it came from, offers to copy it, and writes and
      propagates nothing.
- [ ] `landing.faq.a4` no longer promises editing `title`/`description` or per-task deletion, in both
      locales.
- [ ] `cd backend && conda run -n storico python -m pytest` and `cd frontend && pnpm test` are green,
      including the neutral-Spanish and i18n key-parity tests.
