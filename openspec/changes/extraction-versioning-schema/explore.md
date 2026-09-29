# Exploration: extraction-versioning-schema

> **Change**: `extraction-versioning-schema` — slice (a) of three
> **Depends on**: nothing (root slice)
> **Source spec**: `~/Developer/storico` vault note *"Storico — versionado de extracción y
> tareas inválidas"* (feature 0.9.0, decisions D1–D23)
> **Created**: 2026-09-28

This file is **step 1 of the source spec's "Siguiente paso"**: the spec was measured against
`v0.8.0` + 41 commits (`HEAD` `475964c`) and its note demands that the measurements behind
**D16–D23** be re-checked against whatever is on `main` before 0.9.0 is worked, because those
measurements carry decisions and are not decoration.

## What `main` is, and why the code measurements could not have moved

Measured against `HEAD` `ecea3e2a56291015c50c2203f34c7ec13c491923`, branch `main`,
**42 commits past `v0.8.0`** (`git rev-list --count v0.8.0..HEAD` = 42).

The single commit past the spec's `475964c` is documentation-only:

```
$ git diff --stat 475964c..HEAD
 AGENTS.md            |  6 +++---
 docs/architecture.md | 12 +++++++-----
 docs/deployment.md   |  2 +-
 3 files changed, 11 insertions(+), 9 deletions(-)
```

So **no source file moved** between the spec's measurement and this one. Every verdict below is
therefore a check of the spec's *earlier verification pass*, not a check of new commits. That is
the useful outcome: a claim that fails now failed then too.

## Method

Three bounded read-only scouts (`gentle-ai-explore`, no write authority) over
schema/row-lifecycle, HTTP API/permissions, and prompt/vector, plus targeted parent re-reads of
every claim that touched a decision premise. All citations below are **current at `ecea3e2`**.

## Verdict: the premise of the feature survives

`Extraction` has no version and no order; `Task` hangs off `user_story_id`; the prompt template
takes only `user_story` and `examples`; the Qdrant payload has exactly 7 keys; nothing about
validity exists in any store. The three gaps the feature exists to close are all still there.

### Confirmed (unchanged, with current evidence)

| Spec claim | Evidence at `ecea3e2` |
| --- | --- |
| Alembic head is `0027`; new migrations start at `0028` | `infrastructure/database/alembic/versions/0027_drop_few_shot_examples.py:43-44` (`revision = "0027"`, `down_revision = "0026"`); no revision declares `down_revision = "0027"` |
| `Extraction` has no version/order column, no "current" flag | `domain/entities/extraction.py:21-38` — fields are `user_story_id, model_used, raw_response, status, user_story_status, error_info, prompt_config, confidence_score, id, created_at, completed_at` |
| `Task` hangs off `user_story_id` | `domain/entities/task.py:23`; `infrastructure/database/models/task.py:23-25` |
| `Task` has no natural key: `uuid7` pk, two **non-unique** indexes | `models/task.py:22` (`default=uuid7`), `:48-51` (`Index("ix_tasks_user_story_id", …)`, `Index("idx_tasks_status", …)`) — no `UniqueConstraint`, no title hash |
| `ExtractionStatus` is exactly `pending \| completed \| failed` | `domain/entities/extraction.py:13-18` — **all six re-pinned line numbers in the spec still resolve** (see below) |
| A failed run keeps its row | `infrastructure/tasks/extraction_task.py:131` → `_mark_extraction_failed` (`:577`) `save()`s a FAILED copy; no `delete` in any failure path |
| The row is born `pending` **before** the LLM is called, with `raw_response=""` | `api/routes/extraction.py:230-241`, then `:246` `asyncio.create_task(run_background_extraction(...))` |
| Retry **reuses the same row** | `extraction_task.py:74` loops over one `extraction_id`; `_run_extraction` persists with `id=extraction_id` (`:430-431`) after carrying `created_at` forward (`:425-426`, `_get_created_at` at `:530`) |
| `recover_stuck_extractions` only virals `pending` older than 5 minutes to `failed`; never re-runs; never touches `failed` | `extraction_task.py:166` (`max_age_minutes: int = 5`), `:176`, `:187-193` |
| `extractions.user_story_id` and `tasks.user_story_id` are `ON DELETE CASCADE`, from `0014` | `models/extraction.py:25`, `models/task.py:24`; `alembic/versions/0014_add_cascade_deletes.py` recreates both FKs with `ondelete="CASCADE"` |
| `extractions.created_at` **and** `completed_at` both exist (D20's duration needs no new column) | `models/extraction.py:52`, `:56-58`; `completed_at` added by `0023_add_completed_at_to_extractions.py`; written at `extraction_task.py:444`, `:508`, `:602`, `:201` |
| `Extraction.prompt_config` is **JSON**, not JSONB | `models/extraction.py:9` imports `JSON`, `:49` `mapped_column(JSON, …)`; born `sa.JSON()` at `alembic/versions/0001_initial_schema.py:111`; `prompt_config` appears in **no** later migration |
| JSON→JSONB precedent exists | `0009_align_schema_drift_workspace_id_and_jsonb.py` — `op.alter_column(..., existing_type=sa.JSON(), type_=postgresql.JSONB(), postgresql_using="few_shot_examples::jsonb")`; that column had been born as JSON in `0007_add_workspaces.py:100` |
| `tasks.priority` defaults to `medium` and the extractor never sets it (D21) | `domain/entities/task.py:26`; `models/task.py:38`; the production `Task(...)` at `extraction_task.py:450-456` omits `priority`; the only `priority=` writes are manual CRUD (`api/routes/tasks.py:117,298`) |
| The parser never populates `dependencies` (D5's "Origen: Usuario" is by construction) | `infrastructure/llm/task_parser.py:90-94` `_extract_labels`; `ParsedTask(...)` built at `:127-131`, `:152-156`, `:174` — `dependencies` is never passed, so it stays `()` |
| Labels do come from the LLM, through `[brackets]` | `task_parser.py:90-94`; assigned at `extraction_service.py:311` and `extraction_task.py:454` (`labels=list(pt.labels)`) |
| `UpdateTaskRequest` accepts `title` and `description` today (C10 is a real contract change) | `api/schemas/task.py:25-35` — `title, description, status, priority, labels, dependencies`, `extra="forbid"` |
| `DELETE /api/v1/tasks/{task_id}` is a real delete, with zero frontend callers (D17) | `api/routes/tasks.py:320` (204) → `:336` `repo.delete`; no `deleteTask` anywhere in `frontend/src` |
| `ExtractionRepository.delete` has zero production callers and one test (D17) | port `domain/ports/extraction_repository.py:53-56`; impl `repositories/extraction_repository.py:123-134`; only caller `backend/tests/test_repositories/test_extraction_repo.py:416,420` |
| 410-Gone mechanism precedent exists (D17) | `api/routes/extraction.py:68-91` `deprecated_extract` and `api/routes/projects.py:35-59` `deprecated_projects`: `@router.api_route(..., status_code=status.HTTP_410_GONE)` + `raise ApiError(status_code=410, error_code=<X>_ENDPOINT_REMOVED, detail=…)`; envelope `{detail, error_code}` from `api/errors.py:81-86`; codes declared in `api/error_codes.py` |
| `POST /api/v1/tasks/` exists with membership-only access and no frontend caller (D3) | `api/routes/tasks.py:89-114` |
| Extract is open to any member today (D13 restricts a deployed capability) | `api/routes/extraction.py:154` `Depends(get_workspace_for_user)`; the role is discarded at `:178` (`workspace, _ = ctx`) |
| The permission gate lives in `extraction.py` (**singular**); `extractions.py` is read-only | `extraction.py:96` `extraction_router` (POST `/` 202, GET `/status/{id}`); `extractions.py:27,79,166` — two GETs only |
| No dependency expresses "owner **or** `ADMIN`" (D13 needs new code) | `api/dependencies.py:209` `get_workspace_for_user` (membership only), `:243` `require_admin` (`role != ADMIN` → 403), `:261` `require_owner` (chains `Depends(require_admin)` **then** `workspace.owner_id != current_user.id`) → owner-or-admin is code **new** to `dependencies.py` |
| Roles are only `ADMIN`/`MEMBER`; owner is `Workspace.owner_id` | `domain/entities/workspace_member.py:17-21`; `domain/entities/workspace.py:22` |
| `DELETE /stories/{story_id}` needs membership only — a `MEMBER` can already destroy the whole history (D15) | `api/routes/stories.py:290-309`, gated by `require_story_workspace_access` (`dependencies.py:280`, membership only) with cascade `:309` `repo.delete` |
| `PUT /stories/{story_id}` keeps four fields, no `title`/`description` (D14) | `api/schemas/story.py:24-32` (`actor`, `feature`, `benefit`, `raw_text`, all `max_length`-bounded), route `api/routes/stories.py:245` |
| Pagination defaults 20 / cap 100 (D9's silent-truncation hazard) | `api/schemas/common.py:9-10` — **and the cited line numbers still match** |
| No unpaginated project-scoped read for stories or tasks (D23) | `UserStoryRepository.list_page` `:41` (paginated), `list_parts_by_project` `:161-170` (returns `actor, feature, benefit, id` only), `list_by_workspace` `:135`; `TaskRepository.list_page` `:52`, `list_by_story` `:120`, `list_by_workspace` `:125` — **`TaskRepository` has no project-scoped read at all** |
| Task dedupe / title normalization does not exist (D16) | only task-title `casefold()` in the backend is `api/routes/export.py:45`, used to resolve dependency references at `:49`, not to dedupe; story dedupe key is `(actor, feature, benefit)` (`domain/services/story_import.py` `_story_key`, `validate_import`) |
| i18n already promises no single-task deletion (D17) | `frontend/src/i18n/en.json:132` `landing.faq.a4` "…but **Storico does not delete a single task**…"; `frontend/src/i18n/es.json:132` "…pero **Storico no elimina tareas una por una**…" |
| State machine still governs task status (D5) | `domain/validators/state_machine.py:28-36` `VALID_TASK_TRANSITIONS`, `:49-58` (self-transition allowed); production caller `api/routes/tasks.py:277` → `application/services/task_service.py:30,37` |
| `priority` is in the API output and only in the JSON export (D21) | `api/schemas/task.py:48`; `api/routes/export.py:118-123` (JSON via `model_dump`) vs `_build_markdown` `:38-72` (never references priority); formats are exactly `json`/`markdown` |
| The prompt template takes only `user_story` and `examples` (D9 changes the render contract) | `infrastructure/llm/prompts/task_generation.j2:18-20` (`{% if examples %}`/`{{ examples }}`) and `:26` (`{{user_story}}`); renderer `domain/services/extraction_service.py:145-152` passes exactly those two |
| Only an **output** cap exists on the LLM call | `domain/ports/llm_port.py:15` `max_tokens: int = 2048`; pinned again in the runner at `extraction_task.py:385-388` (which **ignores** `workspace_llm_config.max_tokens`, `domain/entities/workspace_llm_config.py:28`) |
| `search_similar` cannot express D10's exclusions | `domain/ports/vector_store_port.py:25-32` — `(self, text, limit=3, threshold=0.85, *, workspace_id)`; `ExtractionExample` `:13-20` carries no id and no validity field |
| The only Qdrant filter is workspace-keyed, with no `must_not` | `infrastructure/vector/qdrant_adapter.py:125-137` `_build_workspace_filter` → `Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(…))])`; `:131` is the only `Filter(` construction site in the vector directory; no `must_not` / `min_should_match` anywhere in it |
| Qdrant payload is exactly **7** keys; none of D9/D10's three additions exist | `qdrant_adapter.py:257-265` — `user_story_text, tasks_summary, model_used, workspace_id, confidence_score, user_story_id, created_at`; pinned by `tests/test_unit/test_vector_store.py:606-639`; no `project_id`, no `version_number`, no `has_invalid_tasks` |
| Few-shot defaults are `limit=3`, `threshold=0.85`, per workspace | `extraction_service.py:34-44` `FewShotConfig`; runner builds it from `workspace_prompts` at `extraction_task.py:357-361` and passes it at `:396-400` — **the workspace row wins at runtime**; the service default only applies when `None` is passed (`extraction_service.py:120`) |
| The in-flight point is written **after** the search, so what can return as an example is a *previous* run of the same story | search: `extraction_task.py:393` → `extraction_service.py:126` → `:199`; upsert: `extraction_task.py:460` → `:557` → `qdrant_adapter.py:195` |
| No adapter reads provider token usage; nothing logs or persists it (D20) | `ollama_adapter.py:159-165` (`data["message"]["content"]`), `openai_adapter.py:124`, `anthropic_adapter.py:104-107`, `gemini_adapter.py:81`; repo-wide grep for `usage\|prompt_eval_count\|eval_count\|usageMetadata\|prompt_tokens\|completion_tokens\|total_tokens` → **zero matches in source or tests**; `ExtractionResult` (`domain/ports/llm_port.py:35`) has `tasks, raw_response, confidence_score` and no usage field, and there is no `LLMResponse`/`GenerationResult` type |
| No timing middleware; `latency_ms` lives only in health probes and the LLM connection test (D20) | `api/routes/health.py:55,59,69,99,115,122,144,150,196,200,214,219`; `api/routes/settings.py:154` `time.monotonic()` → `:181,188,214,221,247,254,280,287,321,328`; `api/schemas/settings.py:123`; `api/app.py:141-142` adds only `CORSMiddleware` |
| `Project.description` cap is 500 | `api/schemas/project.py:18` and `:28` |

### The six re-pinned line numbers

The spec's second correction note says the document cites six line numbers and that all six
were re-pinned against `475964c` and coincided. Re-checked against `ecea3e2`: **all six still
resolve to what they name.**

| Citation | Resolves to |
| --- | --- |
| `domain/entities/extraction.py:13-18` | `class ExtractionStatus(StrEnum)` + its three members |
| `domain/ports/llm_port.py:15` | `max_tokens: int = 2048` |
| `api/schemas/common.py:9-10` | `page` default 1, `size` default 20 / `le=100` |
| `infrastructure/tasks/extraction_task.py:387` | `max_tokens=2048,` inside the runner's `LLMConfig(...)` |
| `infrastructure/tasks/extraction_task.py:131` | `await _mark_extraction_failed(extraction_id, str(exc))` |
| `infrastructure/database/models/extraction.py:49` | `prompt_config: Mapped[dict \| None] = mapped_column(JSON, nullable=True, default=None)` |

---

## Four measurements that do **not** survive

These are the ones the spec's next step asked to be re-checked because they carry decisions.
Each is recorded with the decision it touches and what the change has to do about it.

### Δ1 — `MAX_ROWS = 1000` is a **per-file** cap, not "1000 stories per project" (touches D9, D20, D23)

`infrastructure/parsers/story_csv.py:23` defines `MAX_ROWS = 1000` and enforces it at `:143`
**inside the parser**, while the file is being read:

```python
if len(rows) >= MAX_ROWS:
    raise StoryCsvError("too_many_rows")
```

`api/routes/stories.py:410` only uses the constant to fill in an error detail
(`detail["max"] = MAX_ROWS`). There is **no per-project quota anywhere**. The write is one
transaction per upload (`user_story_repository.py:151-166` `save_many`, one `add_all` + one
`commit`), so a project can cross 1000 stories by importing a second file.

**Effect on the decision.** D9's "el proyecto entero entra completo, sin tope" gets **worse**,
not better: the multiplier the spec discovered is not even an upper bound. D23's mandatory test
at 1000 stories is therefore a **floor**, not a ceiling, and the change must say so instead of
implying 1000 is the worst case.

### Δ2 — the extraction path has no input cap, but each story is capped at 2000 chars upstream (touches D9, D20)

`extraction_service.py:112` reads `raw_text` and passes it to the template with no length
operation, and no truncation exists in `infrastructure/llm/`. That half of the claim holds.
The absolute phrasing ("no input-size limit anywhere") does not: the story text is bounded at
creation and at import —

- `api/schemas/story.py:20` `raw_text: str = Field(..., max_length=2000)` (and `:31` on update)
- `domain/services/story_import.py:35` `FIELD_LIMITS = {"actor": 100, "feature": 300, "benefit": 300, "raw_text": 2000}`

**Effect on the decision.** The unbounded dimension is the **number of items**, not their size.
Worst case for one project is roughly `stories × 2000 chars` plus every existing task title —
the arithmetic is in D20's own bench, and the change must state the bound where the spec said
there is none.

### Δ3 — the per-run statement count is about **double** the spec's estimate (touches D23's cost argument)

The spec's D23 argues "a run issues ~8 fixed statements plus one per generated task, so D9's
context is two more". Tracing the call sites at `ecea3e2` gives **≈16 fixed + ≈2 per task**:

- request phase (`api/routes/extraction.py:165-246`): auth user (`dependencies.py:98`) +
  workspace (`:225`) + membership (`:232`) + story (`extraction.py:120`) + project (`:124`) +
  LLM config (`:206`) + the pending `save` = **≈7–8**
- background phase (`extraction_task.py:283-475`): story load `:312`, story→EXTRACTING `save`
  `:327`, workspace-prompt resolve `:337`, `_get_created_at` `:431`, extraction `save` `:446`,
  task `save` `:457` (×N), final story transition `:475` = **≈9 fixed**

Two structural reasons the spec undercounted: **every repository `save()` is two round-trips**
(a `session.get` SELECT plus a COMMIT — `repositories/extraction_repository.py:25,32`,
`task_repository.py:25,32`, `user_story_repository.py:26,34`), so persisting N tasks costs ~2N,
not N; and `ExtractionModel.user_story` (`models/extraction.py:58-60`) plus
`UserStoryModel.project/tasks/extractions` (`models/user_story.py:51-59`) are `lazy="selectin"`,
which adds SELECTs not visible in a call-site count. The spec already flagged this figure as
"estimado leyendo, no medido en runtime", so it is a correction of an honest estimate, not of a
measurement.

**Effect on the decision.** None: D23 adds **two** statements regardless of the baseline, and
"2 of ~26" is a smaller share than "2 of ~13". The conclusion ("no se toca `pool_pre_ping`",
debt 2 stays open by decision) stands. What must change is the arithmetic quoted in the thesis —
it should not repeat "8 + 1/task" as a measured fact.

### Δ4 — a **failed** version stores almost none of D8's snapshot, and the spec never says who writes it (touches D8, D22, C9)

`prompt_config` is written with **different key sets depending on the row's fate**:

| Path | Keys actually stored |
| --- | --- |
| pending insert — `api/routes/extraction.py:236-239` | `{validate, temperature}` |
| completed — `infrastructure/tasks/extraction_task.py:438-442` | `{validate, temperature, system_prompt}` |
| failed / stuck — `extraction_task.py:199`, `:506`, `:600` | copies `pending.prompt_config` → `{validate, temperature}` |

Combined with D22 (a failed run keeps its number forever) and D4/D22's selector behaviour (the
board offers the failed version with its `error_info`), the spec's D8 promise — "*cada versión
congela todo lo que hace falta para leerla y reproducirla después*" — is **false for exactly the
versions D22 introduced**. A `failed` version would carry no provider, no rendered prompt, no
few-shots, no project context and no story text, because nothing in the current code writes
them before the provider answers.

**Effect on the decision.** This is not a drift in a measurement; it is a hole the measurement
opened, and it is the reason slice (a) cannot ship `version_number` alone. The change must place
the snapshot write **before the provider call, after render**, so a run that dies still has the
prompt it was given. Consequences that must be written down, not discovered later:

- a `failed` version has a **complete input snapshot** and **absent output** (`raw_response=""`,
  no `usage`, no `confidence_score`) — the selector has to render that honestly;
- `usage` is the **only** snapshot key that may legitimately be missing, because a call that
  never answered has no token counts, and D20 already says "si el proveedor no lo devuelve, la
  clave se omite y queda anotado";
- the render-time write is what makes the extra `prompt_rendered` column cheap (it is already in
  memory at that moment) and what makes D22's burned numbers legible.

## Two imprecisions worth correcting in the spec, no decision attached

- **"13 entidades, 15 puertos: confirmados"** — the 15 ports are right
  (`domain/ports/`, 16 files, one `__init__.py`, each an `ABC`). The 13 is a **file count**: it
  includes `domain/entities/exceptions.py` (18 exception classes, not entities). Twelve modules
  define entities; the rest are two variant dataclasses (`ProjectWithCount`,
  `WorkspaceWithRoleAndCount`) and four enums.
- **D8's "proveedor, tokens y prompt renderizado no existen en ningún lado"** is right about
  provider and tokens, and right that the *rendered instruction* is not stored — but the
  **system prompt is**, inside `prompt_config` on completed rows (`extraction_task.py:441`). The
  snapshot work should not double-store it.
- The JSON→JSONB precedent (`0009`) still exists as a migration, but `0027` **dropped the very
  column it converted** (`op.drop_column("workspace_prompts", "few_shot_examples")`). Quote the
  pattern, not the column.
- The spec's "estado del código hoy" table says the task editor edits four fields. It edits
  **five**: `TaskEditor.tsx` renders title, description, labels, dependencies **and a `status`
  select**, and sends all five through `updateTask` → `PUT /api/v1/tasks/{id}`
  (`stores/taskStore.ts:399-434`, `lib/tasks-api.ts:74-81`). `priority` appears nowhere in it.
  D5's "status editable" therefore already matches the UI; only title/description are a
  restriction.

## One structural hazard for the implementer of this slice

There are **two** extraction persistence paths in the codebase, and only one is live:

- production: `extraction_task.py::_run_extraction` — reuses the row (`id=extraction_id`),
  which is exactly what D22's "retry does not mint a second number" needs;
- **dead, test-only**: `extraction_service.py::extract_and_persist` (`:224`, task build at
  `:307-312`, save at `:301`/`:337`) — creates a **fresh row** on every call.

If `version_number` is allocated anywhere other than the row's birth in the route, the dead path
can mint two numbers for one run. Slice (a) has to state where the number is assigned and what
happens to `extract_and_persist`.

## Slice scope of this change

Schema and identity only: D1, D3, D4, D12's storage, D22, and the storage half of D6 and D8.
The HTTP contract, permissions and UI are `extraction-versioning-api`; the prompt, context,
snapshot content and few-shot exclusions are `extraction-versioning-prompt`. Those two changes
read the ledger above; this file is the shared evidence base for all three.
