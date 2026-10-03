# Tasks: Extraction Versioning — Prompt Context, Snapshot Content and Few-Shot Exclusions

Slice (c) of three for Storico 0.9.0. Planning artifact only: every line below is unchecked and no
line claims a check that has not run. Evidence base: `explore.md` (this change), the shared ledger
`../archive/2026-09-30-extraction-versioning-schema/explore.md` (`main` `ecea3e2`, Δ1–Δ4), the four `specs/` deltas
(22 requirements), the 13 design decisions with their four accepted `(correction)` reconciliations,
slice (a)'s `tasks.md`, slice (b)'s `tasks.md`, and `openspec/config.yaml`
(`strict_tdd: true`, `rules.tasks.protect_review_workload: true`).

Runners: backend `cd backend && conda run -n storico python -m pytest` (unit
`-m "not integration"`, integration `-m integration`). `python -m` is required because the conda env
exposes no bare console scripts (`AGENTS.md` §0); the `commands.integration` line in
`openspec/config.yaml` omits `python -m` and is the stale one. There is **no frontend work in this
slice** and no browser verification — frontend E2E is not runnable (`@playwright/test` is not a
devDependency) and (c) has no UI.

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | ≈2,500–3,400 for the whole slice (`additions + deletions`) |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | WU1 (ports + context argument) → WU2 (snapshot + usage) → WU3 (few-shot exclusions + mark refresh) → WU4 (benches), each with its named intra-unit split axis; chain selection pending |
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
Chain strategy: chained PRs, one PR per work unit, split on this slice's own axes
size:exception: accepted for (a) WU1, (b) WU2 and (b) WU4 only
```

- **This slice takes no `size:exception`, and needs none.** Its three large units chain on the split
  axes already named in the Per-Work-Unit Estimate table: WU1 into ports + repositories, then
  `ProjectContext` + the `render()` argument with its call-site churn, then the two template blocks;
  WU2 into the negative-example composer + snapshot dictionary, then the `usage` types + four adapters
  + `record_usage`; WU3 into the payload keys + indexes, then the filter + `search_similar`
  signature, then the point-id setter + refresh order + `count_active_for_extraction`. The largest
  atomic commit inside them — the `LLMResponse` ripple, ≈305 lines — fits under 400.
- **The chain has one hard internal ordering.** Inside WU3 the payload keys and their indexes must
  land in an earlier PR than the fail-closed `must: has_invalid_tasks = false`. Reversed, every
  pre-existing point becomes silently unretrievable instead of failing loudly. This is a merge-order
  constraint, not a suggestion.
- **One dependency this slice cannot discharge alone:** tasks 3.6–3.8 edit slice (b)'s handler file,
  so (b)'s mark endpoints (its WU5) must be merged before (c)'s refresh PR opens.
- **WU4 is not a code PR.** The two benches and the verification note are operator-run against real
  infrastructure; the artifact is `verify-report.md`. A provider rejection at the 1000-story bench is
  recorded there as a finding — it does not authorize a cap, a truncation or a paginated read, and it
  is not a red test to retry until green.

### Per-Work-Unit Estimate

These are `additions + deletions`, built from the design's File Changes table plus the test lines the
pinned scenarios force (prompt content, filter shape, payload keys, snapshot key set, usage per
adapter).

| Unit | Design unit | Estimated changed lines | Fits 400-line budget? |
|------|-------------|-------------------------|------------------------|
| WU1 — the project enters the prompt: two ports + two repositories + `ProjectContext` + the required `context` argument + the two template blocks + the required-argument churn | WU1 | ≈750–1,000 (≈320 / ≈230 / ≈240 across its three split parts) | **No as one unit** |
| WU2 — what the version records: the negative-example composer, the snapshot dictionary, the marks read, the `usage` types, the four adapters, `record_usage` | WU2 | ≈750–1,000 (≈240 / ≈300 / ≈305 across its three split parts) | **No as one unit** |
| WU3 — few-shot exclusions and the mark's vector consequence: signature, filter, payload keys, indexes, the point-id setter, the refresh order, `count_active_for_extraction` | WU3 | ≈900–1,200 (≈200 / ≈250 / ≈320 / ≈180 live-Qdrant across its four split parts) | **No as one unit** |
| WU4 — both benches and the verification note (no source file changes) | WU4 | ≈100–180 | Yes |
| **Slice total** | | **≈2,500–3,400** | **No** |

### (c) has no unsplittable over-400 unit — unlike (a) and (b)

Slice (a) reported **WU1** unsplittable (two `NOT NULL` columns plus `tasks.extraction_id NOT NULL`
break ~32 seed sites with no green intermediate) and slice (b) reported **WU2** (the `extra="forbid"`
pair) and **WU4**'s storage half. **Slice (c) reports none.** Three of its four units breach 400
lines, but each has an honest split axis that ends on a green suite, so the breach is a **sizing and
review-boundary problem solved by chaining**, not a `size:exception` candidate:

- **WU1** splits three ways on dependency order — (i) the two port methods + their repository
  implementations + their repository tests (~320 lines; nothing calls them yet, green), (ii)
  `ProjectContext` + the required `context` argument + the two template blocks + the required-argument
  churn at every `render()` call site (~230 lines, green), (iii) the prompt-content and context
  behavior tests (~240 lines, green).
- **WU2** splits three ways — (i) the composer + its unit table (~240), (ii) the snapshot dictionary
  and the negative-block behavior tests (~300), (iii) `LLMResponse`/`ExtractionResult.usage` + the
  four adapters + the `.text` ripple + `record_usage` (~305; this is the **largest atomic commit in
  the slice**, because `LLMPort.generate`'s return type change breaks all four adapters and all six
  reader sites at once, and it still fits).
- **WU3** splits four ways — (i) the payload keys + indexes + `_store_rag` arguments (~200; must land
  **before** the fail-closed filter or every point silently becomes unretrievable), (ii) the
  `search_similar` signature + `must`/`must_not` filter + call-site churn (~250), (iii) the
  point-id setter + `count_active_for_extraction` + the two handler orders + their tests (~320), (iv)
  the live-Qdrant cases (~180).
- **WU4** fits.

Choosing whether those splits become separate PRs, and which chain shape carries them, is the
delivery decision `ask-on-risk` pauses for; it is not taken here. No chain strategy is preselected
and `size:exception` is not accepted.

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test | Runtime harness | Rollback boundary |
|------|------|-----------|--------------|-----------------|-------------------|
| 1 | The project's name, description, other stories and existing tasks reach the prompt through two new unpaginated ports and one required `render()` input; the template gains both blocks | PR 1 (over budget — split parts i→ii→iii if the pause asks for it) | `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_user_story_repo.py tests/test_repositories/test_task_repo.py tests/test_unit/test_prompt_manager.py tests/test_api/test_extraction.py -m "not integration"` | SQLite in-memory (`sqlite+aiosqlite://`, `backend/tests/conftest.py:36`); the 1000-row read needs Postgres | Delete the two port methods and their repository code, the template blocks and `ProjectContext`; revert `render()` to its single caller shape |
| 2 | The version records `few_shots` with text, `project_context`, `story_text`, `negative_examples_omitted` and the provider's `usage`; the negative-example block is composed, capped at 20 and self-announcing | PR 2 (over budget — split parts i→ii→iii) | `cd backend && conda run -n storico python -m pytest tests/test_unit/test_negative_examples.py tests/test_unit/test_ollama_adapter.py tests/test_unit/test_openai_adapter.py tests/test_unit/test_anthropic_adapter.py tests/test_unit/test_gemini_adapter.py tests/test_api/test_extraction.py -m "not integration"` | SQLite in-memory; FastAPI `TestClient` with a doubled LLM and a recording vector store | Delete `domain/services/negative_examples.py`, restore `generate()`'s two-tuple and `LLMPort.generate -> str`, drop `record_usage` and the extra snapshot keys |
| 3 | Few-shot retrieval loses the story's own run and every invalid-marked extraction inside the filter, the payload grows to ten keys with their indexes, and the validity flag tracks the marks on mark and revoke | PR 3 (over budget — split parts i→ii→iii→iv) | `cd backend && conda run -n storico python -m pytest tests/test_unit/test_vector_store.py tests/test_unit/test_few_shot_retrieval.py tests/test_api/test_tasks.py -m "not integration"` | SQLite in-memory for the port/refresh halves; a reachable Qdrant with `STORICO_TEST_LIVE_QDRANT=1` for the filter semantics | Revert `search_similar`'s signature and filter, drop the three payload keys and the setter, and remove the refresh lines from (b)'s handlers |
| 4 | Both benches run and their numbers, outcomes and the per-provider usage confirmation land in the verification note | PR 4 | none automated — operator-run data operations | Neon-like database + a configured provider; a reachable Qdrant for the imports' RAG path | Delete `verify-report.md`; nothing in the source tree changes |

## Slice Dependencies and Flagged Seams

Consumed unchanged from **(a)**: `record_rendered_prompt` / the render-time write moment and its
ordering (render → write → provider), `prompt_rendered` / `provider` / `temperature` /
`version_number` on the extraction row, `RenderedPrompt.template_variables`, `mark_completed` /
`mark_failed`, `find_current_version`, `tasks.extraction_id` (a 1.12, 1.13, 3.4, 3.5).

Consumed unchanged from **(b)**: `TaskInvalidationRepository.list_active_on_other_versions` (b 5.6)
for D7's block, and the mark/revoke endpoints in `api/routes/tasks.py` (b 5.9) as the refresh's
callers.

**Four seams this file must flag rather than silently assume:**

1. **(b) must call the payload refresh from its mark and revoke endpoints — that call is written here,
   not in (b).** (b) 5.4 and 5.9 create `POST /{task_id}/invalidations` and
   `DELETE /{task_id}/invalidations/current` and never mention `set_has_invalid_tasks`; (b)'s RED
   cases do not test the refresh order. **(c) WU3 tasks 3.6–3.8 add both call sites and their RED
   cases to (b)'s handler.** Until 3.8 lands, (b)'s endpoints are complete but the validity flag
   never moves — an unmarked-in-vector state, not a broken endpoint.
2. **(b)'s story deletion must coexist with (c)'s payload keys.** (b) 4.12's `delete_by_story` filters
   a `FilterSelector` over the `workspace_id` + `user_story_id` payload keys and never reads
   `has_invalid_tasks`, so (c)'s three additive keys do not perturb it, and a point-id refresh cannot
   resurrect a deleted point. Neither file schedules the proof; **(c) WU3 task 3.9 carries it** as a
   live-Qdrant case that deletes a story whose point is flagged.
3. **`version_number` in the runner is owned by neither (a) nor (b) as written.** (a) 2.3 passes only
   `temperature` into `run_background_extraction`; (b) 4.6 only adds `version_number` to the 202
   body. (c)'s design decides the route passes it alongside the temperature. **(c) WU3 task 3.5
   carries the parameter.**
4. **`generate()`'s return type supersedes (a) 3.4.** (a) fixes
   `generate(rendered, config) -> tuple[list[ParsedTask], str]`; usage cannot leave the service
   through a two-tuple, so the accepted amendment is `ExtractionResult`. **(c) WU2 task 2.8 carries
   the one-line change and the one iteration**; (a)'s WU3 may implement the final shape directly.

**Path corrections against the design's tables** (verified at planning time, not silently
substituted):

- `domain/ports/task_invalidation_repository.py`, `infrastructure/database/repositories/task_invalidation_repository.py`,
  `domain/services/task_title_normalizer.py` and `domain/entities/task_invalidation.py` **do not exist
  at `main`** — they are files **(b) creates** at 5.5, 5.6 and 5.7. Tasks below that touch them are
  marked *"(b)'s file"*, and each states what (c) adds.
- Both `backend/tests/integration/` and `backend/tests/test_integration/` exist. The new Postgres-only
  file goes to **`backend/tests/test_integration/test_context_ports_scale.py`**, the home of
  `test_few_shot_rag_qdrant.py` and `test_migration_chain.py`, matching slice (a)'s convention.
- `backend/tests/test_services/test_workspace_prompt_resolution.py` is a `render()`/`extract()` call
  site that **neither design's call-site table names**; (c) WU1 task 1.10 includes it.
- `backend/tests/test_few_shot_examples.py` renders the instruction template directly (three sites)
  and must stay green once the template gains optional blocks — checked in WU1 task 1.15.
- Design's `test_repositories/test_{user_story,task}_repo.py` are correct:
  `backend/tests/test_repositories/test_user_story_repo.py` and `test_task_repo.py` both exist.

## Verification Environments (honest preconditions)

| Layer | Command | Precondition |
|-------|---------|--------------|
| Unit / SQLite | `cd backend && conda run -n storico python -m pytest -m "not integration"` | none; schema from the models on `sqlite+aiosqlite://` (`backend/tests/conftest.py:36`), which **enforces no foreign keys** |
| Postgres | `cd backend && conda run -n storico python -m pytest -m integration` | a Docker daemon (Postgres 16 via testcontainers); without it every case **skips and stays unverified** |
| Live Qdrant | `STORICO_TEST_LIVE_QDRANT=1 cd backend && conda run -n storico python -m pytest tests/test_integration/test_few_shot_rag_qdrant.py` | a reachable Qdrant — Docker Compose in dev, Qdrant Cloud in prod; a skip here **proves nothing** and the flag makes an unreachable service a failure by design |
| Benches | operator-run, no test command | a Neon-like database (never the dev pooler), a configured provider per adapter, and the CSV import path |

## Spec Coverage

All 22 `### Requirement:` headings across the four deltas map to at least one task.

| Requirement (delta) | Covered by |
|--------------------|------------|
| C1 Project name and description as they are at render time (`extraction-context`) | 1.5, 1.7, 1.8, 1.9, 1.15 |
| C2 The project's other stories and existing tasks appear | 1.1, 1.4, 1.7, 1.9, 1.11 |
| C3 The story being extracted never appears as its own context | 1.2, 1.3, 1.7, 1.9, 1.11, 1.14 |
| C4 No invalid task appears as positive context (and revoke restores it) | 1.2, 1.3, 1.7, 1.9, 1.12 |
| C5 Negative examples are all previous versions' marks | 2.1, 2.2, 2.5, 2.6, 2.10 |
| C6 Cap 20, most recent first, deduplicated, self-announcing, no workspace knob | 2.1, 2.2, 2.4, 2.6, 2.10 |
| C7 Context read unpaginated with the exclusion in the query | 1.1, 1.2, 1.4, 1.14 |
| C8 A workspace-authored template opts out of the new blocks | 1.5, 1.6, 1.13 |
| V1 The snapshot carries the few-shots with their text (`extraction-versioning`) | 2.6, 2.7, 2.12 |
| V2 The snapshot carries `project_context` and `story_text`, nothing twice | 2.4, 2.6, 2.7 |
| V3 The snapshot records `negative_examples_omitted` | 2.4, 2.6, 2.10 |
| V4 Token usage stored only when the provider returned it | 2.8, 2.9, 2.11, 4.1 |
| V5 Measurement derives from stored facts, no new instrument | 2.6, 4.2, 4.4 |
| V6 Reproducibility is the stored prompt, not a re-execution promise | 1.7, 2.6 |
| V7 Both bench outcomes are honest and both are recorded | 4.2, 4.3, 4.4, 4.5 |
| F1 Unified few-shot section with both exclusions in the filter (`few-shot-retrieval`) | 3.1, 3.2, 3.3, 3.4, 3.9 |
| F2 A point without the validity flag is not treated as valid | 3.1, 3.3, 3.9 |
| S1 Workspace-scoped retrieval as a positive/negative expression (`vector-store-isolation`) | 3.1, 3.2, 3.3, 3.4 |
| S2 Legacy points excluded, fail-closed on the validity flag | 3.1, 3.3, 3.9 |
| S3 Payload indexes on the three filtered fields | 3.1, 3.3, 3.9 |
| S4 Every stored point carries project, version and validity | 3.1, 3.3, 3.5 |
| S5 The flag tracks the marks, not the write time | 3.6, 3.7, 3.8, 3.9 |

---

## Phase 1: WU1 — The Project Enters the Prompt

Runner for this phase:
`cd backend && conda run -n storico python -m pytest tests/test_repositories/test_user_story_repo.py tests/test_repositories/test_task_repo.py tests/test_unit/test_prompt_manager.py tests/test_api/test_extraction.py -m "not integration"`.
STRICT TDD order: RED first, then GREEN, then TRIANGULATE, then REFACTOR. If the `ask-on-risk` pause
asks for the split, parts i (1.1–1.4), ii (1.5–1.10) and iii (1.11–1.15) each end green.

- [x] 1.1 RED — `backend/tests/test_repositories/test_user_story_repo.py`: add the failing
      `list_for_context` cases. A project with three stories returns the two others for a given
      `exclude_story_id`, never the excluded one; two calls over the same project state return the
      same order (`created_at, id`); a 120-story project returns 119 — past the API's page cap of 100,
      which `list_page` would have applied; **the signature carries no `limit` or `offset`**, asserted
      by `inspect.signature` over both `UserStoryRepository.list_for_context` and its SQLAlchemy
      implementation (the pattern at `backend/tests/test_unit/test_vector_store.py:157-166`). Prove RED
      with
      `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_user_story_repo.py -m "not integration"`.
- [x] 1.2 RED — `backend/tests/test_repositories/test_task_repo.py`: add the failing
      `list_for_context` cases. The excluded story's tasks are absent **in every one of its versions**
      (v1 completed + v2 completed, both sets of tasks in the fixture); a task carrying an active mark
      is absent; the same task is present once its mark is revoked; a superseded version's tasks are
      absent when a newer completed version exists; a `pending` v3 above a completed v2 leaves v2's
      tasks current; the cross-check that `list_for_context(project)` equals the union of (b)'s
      current-version `GET /tasks?workspace_id=` rows for that project's stories over a two-version,
      one-invalid-mark fixture (the currency rule reported in one place); deterministic order; no
      `limit`/`offset` in the signature. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_task_repo.py -m "not integration"`.
- [x] 1.3 GREEN — `backend/src/storico/domain/ports/user_story_repository.py` and
      `backend/src/storico/domain/ports/task_repository.py`: add the frozen slotted
      `StoryContextRow(id, raw_text)` and `TaskContextRow(title, status, user_story_id)` beside their
      ports, plus `list_for_context(project_id, *, exclude_story_id)` on each, with the docstring
      stating that the read is deliberately unbounded and the exclusion rides in the `WHERE`.
      Re-export both row types from `backend/src/storico/domain/ports/__init__.py`.
- [x] 1.4 GREEN — `backend/src/storico/infrastructure/database/repositories/user_story_repository.py`:
      the two-column projection `select(UserStoryModel.id, UserStoryModel.raw_text).where(project_id
      == :p, id != :excluded).order_by(created_at, id)`;
      `backend/src/storico/infrastructure/database/repositories/task_repository.py`: the one statement
      — `tasks JOIN user_stories ON tasks.user_story_id = user_stories.id` (project scoping),
      `JOIN extractions E ON E.id = tasks.extraction_id` with `E.status = 'completed'`, `NOT EXISTS`
      a higher-numbered completed version of the same story, `NOT EXISTS` a
      `task_invalidations` row with `revoked_at IS NULL`, `tasks.user_story_id != :excluded` — with
      **both** exclusions in the `WHERE` and no Python filter.
- [x] 1.5 RED — `backend/tests/test_unit/test_prompt_manager.py`: add the failing template cases
      against the rendered prompt only (no database). The prompt carries the `## Project Context`
      block with the name, the description, each other story's text and each task's title with its
      owning story id; the block order is `## Project Context` → `## Do Not Produce These Tasks
      (Previously Marked Invalid)` → the existing `## Few-Shot Examples` → `User story:`; with
      `negative_examples_omitted > 0` the block closes with the English omission sentence naming the
      count; a workspace `instruction_template` that references only `{{ user_story }}` renders
      **neither** new block (C8's opt-out half). Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_unit/test_prompt_manager.py -m "not integration"`.
- [x] 1.6 GREEN — `backend/src/storico/infrastructure/llm/prompts/task_generation.j2`: add the
      `## Project Context` block and the `## Do Not Produce These Tasks (Previously Marked Invalid)`
      block, both in English, both guarded by `{% if %}` on their variables, in the fixed order; leave
      the format instructions, the existing `{% if examples %}` section and `{{user_story}}`
      untouched.
- [x] 1.7 RED — `backend/tests/test_api/test_extraction.py`: add the failing runner-level context
      cases — the rendered prompt contains the project name and description, each other story's
      `raw_text`, and each existing task's title with its owning story; a description edit after v1
      does not change v1's stored prompt while v2's carries the new one; two runs over an unchanged
      project state compose identical context blocks; the `context` argument is required (a call
      without it fails). These are RED today because `render()` takes no context and
      `ProjectContext` does not exist. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_extraction.py -m "not integration"`.
- [x] 1.8 GREEN — `backend/src/storico/domain/services/extraction_service.py`: add the frozen slotted
      `ProjectContext(name, description, other_stories, existing_tasks, negative_examples=(),
      negative_examples_omitted=0)` with `as_template_variables()` doing the `UUID → str` /
      `TaskStatus → str` conversion at the boundary; `render(...)` gains the **required** keyword-only
      `context: ProjectContext`; `prompt_kwargs` becomes `user_story`, `project_context`,
      `negative_examples`, `negative_examples_omitted` and `few_shots` (plus the unchanged `examples`
      when there are examples); `RenderedPrompt` itself is unchanged.
- [x] 1.9 GREEN — `backend/src/storico/infrastructure/tasks/extraction_task.py`: in `_run_extraction`,
      between the story load and the `render()` call, read the project row through the existing
      `ProjectRepository.find_by_id(story.project_id)` for name and description (ignoring the
      `workspace_id` that comes back), call both new port methods with
      `exclude_story_id=story.id`, build `ProjectContext` and pass `context=` into `render()`. Until
      task 2.5 wires the marks read, `negative_examples` is empty and `negative_examples_omitted`
      is `0` — the block ships but stays empty, which is why D7's requirement belongs to WU2.
- [x] 1.10 GREEN — the required-argument churn at every remaining `render()` / `extract()` call site:
      add one shared `simple_context()` builder to `backend/tests/_helpers.py` and use it in
      `backend/tests/test_services/test_extraction_service.py`,
      `backend/tests/test_services/test_workspace_prompt_resolution.py` (**the call site neither
      design table names**), `backend/tests/test_unit/test_few_shot_retrieval.py`,
      `backend/tests/test_extraction_flow_few_shot.py`,
      `backend/tests/test_integration/test_few_shot_rag_qdrant.py` and
      `backend/tests/test_api/test_extraction.py`; re-point the `assert_called_once_with(...)`
      assertions on `render_instruction` to the widened kwargs.
- [x] 1.11 TRIANGULATE — **the story absent from its own task block.**
      `backend/tests/test_api/test_extraction.py` + `backend/tests/test_repositories/test_task_repo.py`:
      a story whose completed v1 produced "Implement login retry" does not carry that title in the
      existing-tasks block of its own next prompt, while a **different** story's "Set up database
      schema" does; the story's own raw text appears exactly once, as the story to decompose. Prove
      with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_extraction.py tests/test_repositories/test_task_repo.py -m "not integration"`.
- [x] 1.12 TRIANGULATE — **an invalid task never as positive context.**
      `backend/tests/test_repositories/test_task_repo.py` + `backend/tests/test_api/test_extraction.py`:
      a task of another story with an active mark is absent from the existing-tasks block and from
      every story's context; after the mark is revoked while its version is still current, the task
      returns to the existing-tasks block. (Its exit from the *negative-example* block is asserted in
      2.10, once WU2 wires that block.) Prove with the same command as 1.11.
- [x] 1.13 TRIANGULATE — **the workspace template that does not reference the new variables.**
      `backend/tests/test_unit/test_prompt_manager.py` (the template half) and
      `backend/tests/test_api/test_extraction.py` (the record half): a custom `instruction_template`
      referencing only `{{ user_story }}` renders neither block, the run completes normally, and
      `RenderedPrompt.template_variables` still carries `project_context` and
      `negative_examples_omitted`; the stored `prompt_rendered` shows the provider received neither
      block, so the divergence is readable by comparing two stored facts of one version. No runtime
      warning is added (the spec blesses the opt-out). Prove with the same command as 1.11.
- [x] 1.14 TRIANGULATE — **Postgres-only, 1000-row non-truncation.**
      `backend/tests/test_integration/test_context_ports_scale.py` **New** (path free; confirmed
      absent at planning time), each case `@pytest.mark.integration` with the `_docker_reachable()`
      skipif of `backend/tests/test_integration/test_migration_chain.py`: a project of 1000 stories
      created through the CSV import returns 999 rows from `list_for_context` and the count equals
      `count(*) FROM user_stories WHERE project_id = :p` minus one; the task read returns every valid
      current-version task without a `LIMIT`; two calls over the same state are byte-identical.
      **Requires a Docker daemon (Postgres 16 via testcontainers); without one this case skips and the
      scale proof stays unverified** — that is the honest status, not a green. Prove with
      `cd backend && conda run -n storico python -m pytest tests/test_integration/test_context_ports_scale.py -m integration`.
- [x] 1.15 REFACTOR — confirm there is exactly one context-construction site (the runner), that no
      read path filters in Python, that the two port methods appear in no paginated caller, and that
      `backend/tests/test_few_shot_examples.py`'s three direct `render_instruction` sites still pass
      now that the template has optional blocks; then rerun the phase runner and
      `cd backend && conda run -n storico python -m pytest`.

## Phase 2: WU2 — What the Version Records

Runner for this phase:
`cd backend && conda run -n storico python -m pytest tests/test_unit/test_negative_examples.py tests/test_unit/test_ollama_adapter.py tests/test_unit/test_openai_adapter.py tests/test_unit/test_anthropic_adapter.py tests/test_unit/test_gemini_adapter.py tests/test_api/test_extraction.py -m "not integration"`.
STRICT TDD. If the pause asks for the split: parts i (2.1–2.3), ii (2.4–2.6) and iii (2.7–2.9) each
end green.

> **[Amended 2026-10-03, before WU2's first tranche — the boundaries move by one task]** The owner chose
> to make each of WU1's parts its own chained PR, and the same shape carries here, which is what turns
> this line's split into review boundaries. **2.3 cannot sit in part i.** Its cases assert the negative
> block *in the rendered prompt*, and the block ships empty (WU1's part (ii)) until the runner feeds it
> the composer's output — so a part ending at 2.3 ends **red**, and a red part is not a PR boundary.
> The parts are therefore: **i = 2.1–2.2** (the composer and its unit table), **ii = 2.3–2.6** (the
> block-level RED together with the wiring that turns it green, plus 2.6's row-level read-back), and
> **iii = 2.7–2.11** (the `LLMResponse` / `usage` ripple, `record_usage`, and 2.10's pinned edges plus
> 2.11's closing pass). The original line above stays as the planning record.

- [x] 2.1 RED — `backend/tests/test_unit/test_negative_examples.py` **New** (path free; confirmed
      absent): the failing composer table over `TaskInvalidationCandidate` rows.
      **21 distinct candidates yield 20 taken and `omitted == 1`**, most recent `marked_at` first;
      two candidates with identical normalized title and reason dedupe to one entry, keeping the most
      recent; the order is total — `marked_at DESC`, then `version_number DESC`, then normalized
      title, then reason — so a tie-heavy fixture composes byte-identically twice; 5 candidates yield
      `omitted == 0`; the identity assertion that the module imports `normalize_task_title` from
      `domain/services/task_title_normalizer.py` (b's file) and defines no second casefold or
      whitespace helper. Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_unit/test_negative_examples.py -m "not integration"`.
- [x] 2.2 GREEN — `backend/src/storico/domain/services/negative_examples.py` **New** (path free):
      `MAX_NEGATIVE_EXAMPLES = 20` as a module constant, the frozen slotted
      `NegativeExample(title, reason, version_number, marked_at)` and
      `NegativeExampleBlock(examples, omitted)` with its JSON-native `as_template_variables()`, and
      `compose_negative_examples(candidates) -> NegativeExampleBlock` implementing sort → dedupe →
      cap → `omitted = deduped_total - taken`. No session, no I/O, no new mark read.
- [x] 2.3 RED — `backend/tests/test_api/test_extraction.py`: add the failing block-level cases — the
      prompt of v3 carries the v1 mark with reason "Duplicates the auth task" and the v2 mark with
      reason "Too coarse to implement"; a mark on another story is absent from this story's block;
      **21 marks put exactly 20 in the block and the block announces that 1 older mark was omitted**;
      with a workspace `few_shot_limit` above 20 the block still carries exactly 20 and announces 5
      omitted, and no `workspace_prompts` field exists that changes the cap (C6's no-knob half).
      Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_extraction.py -m "not integration"`.
- [x] 2.4 GREEN — `backend/src/storico/domain/services/extraction_service.py`: add `few_shots`
      (`[{user_story_text, tasks_summary, model_used, confidence_score, similarity_score}]` — the
      port's own fields, **text not id**, and not interpolated by the template) and the two
      negative-example entries to `prompt_kwargs`, sourced from `context`.
- [x] 2.5 GREEN — `backend/src/storico/infrastructure/tasks/extraction_task.py`: call (b)'s
      `TaskInvalidationRepository.list_active_on_other_versions(user_story_id=story.id,
      exclude_extraction_id=None)` (b's file, created at 5.6 — **no second mark read is invented**),
      feed it through `compose_negative_examples`, and fold both results into the `ProjectContext`
      the runner builds; then write the snapshot dictionary from `rendered.template_variables` in
      (a)'s `record_rendered_prompt` call — `few_shots`, `project_context`, `story_text`,
      `negative_examples_omitted` beside the inherited `validate` and `system_prompt` — with
      `negative_examples` deliberately **not** a snapshot key (it is in `prompt_rendered`).
      The ordering render → write → provider is (a)'s and is not moved.
- [x] 2.6 TRIANGULATE — **21 marks → 20 plus the announced omission, read back from the row.**
      `backend/tests/test_api/test_extraction.py`: `prompt_config["negative_examples_omitted"] == 1`
      and the stored rendered prompt's block announces it; 5 marks give `0`; the two-run determinism
      case composes the same block; the snapshot key set is exactly the six expected keys;
      `json.dumps(snapshot)` succeeds on a full context; editing the story leaves version 1's
      `story_text` unchanged while a later run stores the new text; the system prompt appears only as
      `prompt_config.system_prompt` and provider/model/temperature/rendered prompt only in their own
      columns; `few_shots` lists each example with text, model and similarity and matches the
      prompt's few-shot section; two runs with identical provider/model/temperature and one new story
      in between store two **different** prompts; the app's middleware list stays `[CORSMiddleware]`
      (V5's no-new-instrument shape assertion). Prove with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_extraction.py -m "not integration"`.
- [x] 2.7 RED — `backend/tests/test_unit/test_ollama_adapter.py`,
      `test_openai_adapter.py`, `test_anthropic_adapter.py`, `test_gemini_adapter.py`: add the failing
      return-shape cases — each adapter returns an `LLMResponse` carrying the response text, and the
      provider's own usage mapping verbatim when the response contains one; a response with no usage
      container yields `LLMResponse(text=…, usage=None)`. Also update the doubles in
      `backend/tests/test_api/test_extraction.py`, `backend/tests/test_api/test_llm_test_route.py` and
      `backend/tests/test_integration/test_few_shot_rag_qdrant.py` to return `LLMResponse`. Prove RED
      with the phase runner.
- [x] 2.8 GREEN — `backend/src/storico/domain/ports/llm_port.py`: add the frozen slotted
      `LLMResponse(text, usage=None)`, add `usage: dict | None = None` to `ExtractionResult`, and
      change `LLMPort.generate(...) -> LLMResponse`; then the four adapters
      (`ollama_adapter.py`, `openai_adapter.py`, `anthropic_adapter.py`, `gemini_adapter.py`) return
      `LLMResponse` and copy the provider's container when present; the `.text` ripple at
      `domain/services/extraction_judge_service.py`, the five probes in `api/routes/settings.py` and
      `extraction_service.py`; **`generate()` widens to `-> ExtractionResult`**, superseding (a) 3.4's
      two-tuple (seam 4 above) and updating the runner's iteration to `result.tasks`.
- [x] 2.9 GREEN — `backend/src/storico/domain/ports/extraction_repository.py` and
      `backend/src/storico/infrastructure/database/repositories/extraction_repository.py`: add
      `record_usage(extraction_id, *, prompt_config: dict)` as a single `UPDATE` naming **only**
      `prompt_config`; `backend/src/storico/infrastructure/tasks/extraction_task.py`: after the
      provider answers, call it once with the complete dictionary plus `usage` **only when
      `result.usage is not None`** — no write, no key and no zero when the provider returned nothing.
- [x] 2.10 TRIANGULATE — the remaining pinned edges at the row level:
      `backend/tests/test_api/test_extraction.py` — a run whose prompt rendered but whose provider
      call failed keeps **every** snapshot key but `usage` and keeps a non-null `prompt_rendered`,
      while a run that died before render keeps `prompt_rendered IS NULL`; a provider returning no
      usage leaves the key absent (never zero-filled, never estimated); an invalid task's mark
      **leaves** the negative block once revoked while its version is still current. Prove with the
      phase runner.
- [x] 2.11 REFACTOR — confirm `ExtractionResult` has exactly one producer and one consumer, that no
      snapshot value is computed outside `template_variables`, and that no write names a snapshot
      column; then rerun the phase runner and
      `cd backend && conda run -n storico python -m pytest tests/test_unit tests/test_api -m "not integration"`.

## Phase 3: WU3 — Few-Shot Exclusions and the Mark's Vector Consequence

Runner for this phase:
`cd backend && conda run -n storico python -m pytest tests/test_unit/test_vector_store.py tests/test_unit/test_few_shot_retrieval.py tests/test_api/test_tasks.py -m "not integration"`.
STRICT TDD. If the pause asks for the split: parts i (3.1–3.3), ii (3.4–3.5), iii (3.6–3.8) and iv
(3.9) each end green. **Order inside the unit matters:** the payload keys land before the fail-closed
filter, or every existing point silently becomes unretrievable.

- [ ] 3.1 RED — `backend/tests/test_unit/test_vector_store.py`: add the failing filter, payload and
      index cases against the fake client. `search_similar` requires the new keyword
      `exclude_story_id` on both the port and the adapter (signature inspection at
      `test_vector_store.py:157-166`); the built filter is
      `must=[workspace_id == str(W), has_invalid_tasks == False], must_not=[user_story_id == str(excluded)]`
      — with the validity condition asserted as a **positive `must` on `False`**, never a `must_not`
      on `True`; `store_extraction` writes the ten keys, growing the pinned payload assertion at
      `test_vector_store.py:606-639` from 7 to 10 with `project_id`/`version_number`/
      `has_invalid_tasks=False`; `create_payload_index` is called for `workspace_id` and `project_id`
      (`KEYWORD`) and `has_invalid_tasks` (`BOOL`) — this first RED step also **pins the schema
      against the pinned `qdrant_client`**, with the literal `KEYWORD` fallback recorded if the client
      rejects `BOOL`; `set_has_invalid_tasks` issues
      `set_payload(points=[extraction_id], payload={"has_invalid_tasks": …}, wait=True)`.
      Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_unit/test_vector_store.py -m "not integration"`.
- [ ] 3.2 GREEN — `backend/src/storico/domain/ports/vector_store_port.py`: `search_similar` gains the
      required `exclude_story_id`, its docstring stating that **both** exclusions are unconditional
      rules of retrieval and that no caller may opt out; `store_extraction` gains the required
      keyword-only `project_id` and `version_number`; add the abstract
      `set_has_invalid_tasks(*, extraction_id, has_invalid_tasks)` whose docstring states that it
      addresses the point id that **is** the extraction id, that a missing point is a no-op, and that
      — unlike `search_similar`/`store_extraction` — it **raises** `VectorStoreError` because its
      caller must not proceed on an unverified result.
- [ ] 3.3 GREEN — `backend/src/storico/infrastructure/vector/qdrant_adapter.py`: replace
      `_build_workspace_filter`'s single positive condition with the `must`/`must_not` expression;
      add the three payload keys; generalise `_ensure_workspace_payload_index` into
      `_ensure_payload_indexes` looping over `("workspace_id", "project_id", "has_invalid_tasks")`
      behind one flag, called from `_get_client` right after the collection is ensured, still logging
      a failure without failing the request; implement the setter with `client.set_payload(...,
      wait=True)` wrapping driver failures in `VectorStoreError`.
- [ ] 3.4 GREEN — `backend/src/storico/domain/services/extraction_service.py`: `_fetch_rag_examples`
      takes the story id and forwards `exclude_story_id`; it **fails closed** when the story has no
      id (skip retrieval, warn with `reason="missing_story_id"`), mirroring the existing
      missing-`workspace_id` branch at `:186-197`. Move the remaining callers: the ~10 sites in
      `backend/tests/test_unit/test_vector_store.py`, plus
      `backend/tests/test_unit/test_few_shot_retrieval.py`,
      `backend/tests/test_services/test_extraction_service.py`,
      `backend/tests/test_extraction_flow_few_shot.py`,
      `backend/tests/test_integration/test_few_shot_rag_qdrant.py` (~7 sites) and
      `_RecordingVectorStore` in `backend/tests/test_api/test_extraction.py:59-76`.
- [ ] 3.5 GREEN — `backend/src/storico/infrastructure/tasks/extraction_task.py`: `_store_rag` gains
      `project_id` and `version_number` and writes them through to `store_extraction`; thread
      `version_number` from the route through `run_background_extraction` into `_run_extraction`
      alongside the temperature (a's parameter) — **seam 3 above: (a) 2.3 and (b) 4.6 do not schedule
      this parameter, so (c) owns it**, and the value is the one (b) returns in the 202 body so a
      retry reuses it (D22).
- [ ] 3.6 RED — `backend/tests/test_api/test_tasks.py`: add the failing refresh cases, all through the
      `get_vector_store` injection point with a recording fake. Marking a task calls
      `set_has_invalid_tasks(extraction_id, True)` **before** `invalidation_repo.create` (assert the
      call order, not just the call); the same task un-marked while its version is still current
      leaves the flag set; a second active mark revoked leaves `True`; the last active mark revoked
      calls with `False`; a fake store that raises on the refresh answers 503
      `VECTOR_STORE_UNAVAILABLE` with **no mark row created** and the mark still active on the revoke
      path; with no vector store configured both operations proceed and **no refresh call** is made.
      Prove RED with
      `cd backend && conda run -n storico python -m pytest tests/test_api/test_tasks.py -m "not integration"`.
- [ ] 3.7 GREEN — `backend/src/storico/domain/ports/task_invalidation_repository.py` and
      `backend/src/storico/infrastructure/database/repositories/task_invalidation_repository.py`
      **(b's files, created at 5.5 and 5.6 — (c) adds this method)**: add
      `count_active_for_extraction(*, extraction_id, exclude_mark_id=None) -> int` as one statement —
      `task_invalidations JOIN tasks ON tasks.id = task_invalidations.task_id`,
      `tasks.extraction_id = :extraction_id`, `revoked_at IS NULL`, `id != :exclude_mark_id` — with its
      docstring stating it is a **computed** value, which is what makes refresh-first possible without
      surgery on (b)'s internally-committing `revoke`.
- [ ] 3.8 GREEN — `backend/src/storico/api/routes/tasks.py` **(b's file, whose two handlers are
      created at 5.9 — (c) adds these calls, seam 1 above)**: create-mark handler order becomes
      gate (403) → reason schema (422) → frozen check (409) → `find_active_by_task` (409) →
      **`set_has_invalid_tasks(extraction_id, True)`** → `invalidation_repo.create(mark)` → 201;
      revoke order becomes gate → frozen check (409) → `find_active_by_task` (404) →
      **`remaining = count_active_for_extraction(extraction_id, exclude_mark_id=mark.id)`** →
      **`set_has_invalid_tasks(extraction_id, remaining > 0)`** → `invalidation_repo.revoke(...)` →
      204. The refresh sits **before** the relational write, per the accepted `(correction)`, so a
      failure leaves no mark persisted; with `get_vector_store` returning `None` the whole refresh
      block is skipped.
- [ ] 3.9 TRIANGULATE — **a point missing the validity flag is excluded, proved against a real
      Qdrant.** `backend/tests/test_integration/test_few_shot_rag_qdrant.py`, all cases behind
      `STORICO_TEST_LIVE_QDRANT=1`: the same story's previous point is not returned for its own
      re-extraction; an extraction carrying an active mark is not returned; with `limit=1` and both
      contaminated points above the threshold the returned example is the valid one, so neither
      excluded point consumed the limit; **a point written without `has_invalid_tasks` is not
      returned while a valid point still is** (the fail-closed proof a fake client cannot give); the
      collection's `payload_schema` carries all three indexes; and the cross-slice coexistence proof
      from seam 2 — (b)'s `delete_by_story` removes a story's point whose payload carries the new keys
      and whose flag is `true`, and the refresh on that deleted point is a no-op. **Precondition: a
      reachable Qdrant** (Docker Compose dev / Qdrant Cloud prod); a skip here proves nothing and the
      flag makes an unreachable service a failure by design. Prove with
      `STORICO_TEST_LIVE_QDRANT=1 cd backend && conda run -n storico python -m pytest tests/test_integration/test_few_shot_rag_qdrant.py`.
- [ ] 3.10 TRIANGULATE (unit) — `backend/tests/test_repositories/test_task_invalidation.py` **(b's
      file, created at 1.2/4.1 of (a) and extended at 5.3 of (b) — (c) adds the counting cases)**: two
      active marks on one extraction give `count_active_for_extraction(...) == 2`; revoking one with
      `exclude_mark_id` set to that mark gives `remaining == 1`; the last one gives `0`; the count is
      scoped to the extraction, so another version's mark on the same story is not counted. Prove with
      `cd backend && conda run -n storico python -m pytest tests/test_repositories/test_task_invalidation.py tests/test_unit/test_few_shot_retrieval.py -m "not integration"`.
- [ ] 3.11 REFACTOR — confirm the validity exclusion is expressed in exactly one filter and never in
      Python, that the exclusion carries the story id from the story object rather than a
      re-derivation, that the payload assertion is the only place enumerating payload keys, and that
      the two handler orders are the only refresh call sites in the tree; then rerun the phase runner
      and `cd backend && conda run -n storico python -m pytest tests/test_unit tests/test_api tests/test_repositories -m "not integration"`.

## Phase 4: WU4 — The Two Benches and the Record

**This unit is not a TDD unit.** It is a measurement unit: its evidence is the recorded number, not a
test, and **no code line in this phase may add an input cap, a truncation or an input-side pagination
to make a run pass**. Operator-run, after the code lands and after D11's wipe; every number goes into
`openspec/changes/extraction-versioning-prompt/verify-report.md`.

- [ ] 4.1 **Per-provider `usage` confirmation against real responses** (operator-run). For each of
      Ollama, OpenAI, Anthropic and Gemini: issue one real generation through the corresponding
      adapter with a configured provider, capture the raw response, and record in `verify-report.md`
      a table of *provider → field actually present → captured mapping or "absent"*. The **surviving
      rule is written into this line and into the report**: **no field, no key — if the provider does
      not return usage, the `usage` key is omitted and the omission is annotated**, never
      zero-filled, never estimated. Confirm the field names D20 guessed
      (`prompt_eval_count`/`eval_count`, `usage`, `usage_metadata`) against the real containers, and
      fix any adapter test that pinned a guess the real response contradicts. **Precondition: one
      reachable provider per adapter**; a provider that cannot be reached is recorded as "not
      confirmed", not as "absent from the provider".
- [ ] 4.2 **D20's ladder — 1 / 50 / 200 stories, on a Neon-like database, never the dev pooler.**
      (operator-run data operation; separate from 4.3 and never a substitute for it). For each size:
      one fresh workspace, one project, the stories created through the CSV import
      (`POST /api/v1/workspaces/{workspace_id}/stories/import`), and one extraction run with a
      configured provider. Then read the three numbers from the stored row — **no new instrument**,
      `completed_at - created_at` and `length(prompt_rendered)` and `prompt_config -> 'usage'` — and
      record them per project in `verify-report.md`, with the statement-count baseline this change
      writes down (**≈16 fixed + ≈2 per task**; the "~8 + 1" figure is not repeated as measured) and
      the call-site delta of the three context reads. The dev pooler is excluded **by name** because
      its ~2 s per-statement floor (open debt 2) would measure the pooler instead of the prompt.
- [ ] 4.3 **D23's mandatory 1000-story project, created through the CSV import** (operator-run data
      operation; separate from 4.2). One import of 1000 rows, then one run, then the count check
      `json_array_length(prompt_config -> 'project_context' -> 'other_stories')` against
      `count(*) FROM user_stories WHERE project_id = :p` minus one. **Exactly two outcomes are
      legitimate and both are recorded:** either the run stores a version whose measured size and
      duration are written down, **or** the provider rejects the prompt and — by D22 — that run
      consumes a version number while producing nothing (`status = failed`, `prompt_rendered`
      non-null, no `usage`, `error_info` naming the refusal). **A rejection at 1000 stories is a
      recorded finding, not a failing test to retry until green:** nothing in the extraction path is
      changed to make it pass, and the report carries the real numbers as the annotated known
      limitation. Record that **1000 is a floor** — `MAX_ROWS = 1000` is a per-uploaded-file cap with
      no per-project quota (Δ1), so the annotation reads *"1000 stories from one import; a second
      import crosses it"* and never implies a project maximum.
- [ ] 4.4 GREEN (documentation) — `openspec/changes/extraction-versioning-prompt/verify-report.md`
      **New** (path free; confirmed absent): the ladder table per project (prompt size, duration,
      usage when present), the 1000-story run with its bound statement, the outcome each run actually
      landed in, the 4.1 usage-confirmation table with its omissions annotated, the corrected
      statement-count baseline, and one line stating that no input token cap, no truncation and no
      input-side pagination were introduced anywhere between the story text and the provider call.
- [ ] 4.5 **No-shortcut sweep** (operator/inspection, recorded in the same file): confirm by reading
      the extraction path that no length operation, `min(`, slice, token budget or paginated read was
      added between `extraction_service.py`'s `raw_text` read and the provider call, and that
      `list_page`'s 20/100 window bounds neither of the two context reads. Record the sweep's result
      in `verify-report.md`; if a bench failed, this sweep is what proves the failure was not
      "fixed".

## Phase 5: Slice Verification

- [ ] 5.1 Whole backend suite (the acceptance gate):
      `cd backend && conda run -n storico python -m pytest`.
- [ ] 5.2 Integration layer, run where the Docker daemon exists:
      `cd backend && conda run -n storico python -m pytest -m integration`. Without a Docker daemon
      the Postgres-only scale proof (1.14) and the Postgres half of (b)'s deletion record skip and
      stay **unverified** — record that outcome instead of reporting green.
- [ ] 5.3 Live-Qdrant layer, run where a Qdrant server is reachable:
      `STORICO_TEST_LIVE_QDRANT=1 cd backend && conda run -n storico python -m pytest tests/test_integration/test_few_shot_rag_qdrant.py`.
      Record which cases ran and which skipped.
- [ ] 5.4 Repo-documented lint/format (`AGENTS.md` §0), from `backend/`:
      `conda run -n storico python -m ruff check src tests` and
      `conda run -n storico python -m ruff format --check src tests`.
- [ ] 5.5 Record in `verify-report.md` the honest split of evidence: what the SQLite unit layer
      proved, what required Postgres, what required a live Qdrant and what skipped, what the four
      provider responses confirmed, and what each bench measured.

## Slice Boundary

- **(c) depends on (a) and (b) and is the last slice of the three to land.** It consumes (a)'s
  render-time write and `RenderedPrompt.template_variables`, `version_number`, `provider`,
  `temperature`, `prompt_rendered` and `tasks.extraction_id`; and (b)'s `list_active_on_other_versions`,
  `normalize_task_title`, the two mark endpoints and `VectorStoreError`. Nothing here is deployable
  before `0028` and the mark endpoints exist, and all three slices ship in one release.
- **The feature's release is 0.9.0, and D11's data wipe is a precondition of the deploy that carries
  it — not a task in this file.** Wiping the relational data and the two Qdrant collections
  (`storico_extractions_dev`, `storico_extractions_prod`) is a separate destructive operation with its
  own confirmation and record, executed before the deploy. It is what makes the payload's new keys and
  the recreated collections coherent, and no backfill is attempted here. The version bump itself is
  `make bump`, never a hand-edit and never a task in a change.
- **Cross-slice seams this slice owes, and who carries each:**
  - **(b)'s mark and revoke endpoints must call the payload refresh** — the call sites, their order
    (refresh **before** the relational write, per the accepted correction) and their RED cases are
    **(c) WU3 tasks 3.6–3.8**, written into (b)'s handler file `backend/src/storico/api/routes/tasks.py`
    after (b) 5.9 creates those handlers. (b)'s own task list never mentions the refresh, so until 3.8
    lands the flag never moves.
  - **(b)'s story-delete must coexist with (c)'s payload keys** — (b) 4.12's `delete_by_story` filters
    on `workspace_id` + `user_story_id` and never reads `has_invalid_tasks`, and a point-id refresh
    cannot resurrect a deleted point, so (b) needs no change; the proof is **(c) WU3 task 3.9**'s
    live-Qdrant coexistence case.
  - **`version_number` in the runner** is carried by **(c) WU3 task 3.5** — neither (a) 2.3 nor (b)
    4.6 schedules the parameter.
  - **`generate() -> ExtractionResult`** supersedes (a) 3.4's two-tuple and is carried by **(c) WU2
    task 2.8**.
  - **`count_active_for_extraction`** is added to (b)'s port and repository by **(c) WU3 task 3.7**,
    because the revoke recomputation needs it and the refresh order forbids reading committed state.
- **The one item this slice must NOT decide: what to do if the 1000-story bench shows the prompt
  cannot fit.** D9 fixes no input cap **by choice** and D20 says measure and annotate, so (c) records
  the real number as an annotated known limitation and stops there. Adding a cap, a truncation, an
  input-side pagination or a "too large" refusal is a **new user decision outside 0.9.0**, not a fix
  this slice may improvise — which is also why task 4.5 exists as a sweep rather than as a guard.
