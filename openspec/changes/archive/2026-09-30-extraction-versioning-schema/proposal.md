# Proposal: Extraction Versioning — Schema and Version Identity

> **Slice (a) of 3** for Storico feature 0.9.0. Siblings: `extraction-versioning-api` (b),
> `extraction-versioning-prompt` (c). Evidence ledger: `explore.md` in this change
> (measured at `main` `ecea3e2`). Source spec: vault note *"Storico — versionado de extracción y
> tareas inválidas"* (decisions D1–D23, all closed; no open questions).

## Intent

Give an extraction a **version identity** and give every task a **provenance**, so that two runs
over the same user story stop being indistinguishable rows. Today `Extraction` has no version and
no order (`domain/entities/extraction.py:21-38`), `Task` hangs off `user_story_id`
(`domain/entities/task.py:23`), and a second run's task set lands in exactly the same place as the
first one's. There is no way to say "this is v2", no way to keep only one set of tasks current, and
no place to record that a human judged a generated task invalid.

This slice owns the **storage and the identity rules**: migration `0028`, the per-story version
number, the task→extraction link, the run snapshot columns, the invalidation mark table, and the
"nothing inside a version is ever deleted" structure. It owns no HTTP contract, no permission gate
and no UI — those are slice (b) — and no prompt content or vector-store payload — those are
slice (c).

### Problem Statement

1. **A run has no identity.** `extractions` rows are unordered siblings per story. D1 makes the run
   the unit of versioning, so the run needs a number that survives.
2. **A task does not know which run produced it.** `tasks.user_story_id` is the only link, so
   "the tasks of v2" is not expressible (D3), and a second run doubles the task set with no way to
   tell the two apart.
3. **A failed run is a version that promises a snapshot it does not have.** Every run is born
   `pending` before the LLM call (`api/routes/extraction.py:230-246`) and a failure keeps the row
   (`infrastructure/tasks/extraction_task.py:131`). Measured: `prompt_config` is written with
   **different key sets by outcome** — `{validate, temperature}` on the pending insert and on every
   failure path (`:236-239`, copied at `:199`, `:506`, `:600`), and only completed rows add
   `system_prompt` (`:438-442`). D22 (a failing run burns a number and never becomes current) makes
   that hole operative: the versions D22 introduces are exactly the versions with no usable
   snapshot. D8's promise — every version freezes what it takes to read and reproduce it later —
   is false for them today, and cannot be made true by adding a `version_number` column alone.
4. **Nothing observes user judgement as data.** A task a human considers badly derived is deleted
   or edited today; D6 wants it **marked** with an obligatory reason, and the mark needs somewhere
   to live that keeps who marked, when, and whether it was revoked.
5. **Versions must be unremovable.** D12 forbids deleting anything inside a version. The only
   delete path that exists for extractions is `ExtractionRepository.delete`, which has zero
   production callers and one test (`explore.md`); it must not be left as a second way to destroy a
   version.

## Scope

### In Scope

- **Migration `0028`** (chain continues from the verified head `0027`):
  - `extractions.version_number` — `INTEGER NOT NULL`, `CHECK (version_number > 0)`, unique per
    story via `uq_extractions_story_version` on `(user_story_id, version_number)`.
  - `extractions.provider` (`VARCHAR(50) NOT NULL`), `extractions.temperature`
    (`DOUBLE PRECISION NOT NULL`), `extractions.prompt_rendered` (`TEXT NULL`).
  - `tasks.extraction_id` — `UUID NOT NULL`, FK to `extractions.id` with `ON DELETE CASCADE`
    (matching `0014`'s convention for this table family), plus `ix_tasks_extraction_id`.
  - New table **`task_invalidations`** with `id`, `task_id`, `reason`, `marked_by`, `marked_at`,
    `revoked_by`, `revoked_at`.
  - **The migration refuses to run against a non-empty `extractions`/`tasks` table** (see Approach
    step 1).
- **Version identity rules**: D1 (a version is one run), D3 (a task belongs to the extraction that
  produced it, written at task creation), D4 (current version derived, never stored), D22 (every
  run consumes a number; a failed run never becomes current), D12's structural half (no delete path
  for versions).
- **Where the number is minted** and what happens to the dead second persistence path
  (`extraction_service.extract_and_persist`, test-only, creates a fresh row per call).
- **The snapshot write moves to render time**, before the provider answers — the change that makes
  D8 true for the failed versions D22 introduced — plus the column-versus-`prompt_config`-key
  decision for every D8 fact (slice (c) writes the *content* of the new keys).
- **The invalidation mark's storage**: one row per mark event, revoke as an update on that row, at
  most one active mark per task, non-empty reason enforced structurally.

### Out of Scope

**Belongs to the sibling changes (do not build it here):**

- Field-policy matrix for `PUT /tasks/{task_id}`, the `410 Gone` for `DELETE /tasks/{task_id}`, the
  marks endpoints, the owner-or-`ADMIN` permission gate, the story-delete gate with confirmation
  and record, the version selector, the task editor and both confirmations → **slice (b)**.
- Prompt context blocks (project name/description, other stories, existing tasks), negative
  examples, the Qdrant payload keys and filter signature, the two unpaginated context ports, token
  `usage` capture, the 1000-story bench → **slice (c)**.
- Reading the current version as an API filter: after (a) lands, board, export and `GET /tasks`
  still read tasks by `user_story_id`. See "Not independently deployable" in Approach.

**Outside 0.9.0 entirely (recorded so they are not reopened):**

- LLM-as-a-Judge and per-task scores; side-by-side comparison of two versions; grouping runs into
  named experiments; **batch extraction** (closed as a non-goal on 2026-09-25, `POST /batch` does
  not exist); comparison-metrics views and timing middleware; fuzzy/vector propagation of the
  invalid mark; any `priority` editor; and removing `priority` from the contract
  (`TaskResponse`, export, column) — a separate `BREAKING` release, D21 follow-up.

## Capabilities

### New Capabilities

| Capability | This slice writes | Extended later by |
| --- | --- | --- |
| `extraction-versioning` | Version identity and numbering (D1, D22), task→run membership (D3), current-version derivation with no stored flag (D4), run snapshot storage (D8 storage half), no delete path for versions (D12) | (b): API field policy, selector, permissions. (c): snapshot content, context ports |
| `task-invalidation` | The mark's storage: reason required, actor and timestamps, revoke recorded on the same row, at most one active mark per task | (b): marks endpoints, confirmations, owner/`ADMIN` gate, editor. (c): negative-example block, Qdrant `has_invalid_tasks` |

### Modified Capabilities

**None in this slice.** The nine archived capabilities describe HTTP, UI and vector behavior —
`extraction-workflow` (frontend extraction client, error surfacing, 401), `kanban-board`,
`task-editor`, `export-download`, `few-shot-retrieval`, `vector-store-isolation`,
`few-shot-config`, `embedding-providers`, `onboarding-flow`. None of them asserts anything about
version identity, task provenance, snapshot storage or invalidation records, so none needs a delta
here.

Modifications are **deferred, not forgotten** — the spec phase for the siblings must update:

- **(b)**: `kanban-board`, `export-download` (current-version filter), `task-editor` (read-only
  `title`/`description`, invalidation mark), `extraction-workflow` (extraction restricted to
  owner/`ADMIN`, version visible in the response).
- **(c)**: `few-shot-retrieval` (two exclusions), `vector-store-isolation` (new payload keys).

## Approach

1. **`0028` refuses to guess.** `upgrade()` first counts rows in `extractions` and `tasks`; if
   either is non-zero it raises **before any DDL**, naming D11. Decision: **fail loudly, do not
   default legacy rows to `v1`.** A silent default would mint versions that were never runs and
   would make D8's snapshot a lie about rows that predate the column — and D11 already removed the
   reason to guess, because there is no backfill. The guard also makes the non-nullable
   `tasks.extraction_id` coherent: on an empty table the column is trivially legal, so the operator
   is told to wipe instead of reading a Postgres error. This is why `0028` is safe on an empty
   database and loud on a populated one.
2. **D11 is not this migration.** Wiping the relational data and the two Qdrant collections
   (`storico_extractions_dev`, `storico_extractions_prod`) is a **destructive data operation** with
   its own confirmation and record, executed separately and *before* the deploy that carries
   `0028`. It is not an Alembic step and not part of this change's execution. Cost accepted: the
   production E2E evidence named in D11/C3 is gone for good.
3. **The number is minted where the row is born, atomically.** A new port method
   `ExtractionRepository.create_next_version(extraction) -> Extraction` allocates and inserts in
   one transaction with a single statement —
   `INSERT ... SELECT COALESCE(MAX(version_number), 0) + 1 FROM extractions WHERE user_story_id = :id`
   — and the route (`api/routes/extraction.py`) calls it instead of `save()` for the pending row.
   `Extraction.version_number: int | None` mirrors how `id` already works (domain-side field,
   `None` = not yet minted), with one difference: only this repository method may set it, ever.
   **Concurrency is the unique index, not a convention**: extraction runs as
   `asyncio.create_task` inside the API process (`:246`), so two runs on one story can interleave;
   `uq_extractions_story_version` makes the second insert fail, and the repository recomputes and
   retries a **bounded** number of times (3), then fails the request loudly. The HTTP shape of that
   failure is settled in slice (b); this slice only guarantees it is not silent.
4. **The dead path stops existing.** `extraction_service.extract_and_persist`
   (`:224`, tasks built at `:307-312`, saved at `:301`/`:337`) is test-only and **creates a fresh
   row on every call**, so a second birth path can mint two numbers for one run. Decision: **delete
   it and migrate its tests to the live path** rather than teach it the allocation rule; two
   persistence paths for one lifecycle is the ambiguity D22 cannot afford. The live path
   (`extraction_task.py::_run_extraction`, `id=extraction_id`) is the single birth and retry path.
5. **"Current" is derived, never stored.** No `is_current` column, no materialized view, no
   trigger: the current version is the highest `version_number` of the story whose `status` is
   `completed`, exposed as a read method on the extraction repository
   (`ORDER BY version_number DESC WHERE status = 'completed' LIMIT 1`, served by the unique index).
   A flag can drift; a maximum plus a status filter cannot. While a run is `pending` the previous
   current version stays current; a `failed` top version is offered by the selector (slice (b))
   with its error, never as the current one.
6. **The snapshot is written after render, before the provider call.** The render step is split from
   the generate step so the ordering is visible in the runner:
   `render(...) -> RenderedPrompt` (pure, repository-free, returns the instruction prompt it built)
   then persist `provider`, `temperature`, `prompt_rendered` and the `prompt_config` keys, then
   `generate(...)`. Rejected alternative: returning the rendered prompt from `extract()` — a raised
   `LLMError` would lose it, which is exactly the D22 case this exists for; a callback was also
   rejected because it hides the ordering that must hold. Two consequences must be written down:
   - A `failed` version now has a **complete input snapshot and absent output**
     (`raw_response=""`, no `confidence_score`, no `usage`); the selector must render that honestly.
   - `usage` is the only snapshot key that may legitimately be missing, matching D20.
7. **Terminal writes must carry the whole snapshot.** `ExtractionRepository.save()` reads the row
   and `setattr`s **every** field from the entity
   (`infrastructure/database/repositories/extraction_repository.py:25-32`), so
   `_mark_extraction_failed` (`:577`) and the completed write (`:438`) — which today rebuild an
   `Extraction(...)` and re-read `created_at` by hand (`:425-426`, `_get_created_at:530`) — would
   write `None` over `version_number`, `provider`, `temperature` and `prompt_rendered`. Slice (a)
   must make terminal writes carry the whole snapshot (or mutate the loaded row) and add the
   regression test that a failed run keeps its number and its rendered prompt.
8. **`temperature` gets one source of truth.** `ExtractRequest.temperature` is optional
   (`api/schemas/extraction.py:60`) and the `0.1` fallback lives only in the runner
   (`extraction_task.py:385-388`). The default is resolved once at row birth and written to the
   column and to the LLM config it is passed with, so the version's declared temperature cannot
   disagree with the temperature that ran.
9. **`prompt_config` stays `JSON`, not `JSONB`.** No snapshot key in this slice or in slice (c) is
   indexed or filtered in SQL (the filtered keys of D9/D10 live in the Qdrant payload); Postgres
   reads JSON with `->>` well enough for D20's offline measurement. `0009` is quoted as the pattern
   for the day a key does need indexing — and because `0028` runs on an empty table, that
   conversion is cheap then. Not doing it now avoids an unearned type change.
10. **One writer per fact.** Columns for facts that are one value per run; `prompt_config` keys for
    everything nested or repeated. No fact is stored twice.

   | D8 fact | Home | Written | Slice |
   | --- | --- | --- | --- |
   | version number | `extractions.version_number` (column) | repository, at row birth | (a) |
   | provider | `extractions.provider` (column) | pending insert | (a) |
   | model | `extractions.model_used` (existing column) | unchanged | — |
   | temperature | `extractions.temperature` (column), **removed from the `prompt_config` key set** | pending insert | (a) |
   | rendered prompt | `extractions.prompt_rendered` (column; the composed text the provider received, system block included) | render-time write | (a) column, (c) template variables |
   | system prompt | `prompt_config.system_prompt` key (already exists) — **no column**, it would duplicate `prompt_rendered` | render-time write | (a) |
   | validation flag | `prompt_config.validate` key (unchanged) | pending insert | (a) |
   | few-shots with text | `prompt_config.few_shots` key | render-time write | (c) content |
   | project context used | `prompt_config.project_context` key | render-time write | (c) content |
   | story text as sent | `prompt_config.story_text` key | render-time write | (c) content |
   | token usage | `prompt_config.usage` key (optional) | after the provider answers | (c) |
   | omitted negative examples | `prompt_config.negative_examples_omitted` key | render-time write | (c) content |

11. **The invalidation mark is a table, not two columns.** One row per mark event:
    `task_id` (FK → `tasks.id`, `ON DELETE CASCADE`), `reason` (`VARCHAR(500) NOT NULL`, bounded
    like the project's other user text, `CHECK (btrim(reason) <> '')` so "no reason, no mark" is a
    database invariant, not a UI rule), `marked_by`/`revoked_by` (`UUID NULL`, FK → `users.id` with
    `ON DELETE SET NULL`, matching the repo's existing attribution convention for
    `projects.created_by` — the mark and its reason survive account deletion, only the actor
    reference is nulled), `marked_at`/`revoked_at` (`TIMESTAMPTZ`), a `CHECK` that both revoke
    fields are null or both non-null, and a **partial unique index `(task_id) WHERE revoked_at IS
    NULL`** so a task can never hold two active marks. Revoking is an update, never a delete; the
    row (and its history) is the record D6 asks for. Rejected alternative: `is_invalid` +
    `invalid_reason` columns on `tasks` — simpler, but it cannot record who revoked a mark or when,
    and D6 requires the revoke history.

    > **[Superseded 2026-09-30, task 4.4 / D-a-2 — Option A, owner's choice.]** `revoked_by` ships as
    > `ON DELETE RESTRICT`. The equivalence CHECK makes a nulling delete fail anyway, so `RESTRICT` is
    > the same refusal with the right constraint named. `marked_by` keeps `SET NULL` as described here.
    > Normative text: `specs/task-invalidation/spec.md`.
12. **No delete path for versions.** Port and implementation of `ExtractionRepository.delete` are
    removed with its single test; the only deletion of an extraction remains the story-delete
    cascade (D15). The `410 Gone` for `DELETE /tasks/{task_id}` is HTTP contract and stays in
    slice (b).
13. **Slice (a) is a reviewable unit but not independently deployable.** Board, export and
    `GET /tasks` still read tasks by `user_story_id` until slice (b) applies the current-version
    filter, so a second run on a story shows both versions' task sets. Plan: (a) and (b) ship in the
    same release; do not deploy (a) alone. The same note covers the manual
    `POST /api/v1/tasks/` route, which cannot satisfy a `NOT NULL` `extraction_id` and is left
    untouched for (b) to retire — no user is exposed because (a) is not deployed.
14. **Review workload forecast.** This slice is expected to exceed the 400-line budget (migration,
    two models + two entities, repository allocation with retry, service split, route and runner
    changes, deletion of the dead path, plus DB-level tests). Candidate work units for the tasks
    phase: (1) migration + models/entities, (2) number allocation + dead-path removal,
    (3) render-time snapshot, (4) invalidation table + invariants. The delivery decision stays with
    `ask-on-risk`; nothing here preselects a chain strategy.

## Affected Areas

| Area | Impact | Description |
| --- | --- | --- |
| `backend/src/storico/infrastructure/database/alembic/versions/0028_extraction_versioning.py` | New | Columns, unique/index constraints, `task_invalidations`, `tasks.extraction_id`, empty-table guard |
| `backend/src/storico/infrastructure/database/models/extraction.py` | Modified | `version_number`, `provider`, `temperature`, `prompt_rendered` |
| `backend/src/storico/infrastructure/database/models/task.py` | Modified | `extraction_id` FK + index |
| `backend/src/storico/infrastructure/database/models/task_invalidation.py` | New | ORM model with the partial unique index and checks |
| `backend/src/storico/domain/entities/extraction.py` | Modified | `version_number` (None = unminted), snapshot fields |
| `backend/src/storico/domain/entities/task.py` | Modified | `extraction_id` |
| `backend/src/storico/domain/entities/task_invalidation.py` | **Not in this slice** | The mark's domain entity and its repository port are slice (b)'s, with the endpoints that need them; (a) ships the table and the ORM model only (see `design.md`, "Seams for Slices (b) and (c)") |
| `backend/src/storico/domain/ports/extraction_repository.py` | Modified | `create_next_version`, current-version read; `delete` removed |
| `backend/src/storico/infrastructure/database/repositories/extraction_repository.py` | Modified | Single-statement allocation + bounded retry, current-version query, terminal-write field preservation; `delete` removed |
| `backend/src/storico/infrastructure/database/repositories/task_repository.py` | Modified | Persist `extraction_id` |
| `backend/src/storico/api/routes/extraction.py` | Modified | Pending row born through `create_next_version`, temperature default resolved once |
| `backend/src/storico/infrastructure/tasks/extraction_task.py` | Modified | Render/generate split, render-time snapshot write, terminal writes carry the snapshot, tasks carry `extraction_id` |
| `backend/src/storico/domain/services/extraction_service.py` | Modified | `extract` split into render + generate; `extract_and_persist` deleted |
| `backend/tests/**` | Modified | Migration guard/DB invariants, allocation race, failure snapshot, dead-path tests migrated |

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| (a) deployed alone shows two task sets per story | High | Ship (a) with (b) in one release; stated as a hard sequencing rule, not a preference |
| `0028` blocks on environments that still hold data | High | The failure is the point; document the D11 wipe order (wipe → deploy) in the change notes and the deploy runbook |
| Terminal rebuilds silently null the new columns | High | Step 7: every terminal write carries the snapshot; regression test: a failed run keeps its number and rendered prompt |
| Snapshot-at-render changes the service contract and breaks tests | Medium | Render/generate split with an explicit `RenderedPrompt`; migrate the deleted path's tests in the same work unit |
| Deleting `extract_and_persist` loses coverage it was providing | Medium | Rewrite its cases against the live runner path rather than dropping them |
| Concurrent runs collide on the version number | Low | Unique index is the mechanism; bounded retry, then a loud failure |
| Mixed legacy/new `prompt_config` shapes | Low | Impossible by construction: the migration refuses a non-empty table |
| Reviewers read "JSON, not JSONB" as an oversight | Low | Step 9 records the decision and the `0009` precedent |
| A run that dies before render keeps `prompt_rendered = NULL` | Low | `NULL` means "never rendered" and is never backfilled; slice (b) renders it honestly |

## Rollback Plan

- Revert `0028` with its `downgrade()` (drop `task_invalidations`, drop `tasks.extraction_id` and
  its index, drop the four columns and the unique constraint). Destructive for version identity,
  which is acceptable **only** while no production extraction history exists — true by D11 on prod,
  and the reason the sibling slices must not be live when a rollback is needed.
- Revert the render/generate split and restore the post-provider `prompt_config` write; restore the
  pending insert's `temperature` key and drop the temperature resolution.
- Restore `ExtractionRepository.delete` and `extract_and_persist` if the revert has to be complete.
- Nothing in this slice touches Qdrant, so there is no vector rollback.
- **The D11 wipe is not reversible** and is not part of any rollback: the deleted evidence (C3) does
  not come back.

## Dependencies

- Alembic chain from the verified head `0027`; nothing else in flight may claim `0028`.
- The D11 data wipe, executed as its own confirmed operation **before** the deploy that carries
  `0028` (ADR-005's maintenance window: migrations run between `docker stop` and `docker run`).
- Siblings (**b**) `extraction-versioning-api` and (**c**) `extraction-versioning-prompt` depend on
  this schema; both read `explore.md` as the shared evidence base.
- Source decisions D1, D3, D4, D6, D8, D11, D12, D22 (this slice) and D5, D9, D10, D13, D15, D17,
  D19, D20, D21, D23 (siblings).
- No new runtime dependency, no new setting, no new endpoint.

## Success Criteria

- [ ] `0028` applies cleanly to a database with empty `extractions`/`tasks`, and **refuses** before
      any DDL on a populated one.
- [ ] `uq_extractions_story_version` exists and a duplicate `(user_story_id, version_number)` insert
      fails.
- [ ] Two concurrent runs on one story receive two different numbers; the losing insert recomputes
      and succeeds within the bounded retry.
- [ ] Every run that reaches the row-creating endpoint consumes a number; a `failed` run keeps it
      and is never the current version.
- [ ] The current version is derived by query only — no `is_current` column, flag, trigger or
      materialized view exists after `0028`.
- [ ] Every task created by an extraction carries a non-null `extraction_id` pointing at the
      extraction that produced it.
- [ ] A failed run has a complete input snapshot (`provider`, `temperature`, `prompt_rendered`,
      `system_prompt`) and absent output; `prompt_rendered = NULL` occurs only for runs that never
      rendered.
- [ ] The declared `temperature` equals the temperature passed to the LLM call on every path.
- [ ] `task_invalidations` rejects an empty/whitespace reason and cannot hold two active marks for
      one task; revoking updates the row and never deletes it.
- [ ] No product path deletes a version or a task inside a version: `ExtractionRepository.delete`
      and `extract_and_persist` are gone and nothing mints a second row per run.
- [ ] `cd backend && conda run -n storico python -m pytest` is green, with the migrated cases that
      used to cover `extract_and_persist`.
