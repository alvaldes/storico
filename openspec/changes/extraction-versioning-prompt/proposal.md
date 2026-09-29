# Proposal: Extraction Versioning — Prompt Context, Snapshot Content and Few-Shot Exclusions

> **Slice (c) of 3** for Storico feature 0.9.0. Siblings: `extraction-versioning-schema` (a, the
> root dependency) and `extraction-versioning-api` (b). Evidence: `explore.md` in this change, plus
> the shared ledger `../extraction-versioning-schema/explore.md` (D16–D23 re-verified, every claim
> at `file:line`, measured at `main` `ecea3e2`). Source spec: vault note *"Storico — versionado de
> extracción y tareas inválidas"* (D1–D23, all closed; **no open questions**, none raised here).

## Intent

Give the provider the project it is decomposing a story for, give it the human's negative examples,
and make every version record exactly what it sent. Slice (a) built the version's identity and the
render-time write; slice (b) built the mark the user writes and the reads that follow the current
version; **slice (c) is what the provider receives and what the version records about having
received it** — D8's snapshot *content*, D9's project context, D7/D19's negative examples, D10's
two few-shot exclusions and three payload keys, D20's measurement with no new instrument, and D23's
two unpaginated context ports.

This is also the slice that makes C5 acceptable. Injecting D9 means the prompt for a story depends
on the project's state at that moment, so two runs with identical configuration produce **different
prompts**. Reproducibility is therefore a **stored fact** (the rendered prompt and the context that
went into it), never a re-execution promise — which is exactly why the snapshot carries discrete
keys instead of a promise to re-derive them later.

### Problem Statement

1. **The prompt sees one story and nothing else.** The template consumes exactly two variables —
   `examples` and `user_story` (`infrastructure/llm/prompts/task_generation.j2:18-20,26`) — and the
   renderer passes exactly those (`domain/services/extraction_service.py:145-152`;
   `PromptManager.render_instruction` forwards `**kwargs` verbatim, `prompt_manager.py:110-135`).
   The LLM decomposes a story knowing nothing about the project's name, its description, what the
   project's other stories say, or what was already extracted there, although `Project.description`
   has existed the whole time and D9 makes all of it part of the contract.
2. **What the model saw is not recorded.** On a completed row `prompt_config` holds only
   `{validate, temperature, system_prompt}` (`infrastructure/tasks/extraction_task.py:438-442`) and
   the few-shot text is not persisted at all; `ExtractionExample`
   (`domain/ports/vector_store_port.py:13-20`) carries the text but **no id**, so there is nothing
   even to reference. Two runs cannot be compared as stored facts, and D8's promise — every version
   freezes what it takes to read and reproduce it later — has no content.
3. **The user's judgement never reaches the next prompt.** D6's mark ships in (a) as a table; D7
   says the marks of `v1..v(n)` feed `v(n+1)` as explicit negative examples, and no block, no
   reader and no cap exist yet. D19 fixes the cap at 20 with a self-announcing truncation.
4. **Few-shot retrieval can return the story being extracted.** Measured: the search runs at
   `extraction_task.py:393` → `extraction_service.py:126,199`, the in-flight point is written
   afterwards at `extraction_task.py:460` → `qdrant_adapter.py:195`, so what can come back is *a
   previous run of the same story*. `search_similar(text, limit, threshold, *, workspace_id)`
   (`vector_store_port.py:25-32`) cannot express an exclusion, and the adapter's only filter is
   workspace-keyed with no `must_not` anywhere (`qdrant_adapter.py:125-137`, the sole `Filter(`
   construction site in that directory).
5. **The payload has nowhere to read the new exclusions from.** The Qdrant payload is exactly
   **7** keys (`qdrant_adapter.py:257-265`, pinned by `tests/test_unit/test_vector_store.py:606-639`);
   none of `project_id`, `version_number`, `has_invalid_tasks` exists. And `has_invalid_tasks` is
   not a write-once fact: D10 says the key is **updated** on mark *and* on revoke, which today has
   no writer at all.
6. **No unpaginated project-scoped read exists.** `UserStoryRepository.list_page` is paginated
   (default 20, cap 100 — `api/schemas/common.py:9-10`), `list_parts_by_project` returns only the
   three fragments and the id, and `TaskRepository` has **no project-scoped read**. Reusing them
   would truncate the project silently — the exact failure this feature exists to prevent (D23).
7. **No adapter reads provider token usage.** All four read only the content
   (`ollama_adapter.py:159-165`, `openai_adapter.py:124`, `anthropic_adapter.py:104-107`,
   `gemini_adapter.py:81`), and `ExtractionResult` (`domain/ports/llm_port.py:35`) has only
   `tasks, raw_response, confidence_score`; the repo-wide grep for usage fields returns zero
   matches. D20's measurement is a domain type change plus four adapter changes, and the provider
   field names are marked "A confirmar al implementar" — nothing in this repo confirms them.
8. **The prompt has no input cap, and the project has no ceiling.** Δ2: no truncation exists between
   `extraction_service.py:112` and the template, but every story is capped at **2000 characters**
   upstream (`api/schemas/story.py:20,31`; `story_import.py:35`). Δ1: `MAX_ROWS = 1000`
   (`infrastructure/parsers/story_csv.py:23,143`) is a **per uploaded file** cap with no per-project
   quota. The worst case is therefore computable and exceeds every adapted provider's context window
   (Approach 6) — a measured consequence to record, not a defect this slice may fix.

## Scope

### In Scope

- **The snapshot's content (D8)**: `prompt_config.few_shots` (each example **with its text**),
  `project_context`, `story_text` as sent, `negative_examples_omitted`, and `usage` when the
  provider returns it — filled into the render-time write slice (a) moved before the provider call.
  Provider, model, temperature and the rendered prompt are already (a)'s columns; the system prompt
  is already `prompt_config.system_prompt`. **Nothing is stored twice.**
- **D9's context blocks in the template**: project name, the project description as it is at that
  moment, the text of the project's other stories, and the project's existing tasks — with the two
  explicit exclusions (the story being extracted, in every version, from the existing-tasks block;
  and every task marked invalid, anywhere in the project, from positive context).
- **D7/D19's negative-example block**: marks from **all** previous versions of that story with their
  reason, most recent first by `marked_at`, deduplicated by normalized title and reason, capped at
  **20** — a constant of the feature, **not** workspace-configurable in 0.9.0 — and, when it
  truncates, a block that says so plus the omitted count in the snapshot.
- **D10's two few-shot exclusions**: a `VectorStorePort.search_similar` **signature change** plus a
  real `must_not` filter, and the three new payload keys `project_id`, `version_number`,
  `has_invalid_tasks` — with `has_invalid_tasks` refreshed on mark **and** on revoke.
- **D23's two context ports**: `UserStoryRepository.list_for_context(project_id, *,
  exclude_story_id)` → `id` and `raw_text`; `TaskRepository.list_for_context(project_id, *,
  exclude_story_id)` → `title`, `status` and the owning `user_story_id`. Narrow projections,
  exclusion in the `WHERE`, never in Python.
- **D20's measurement, with no new instrument**: run duration from `completed_at - created_at`,
  prompt size from `prompt_rendered` measured offline, plus the `usage` the provider returns. No
  timing middleware, no metrics view.
- **Both bench obligations** (they are two, not one — see Approach 9): D20's 1 / 50 / 200 ladder
  against a Neon-like database, and D23's mandatory 1000-story project created through the CSV
  import.
- **Usage capture across the four adapters** and the domain type it needs.

### Out of Scope

**Owned by the sibling changes (do not build it here):** migration `0028`, the version number and
its allocation, the task→run link, `find_current_version`, the render/generate split and the
render-time write moment, `task_invalidations` and its invariants, and the removal of `save`/
`delete`/`extract_and_persist` → **(a)**. The field-policy matrix, the marks endpoints, the
owner-or-`ADMIN` gate, the story-delete record and vector cleanup, both `410 Gone` retirements, the
version selector and the whole UI → **(b)**. Slice (c) has **no UI and no HTTP contract**.

**Outside 0.9.0 entirely, recorded so nobody reopens it:** LLM-as-a-Judge and per-task scores;
side-by-side version comparison; grouping runs into experiments; **batch extraction** (closed as a
non-goal on 2026-09-25 — `POST /batch` does not exist); comparison-metrics views and timing
middleware (D20 leaves them to 1.0.0); **any input token cap, truncation or input-side pagination**
(D9's "no cap" is not reopened); fuzzy or vector propagation of the invalid mark (D16 decides an
identical-text notice, not copied judgement); any `priority` editor (D21); and removing `priority`
from the contract — a separate `BREAKING` release (D21 follow-up).

**Recorded, not fixed in 0.9.0:** the runner pins `max_tokens=2048` and silently ignores the
workspace's own `workspace_llm_config.max_tokens`
(`infrastructure/tasks/extraction_task.py:385-388` vs `domain/entities/workspace_llm_config.py:28`).
It is a known behaviour of 0.9.0, out of scope here, and the only cap in the whole path (there is no
input cap). Also recorded: `AGENTS.md`'s line "los prompts del sistema y las instrucciones al LLM
están en español" does not describe this repository — the template is English — and correcting that
sentence is a docs edit, not part of this change.

## Capabilities

### New Capabilities

**None.** (a) introduced `extraction-versioning` and `task-invalidation`; (c) extends the first and
modifies two live capabilities. The prompt's non-few-shot content has no live capability behind it,
and (a)'s plan already assigns these blocks to `extraction-versioning` ("(c): snapshot content,
context ports") — so the spec phase writes them as added requirements of that capability rather
than inventing a capability no sibling planned.

### Modified Capabilities

| Capability | This slice adds | Base |
| --- | --- | --- |
| `extraction-versioning` | The snapshot's **content** (few-shots with text, project context, story text, omitted count, usage), the two unpaginated context ports, the negative-example composition rule, and D20's measurement of duration, prompt size and tokens | Introduced by (a); extended by (b) with the HTTP contract |
| `few-shot-retrieval` | Two retrieval exclusions: never the story being extracted, never an extraction containing an invalid task — both enforced in the filter, not by the caller | Live: `openspec/specs/few-shot-retrieval/spec.md` |
| `vector-store-isolation` | Three new payload keys, the payload indexes the new filters need, and the `has_invalid_tasks` maintenance on mark and revoke | Live: `openspec/specs/vector-store-isolation/spec.md` |

`few-shot-config` is **unchanged**: D19's 20 is not a fourth workspace knob. Its three existing
knobs (`enabled` / `limit` / `threshold`) keep their meaning, and no settings-screen field is added.

## Decisions This Change Makes

The source spec's schema table says "nombres y forma a confirmar al escribir el change de OpenSpec".
These are decisions, not open questions.

| Surface | Decision |
| --- | --- |
| Template variables | The render call supplies `user_story` and `examples` (the formatted string, unchanged, so every workspace-authored `instruction_template` keeps working) **plus** three structured variables: `few_shots` (list of example payloads, snapshot-only — the default template does not interpolate it), `project_context` (`{name, description, other_stories: [{id, raw_text}], existing_tasks: [{id, user_story_id, title, status}]}`) and `negative_examples` (`[{title, reason, version_number, marked_at}]`), with `negative_examples_omitted` (int) |
| Template language | The template stays **English**: the validated pipeline (LocalLLM-DataForge) and this repo's `task_generation.j2` are English, and the model-facing blocks are English too. The Spanish wording D7/D19 uses ("se omitieron N marcas más antiguas") states the *rule*; the sentence that ships is English |
| Block order in the template | `## Project Context` → `## Do Not Produce These Tasks (Previously Marked Invalid)` → the existing `## Few-Shot Examples` → `User story:`. The negative block sits **after** the context block so no invalid task is ever stated as positive context, and before the story so it reads as a constraint on the answer |
| Snapshot key shapes | `few_shots`: `[{user_story_text, tasks_summary, model_used, confidence_score, similarity_score}]` — the port's own fields, **text not id** (D8's reason: a point id does not say what the model saw). `project_context`: the object passed as the template variable, i.e. what was composed for this run. `story_text`: the story's `raw_text` at render time. `negative_examples_omitted`: int (`0` when nothing was cut). `usage`: the provider's own usage mapping, verbatim, present only when it returned one |
| Snapshot key authority | The keys are read from `RenderedPrompt.template_variables`, so they record **exactly what was passed to the render**, not a re-derivation. `prompt_rendered` stays the authority on the text the provider received |
| Where `usage` is written | It cannot be in the render-time write (the provider has not answered). It lands in the same `prompt_config`, written **after** the provider answers by one narrow port method that names **only** `prompt_config` (never a snapshot column, so (a)'s rule that terminal writes cannot null a snapshot column still holds) and restates the complete dictionary, as a `JSON` column requires; when the provider returned nothing, no write happens and the key is absent |
| Negative-example cap | `MAX_NEGATIVE_EXAMPLES = 20`, a module constant of the feature; not a column, not a workspace setting, not a request parameter |
| Negative-example composition | A pure domain function (no session, no I/O): sort by `marked_at DESC` with a deterministic tiebreak (`version_number DESC, normalized title, reason`), dedupe on `(normalize_task_title(title), reason)` keeping the most recent of each, take 20, and return the taken list plus `omitted = deduped_total - taken`. Determinism matters because the block's text is snapshotted |
| Negative-example source read | (b)'s `TaskInvalidationRepository.list_active_on_other_versions(*, user_story_id, exclude_extraction_id)` already returns `(version_number, title, reason, marked_at)` for other versions of one story — the exact rows D7 needs — so no new mark repository read is invented for the block |
| `search_similar` signature | `search_similar(text, limit=3, threshold=0.85, *, workspace_id, exclude_story_id: UUID)` — the required keyword carries D10's first exclusion in the filter. The second exclusion (any extraction whose payload says `has_invalid_tasks`) is **unconditional**, documented in the port docstring: D10 makes it a rule of retrieval, and a boolean no caller ever sets to `False` would be dead configuration |
| Payload keys and indexes | `project_id` (string), `version_number` (int), `has_invalid_tasks` (bool) join the payload at store time; payload **indexes** are created for `project_id` and `has_invalid_tasks` on the collection (the pattern exists: `_ensure_workspace_payload_index`, `qdrant_adapter.py:104-119`). (b) hands collection-schema concerns to this slice |
| `has_invalid_tasks` refresh | A port method that sets the key on the point whose id **is** the extraction id (`PointStruct(id=extraction_id, …)`, `qdrant_adapter.py:253-265`) — no search needed. Mark → `True`; revoke → recomputed from the marks still active on that extraction, never assumed `False`. The marks endpoints (b) call it; a failure raises (the `VectorStoreError` → 503 path (b) registers) so a mark is never persisted over a list that still returns the invalid run; with no vector store configured there is nothing to refresh and the mark proceeds |
| Context port row types | `StoryContextRow(id, raw_text)` and `TaskContextRow(title, status, user_story_id)` — frozen slotted dataclasses beside their ports, like `ExtractionExample` and (b)'s `TaskInvalidationCandidate`. Both reads order deterministically (`created_at, id`) so the composed text is stable for a given project state |
| Task context exclusions | `TaskRepository.list_for_context` carries **both** D9 exclusions in its `WHERE`: the story being extracted (`tasks.user_story_id != :exclude_story_id`, joined through `user_stories.project_id`) and every task with an active invalidation mark (`NOT EXISTS` on `task_invalidations` where `revoked_at IS NULL`). D23 names the first; D9 requires the second, and neither may be a Python filter |
| Where the context reads happen | The **runner** calls them (it owns the session and the repositories, and (a) keeps the service repository-free) and passes one new keyword-only `context` argument into `render()`. This is the one place slice (c) widens `render()`'s input; see Approach 3 for the reconciliation with (a)'s seam note |
| Where the bench results live | `openspec/changes/extraction-versioning-prompt/verify-report.md`, the repo's existing verification-note convention, as D20 requires |

## Approach

1. **The template gains three blocks and no new render machinery.** `task_generation.j2` renders
   `project_context` and `negative_examples` as labelled, model-facing English blocks and keeps its
   existing few-shot section and format instructions untouched. Because the blocks are structured
   template variables, the template controls the wording and the format, and `_format_examples`
   keeps producing the same string it produces today — no workspace-authored template changes
   behaviour, and a workspace whose custom `instruction_template` does not reference the new
   variables simply gets a prompt without them (recorded as a limitation in Risks, not papered
   over).
2. **The snapshot is filled from the render, never re-derived.** The runner composes
   `prompt_config` from `rendered.template_variables` — `few_shots`, `project_context`,
   `story_text`, `negative_examples_omitted` — and hands that dictionary to (a)'s
   `record_rendered_prompt`, which writes it before `generate()` is called. Consequence that must
   not regress (Δ4): ordering stays render → write → provider, so a `failed` version keeps a
   **complete input snapshot** and legitimately lacks only `usage` (a call that never answered has
   no token counts). Nothing else in the snapshot may be missing on a failure, and `prompt_rendered
   = NULL` still means "died before render".
3. **The context arrives through the runner, and this needs one argument the (a) seam did not
   anticipate.** (a)'s seam note says (c) fills its keys "without touching `render()`'s signature",
   but D23's two reads live on `UserStoryRepository` and `TaskRepository`, while (a) made the
   service repository-free and gave the runner the session — so the context must be read by the
   runner and handed in. Decision: one new keyword-only argument carrying a `ProjectContext` value
   dataclass (project name/description, other stories, existing tasks, negative examples). This
   widens the *input* only: the render/generate split, the returned shape
   (`RenderedPrompt.template_variables`), the write moment and the ordering are untouched, and the
   reconcile happens at (c)'s design phase against (a)'s artifacts before any code. Rejected
   alternatives: letting the service hold the repository ports (contradicts (a)); rendering the
   context in the runner and bypassing `render()` (duplicates the one place that composes the
   instruction); filtering paginated reads in Python (D23's forbidden shortcut).
4. **Two new port methods, with the exclusion in SQL.** `list_for_context` on
   `UserStoryRepository` (project id + `raw_text`, `id != :exclude_story_id`) and on
   `TaskRepository` (title, status, owning story id, joined through `user_stories.project_id` with
   the exclusion and the active-mark exclusion in the `WHERE`). Both are deliberately unpaginated:
   `list_page`'s 20/100 window would drop rows while the prompt silently claimed to carry the whole
   project. The project's own name and description come from the existing `ProjectRepository.find_by_id`
   — that is the third statement of D9's context, alongside D23's two ports.
5. **The negative-example block is composed by a pure domain function from (b)'s marks read.**
   Most recent `marked_at` first, deduplicated by `(normalize_task_title(title), reason)` — reusing
   (b)'s normalizer, so the codebase has one definition — capped at **20**, and when it cuts, the
   template prints that N older marks were omitted while N also lands in
   `prompt_config.negative_examples_omitted`. The cap is a feature constant: a workspace knob would
   let a workspace silently re-break D19, so the layer that owns the number is the domain, not
   `workspace_prompts`.
6. **The size consequence is measured, not pre-empted.** The decision "no input cap" (D9) is **not
   reopened**. What is now computable is the outcome: 1000 stories × 2000 characters is
   **2,000,000 characters ≈ 5×10⁵ tokens** of prompt before the project's existing tasks (which
   themselves accumulate one set per version, since D12 deletes nothing) against a **2048-token
   output cap and no input cap** — larger than the context window of every provider this codebase
   adapts. So the bench has **two** possible results and both are legitimate:
   1. the prompt fits and its measured size and duration are recorded; or
   2. the provider rejects it and, by D22, that run **consumes a version number** while producing
      nothing.
   Outcome (2) reframes C9: a burned number is not only the hazard of a broken provider key, it is
   the **ordinary** result of a large project — a user with a one-file 1000-story import can press
   Extract and lose a version number repeatedly, with nothing deleted to make room (D12) and no cap
   to lower. The bench records (2) as a legitimate measured outcome, never a test to retry until it
   passes, and the annotated known limitation states the real number. If (2) is what happens, that
   is a **new decision for the user**; this change does not resolve it by inventing a cap, a
   truncation or a pagination shortcut.
7. **Few-shot retrieval loses two classes of results in the filter.** `search_similar` gains the
   required `exclude_story_id` keyword and the adapter's single workspace-keyed filter becomes a real
   `must` + `must_not` expression: `must: [workspace_id = W, has_invalid_tasks = false]`,
   `must_not: [user_story_id = <excluded>]`. The story exclusion is a `must_not`; the validity
   exclusion is a `must` on `false` **on purpose**, because a `must_not` on the key would let a
   point that simply lacks it through — fail-closed is the posture
   `vector-store-isolation` already documents for untagged points, and it is cheap because this
   release writes the key on every point. Exclusion 1 is not hypothetical: the in-flight point is
   written after the search, so the contamination path is today *the previous run of the same
   story*; exclusion 2 is what makes a human's mark improve the next prompt instead of being
   re-injected as a good example. D11 wipes the collections, so no legacy point without the key is
   meant to survive in the first place — the fail-closed form is what keeps that true if one does.
8. **`has_invalid_tasks` is maintained, not just written.** `store_extraction` writes it as `False`
   — a point is stored after its run's tasks are created, and a task cannot be marked before it
   exists — and the mark/revoke endpoints call the new setter. Revoke **recomputes**: clearing the
   flag by assumption would
   re-expose an extraction that still holds another task's active mark. The refresh runs before the
   mark transaction is reported as done and raises on failure, so a vector store outage
   (`503 VECTOR_STORE_UNAVAILABLE`, (b)'s handler) never leaves a mark persisted over a list that
   still returns the invalid run; the opposite partial failure (refreshed point, unpersisted mark)
   over-excludes, which is the safe direction and is recorded.
9. **Both benches, and neither substitutes for the other.**
   - **D20's ladder**: three projects of **1 / 50 / 200** stories, run against a **Neon-like
     database** — explicitly **not** the dev pooler, whose ~2 s per-statement floor is open debt 2.
     It produces the curve: prompt size from `prompt_rendered`, duration from
     `completed_at - created_at`, and `usage` when the provider returned it.
   - **D23's mandatory 1000-story project**, created through the **CSV import**, which proves the
     unpaginated read does not truncate where `list_page`'s 100-row cap would have. Per **Δ1**,
     `MAX_ROWS = 1000` is a **per-file** cap with no per-project quota, so 1000 is a **floor**, not
     a ceiling: the annotation says which bound was reached ("1000 stories from one import; a second
     import crosses it") and never implies 1000 is a project maximum. The 1000-story run is the one
     that can land in outcome (2).
   Cost accounting, corrected: a run costs **≈16 fixed statements + ≈2 per task** (every repository
   `save()` is a `session.get` SELECT plus a COMMIT, and `lazy="selectin"` adds SELECTs a call-site
   count cannot see) — the spec's "~8 fixed + 1 per task" must **not** be repeated as a measured
   fact. D23's "two statements more" holds as the delta for the two context ports; D9's context in
   practice adds three (the project row read is the third), which the ladder measures rather than
   argues.
10. **Usage capture is a domain type plus four adapters, and the field names get confirmed before
    wiring.** `ExtractionResult` gains an optional usage mapping; each adapter copies the provider's
    own usage object into it when the response contains one. D20 marks the names as "A confirmar al
    implementar" and this repo confirms none of them (`prompt_eval_count` for Ollama, `usage` for
    OpenAI and Anthropic, `usageMetadata` for Gemini), so the tasks phase **schedules the
    confirmation against a real response per provider before wiring the adapter**, and the rule that
    survives the answer is fixed here: **if the provider does not return it, the key is omitted and
    the omission is annotated** — never zero-filled, never estimated. Storing the provider's own
    mapping (rather than a normalized schema invented here) keeps the confirmation visible in the
    data; a cross-provider comparison maps names once the confirmation is recorded.
11. **The published prompt section stays one section.** `few-shot-retrieval`'s single
    `## Few-Shot Examples` section keeps its behaviour with two exclusions added; the negative
    examples are a **different** block with different semantics ("this is what not to produce", not
    "this is what a good answer looks like"), so they never live inside the few-shot section.
12. **The other live capabilities' specs stay untouched.** Deliberately not modified — the nine
    live capabilities minus the two this slice proves (`few-shot-retrieval`,
    `vector-store-isolation`): `few-shot-config` (no new knob), `kanban-board`,
    `export-download`, `task-editor`, `extraction-workflow` (no UI, no HTTP),
    `embedding-providers`, `onboarding-flow`.
13. **Review workload.** Four adapters, two ports and two repositories, the Qdrant adapter, the
    template, the composer, the domain type and the runner — plus tests and the bench records. It is
    smaller than (a) or (b) but still crosses the 400-line budget. Candidate work units: (1) the
    context ports + the template blocks + the `ProjectContext` argument, (2) the snapshot content
    keys + the `usage` write + the negative-example composer, (3) the few-shot signature, filter,
    payload keys and the mark/revoke refresh, (4) the two benches and the verification note. Each unit
    is behaviour-shaped, carries its own tests, and ends on a green suite — none is a file-type split
    and none leaves the repo incoherent on its own. The
    delivery decision stays with `ask-on-risk`: on budget risk, stop and ask — no chain strategy is
    preselected.

## Affected Areas

| Area | Impact | Description |
| --- | --- | --- |
| `backend/src/storico/infrastructure/llm/prompts/task_generation.j2` | Modified | `## Project Context` and the negative-example block (English), rendered from the new structured variables |
| `backend/src/storico/domain/services/extraction_service.py` | Modified | `render()` gains the keyword-only `context` argument; `ProjectContext` value dataclass; the new entries in `template_variables`; `RenderedPrompt` itself unchanged |
| `backend/src/storico/domain/services/negative_examples.py` | New | The composer: ordering, dedup, `MAX_NEGATIVE_EXAMPLES = 20`, omitted count |
| `backend/src/storico/domain/ports/user_story_repository.py` · `task_repository.py` | Modified | `list_for_context(...)` + `StoryContextRow` / `TaskContextRow`; exclusions in SQL |
| `backend/src/storico/infrastructure/database/repositories/user_story_repository.py` · `task_repository.py` | Modified | The two unpaginated, deterministic reads |
| `backend/src/storico/domain/ports/vector_store_port.py` | Modified | `search_similar` gains `exclude_story_id` (and the documented unconditional validity exclusion); new `set_has_invalid_tasks` setter |
| `backend/src/storico/infrastructure/vector/qdrant_adapter.py` | Modified | `must`/`must_not` filter, three payload keys, payload indexes for `project_id`/`has_invalid_tasks`, the point-id setter |
| `backend/src/storico/domain/ports/llm_port.py` | Modified | `ExtractionResult.usage: dict \| None` |
| `backend/src/storico/infrastructure/llm/{ollama,openai,anthropic,gemini}_adapter.py` | Modified | Capture the provider's usage mapping when the response carries one |
| `backend/src/storico/infrastructure/tasks/extraction_task.py` | Modified | Context reads, `ProjectContext` construction, snapshot dict, `usage` write, `_store_rag` gains `project_id`/`version_number`, mark/revoke refresh call |
| `backend/src/storico/api/routes/tasks.py` | Modified (b's file) | The marks and revoke handlers call `set_has_invalid_tasks` after the mark commits |
| `backend/src/storico/infrastructure/database/repositories/task_invalidation_repository.py` | Modified (b's file) | The extraction-scoped active-mark read the revoke recomputation needs |
| `backend/tests/**` | Modified/New | Context ports, snapshot keys, composer table, filter semantics, payload keys, refresh on mark and revoke, `usage` per adapter, the failure keeps the snapshot |
| `openspec/changes/extraction-versioning-prompt/verify-report.md` | New | D20's measurements and both benches, with the outcome that actually happened |

No frontend file, no migration, no route beyond the two mark handlers' refresh call, and no new
setting.

## Risks

| Risk | Likelihood | Mitigation |
| --- | --- | --- |
| A large project's prompt exceeds the provider's context window; the run burns a version number and produces nothing (D22/C9) | High on a 1000-story project | Measured by both benches with both outcomes specified; annotated with the real number; **not** worked around — a cap or a truncation is a new user decision this change does not make |
| The "~8 fixed + 1 per task" figure gets repeated as measured | Medium | Approach 9 fixes the baseline at ≈16 + ≈2/task and records Δ3 explicitly |
| The snapshot duplicates the context that `prompt_rendered` already contains (~2 MB of JSON in the worst case) | High by design | Accepted: D8 asks for the project description and the stories *used* as facts, for the same comparability reason that made `story_text` discrete; recorded rather than optimised away |
| A workspace's custom `instruction_template` does not reference the new variables, so the composed context never reaches its prompt while the snapshot records it as composed | Medium | Default template (the product path) carries the blocks; a custom template is the workspace's own text and the snapshot's authority is `template_variables`, with `prompt_rendered` as the authority on what was sent — recorded as a 0.9.0 limitation, and the prompt editor is where a workspace adds the blocks |
| `list_page` gets reused by accident and the project truncates silently at 20/100 | Medium | Two new port methods with the exclusion in the `WHERE`; D23's 1000-story project is the proof, and it is mandatory |
| Revoke clears `has_invalid_tasks` by assumption and re-exposes an extraction with another active mark | Medium | The refresh recomputes from the marks still active on the extraction; the extraction-scoped read is named in the decisions table |
| A vector-store failure during the refresh leaves a contaminated point retrievable | Medium | Refresh before the mark is confirmed; failure raises into (b)'s 503 and the mark persists nothing; the opposite partial failure over-excludes, which is recorded as the safe direction |
| The provider usage field names differ from D20's guess and the capture silently records nothing | High | Confirm against a real response per provider **before** wiring the adapter; the surviving rule (omit the key and annotate) is fixed here, and a per-adapter test pins the captured shape |
| The few-shot exclusion breaks a workspace that relied on its own previous run as an example | Low | That behaviour is the contamination D10 exists to remove; the port docstring states the exclusion is unconditional |
| Snapshot keys drift from what was actually rendered | Low | They are filled from `RenderedPrompt.template_variables` in the same write that stores `prompt_rendered`; one test asserts the rendered text contains the context the keys record |
| Review budget exceeded without a delivery decision | Medium | Step 13's four work units and the `ask-on-risk` pause; no chain strategy preselected |

## Rollback Plan

- Revert the template to its two-variable form and drop the new template variables; `RenderedPrompt`
  and the render-time write revert to (a)'s shape (a `prompt_config` without the new keys), and the
  render-time ordering stays where (a) put it.
- Revert `search_similar` to its current signature and filter, drop the `must_not` clause and the
  three payload keys, and stop refreshing `has_invalid_tasks`; points written while the release was
  live keep the extra keys harmlessly (the filter simply stops reading them).
- Restore `ExtractionResult` to `tasks, raw_response, confidence_score` and the four adapters to
  reading only content; `prompt_config.usage` becomes a key nothing reads and nothing writes.
- Restore the two repositories' `list_for_context` removal and the `_store_rag` signature.
- Nothing here is destructive and nothing is migration-backed, so the rollback is a code revert: no
  data is lost, and the marks, versions and snapshots written while the release was live stay
  readable (the extra `prompt_config` keys and payload keys are additive).
- **Not reversible:** a bench run that landed in outcome (2) burned a version number (D22) — that is
  history, and it is exactly the fact the annotated limitation has to state.

## Dependencies

- **Slice (a) first, in the same release**: the render-time write (`record_rendered_prompt`), the
  `prompt_rendered`/`provider`/`temperature` columns, `version_number` on the row, and
  `RenderedPrompt.template_variables` are all (a)'s. This slice adds keys to a write (a) moved, and
  must not move it back.
- **Slice (b) in the same release**: the mark data (`list_active_on_other_versions`, active-mark
  semantics) is what D7's block reads, and the marks endpoints are where `has_invalid_tasks` is
  refreshed.
- **One seam to reconcile with (a)**: the extra `render()` input argument (Approach 3). (a) is
  artifacts-only and no code forecloses it; the design phase records the reconciliation rather than
  leaving two artifacts that contradict each other.
- **D11's wipe** runs as its own confirmed data operation before the deploy that carries 0.9.0; it
  is what makes the payload's new keys and the recreated collections coherent, and no backfill is
  attempted here.
- **No new runtime dependency and no new setting.** Both benches need an environment with a
  Neon-like database and a configured LLM provider; they are operator-run and recorded, not part of
  the automated suite.
- Source decisions: D7, D8, D9, D10, D12, D19, D20, D22, D23, plus C5 and C9 as the accepted
  consequences.

## Success Criteria

- [ ] A run's `prompt_config` carries `few_shots` (each example with its text, model and similarity
      score), `project_context`, `story_text` and `negative_examples_omitted`, written in the same
      render-time write that stores `prompt_rendered`; a failed run keeps all of them and lacks only
      `usage`.
- [ ] The prompt contains the project name, the description as it is at that moment, the text of the
      project's **other** stories and the project's existing tasks; it contains **no** task of the
      story being extracted (in any version) and **no** task with an active mark as positive
      context.
- [ ] The prompt of `v(n+1)` carries the invalid marks of `v1..v(n)` as negative examples with their
      reason; with 21 marks the block carries 20, says one older mark was omitted, and
      `prompt_config.negative_examples_omitted == 1`.
- [ ] Deduplication and ordering are deterministic: identical marks (normalized title + reason) yield
      one entry, most recent `marked_at` first, and two runs over the same project state produce the
      same block.
- [ ] `search_similar` requires the story being extracted; its filter carries a `must_not` for that
      story and a fail-closed `must` on `has_invalid_tasks = false`, so a re-run of a story cannot
      retrieve its own previous run and an extraction containing an invalid task (or one whose key
      is missing) is never returned.
- [ ] Qdrant points carry `project_id`, `version_number` and `has_invalid_tasks`; marking a task
      updates the key to `true`, revoking recomputes it (still `true` while another active mark
      exists, `false` otherwise), and a refresh failure leaves no mark persisted.
- [ ] Both `list_for_context` reads are unpaginated with the exclusions in the `WHERE`; a project of
      1000 stories created through the CSV import produces a prompt that contains every one of them
      (the count in the block equals the row count), proving no silent truncation.
- [ ] The "no input cap" decision is intact: no cap, truncation or pagination shortcut was added
      anywhere in the extraction path.
- [ ] `usage` capture is implemented per provider after confirming the field name against a real
      response per provider; when a provider returns none, the key is absent and the omission is
      annotated.
- [ ] `verify-report.md` records: the 1 / 50 / 200 ladder against a Neon-like database (prompt size,
      duration, usage, per project), the 1000-story CSV-import run, which of the two outcomes each
      landed in, and — if the outcome was rejection — the real numbers as the annotated known
      limitation, with the note that a cap is a new decision for the user.
- [ ] The corrected statement-count baseline (≈16 fixed + ≈2 per task) is what the change writes
      down; the "~8 + 1" figure is not repeated as measured.
- [ ] `cd backend && conda run -n storico python -m pytest` is green, including the migrated cases
      that cover the render-time snapshot path.
