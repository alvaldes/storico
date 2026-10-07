# Exploration: extraction-versioning-prompt

> **Change**: `extraction-versioning-prompt` — slice (c) of three
> **Depends on**: `extraction-versioning-schema` (a), `extraction-versioning-api` (b)
> **Shared evidence base**: `../archive/2026-09-30-extraction-versioning-schema/explore.md` (the D16–D23
> re-verification ledger, every claim with `file:line` at `main` `ecea3e2`)
> **Created**: 2026-09-28

This slice owns what the provider receives and what each version records about having received it:
D8's snapshot **content**, D9's project context, D7/D19's negative examples, D10's few-shot
exclusions, D20's measurement, D23's two context ports.

## Facts this slice builds on (all verified in the shared ledger)

| Fact | Evidence | Why (c) cares |
| --- | --- | --- |
| The template references exactly two variables, `examples` and `user_story` | `infrastructure/llm/prompts/task_generation.j2:18-20,26`; renderer builds `prompt_kwargs` at `domain/services/extraction_service.py:145`, adds `examples` at `:146-147`, renders at `:149-152`; `PromptManager.render_instruction` forwards `**kwargs` verbatim (`prompt_manager.py:110-135`) | Every D9/D7 block is a **new template variable plus a render-contract change**. This is the row the source spec's "Estado del código hoy" already flags |
| (a) already split render from generate and persists at render time | `../archive/2026-09-30-extraction-versioning-schema/design.md`, decisions "The render/generate split" and "the snapshot is written once between `render()` and `generate()`"; the named seam is `RenderedPrompt.template_variables` | (c) fills its `prompt_config` keys **into (a)'s existing render-time write**. No new write moment, no reordering, no second refactor |
| The only cap is on output: `max_tokens=2048`, hardcoded in the runner, which silently **ignores** the workspace's own `max_tokens` column | `domain/ports/llm_port.py:15`; `infrastructure/tasks/extraction_task.py:385-388`; `domain/entities/workspace_llm_config.py:28` | D9 adds input against no input cap. The runner overriding a setting that already exists is recorded here and **not fixed** in 0.9.0 |
| There is no truncation anywhere in the extraction path | no length operation between `extraction_service.py:112` (`raw_text = getattr(user_story, "raw_text", …)`) and the template; no `truncat\|max_chars\|max_input` hit in `infrastructure/llm/` | Confirms the spec's premise for the block that grows |
| Each story is capped at **2000 characters** upstream | `api/schemas/story.py:20` and `:31`; `domain/services/story_import.py:35` `FIELD_LIMITS = {actor:100, feature:300, benefit:300, raw_text:2000}` | The unbounded dimension is the **count of items**, not their size. That is what makes the arithmetic below computable instead of open-ended |
| `MAX_ROWS = 1000` is a **per-file** parser cap with no per-project quota (Δ1) | `infrastructure/parsers/story_csv.py:23,143`; `api/routes/stories.py:410` only formats `detail["max"]`; one commit per upload via `user_story_repository.py:151-166` | The project can cross 1000 stories with a second import. A 1000-story bench is a **floor**, and the change must say which bound it proves |
| `search_similar(text, limit, threshold, *, workspace_id)` cannot express an exclusion | `domain/ports/vector_store_port.py:25-32`; `ExtractionExample` `:13-20` carries `user_story_text, tasks_summary, model_used, confidence_score, similarity_score` and **no id and no validity field** | D10's two exclusions require a **signature change**, and the returned type cannot currently identify the point it found — which is also why the few-shot text cannot be snapshotted by id today |
| The only filter built anywhere in the vector directory is workspace-keyed, with no `must_not` | `infrastructure/vector/qdrant_adapter.py:125-137` (`_build_workspace_filter`), and `:131` is the **only** `Filter(` construction site in it | A second filter mechanism is new, not a parameter |
| The payload is exactly **7** keys; none of `project_id`, `version_number`, `has_invalid_tasks` exists | `qdrant_adapter.py:257-265` (`user_story_text, tasks_summary, model_used, workspace_id, confidence_score, user_story_id, created_at`), pinned by `tests/test_unit/test_vector_store.py:606-639` | Three new payload keys. `has_invalid_tasks` must also be **updated on mark and on unmark**, per D10 — the mark lives in (b), so this slice closes that loop |
| The in-flight point is written **after** the search | search: `extraction_task.py:393` → `extraction_service.py:126` → `:199`; upsert: `extraction_task.py:460` → `:557` → `qdrant_adapter.py:195` | D10's first exclusion is not hypothetical: the contamination path today is *the previous run of the same story* |
| Few-shot defaults are `limit=3` / `threshold=0.85` and the **workspace row wins at runtime** | `FewShotConfig` at `extraction_service.py:34-44`, fallback `:80`, resolution `:120`; the runner builds it from `workspace_prompts` at `extraction_task.py:357-361` and passes it at `:396-400`; columns at `models/workspace_prompt.py:28-37` | D19's 20 is a **constant of the feature**, not workspace-configurable. The change must say which layer owns each number, or the workspace config silently outranks the feature |
| No adapter reads provider usage; nothing in the repo mentions `usage`, `prompt_eval_count`, `eval_count`, `usageMetadata`, `prompt_tokens`, `completion_tokens`, `total_tokens` | `ollama_adapter.py:159-165` returns `data["message"]["content"]`; `openai_adapter.py:124` returns `response.choices[0].message.content`; `anthropic_adapter.py:104-107` joins text blocks; `gemini_adapter.py:81` returns `response.text`; `ExtractionResult` (`domain/ports/llm_port.py:35`) has only `tasks, raw_response, confidence_score`, and there is **no** `LLMResponse`/`GenerationResult` type | D20's usage capture is four adapter changes **plus a domain type change**. The provider field names in D20's "A confirmar al implementar" are unverified in-repo: they must be confirmed against a real response of each provider, exactly as the decision says |
| There is no timing middleware | `api/app.py:141-142` adds only `CORSMiddleware`; `latency_ms` lives in `api/routes/health.py` and the connection test `api/routes/settings.py:154,181` | D20 forbids a new instrument, and none is needed: both timestamps already exist (`models/extraction.py:52` `created_at`, `:56-58` `completed_at`, added by `0023`) |
| The parser never sets `dependencies`; labels come only from `[brackets]`; the numbered fallback branch sets neither | `infrastructure/llm/task_parser.py:90-94` (`_extract_labels`), construction sites `:127-131`, `:152-156`, `:174` | D5's "dependencies are human by construction" holds. The negative-example block must not imply the model ever emitted them |
| Few-shot text is not persisted per run | the completed write stores `{validate, temperature, system_prompt}` only (`extraction_task.py:438-442`); `ExtractionExample` has no id to store | D8's `few_shots[]` block is net-new persistence and is the only record of what the model actually saw |
| No unpaginated project-scoped read exists for either entity | `UserStoryRepository.list_page` `:41` (paginated), `list_parts_by_project` `:161-170` (`actor, feature, benefit, id` only), `list_by_workspace` `:135`; `TaskRepository.list_page` `:52`, `list_by_story` `:120`, `list_by_workspace` `:125`, `list` `:135` — **no project-scoped task read at all** | D23's two ports are genuinely new methods, and the exclusion must be in the `WHERE` |
| A run costs ≈16 fixed statements + ≈2 per task (Δ3), not "~8 + 1" | every repository `save()` is a `session.get` SELECT **plus** a COMMIT (`repositories/extraction_repository.py:25,32`, `task_repository.py:25,32`, `user_story_repository.py:26,34`); `lazy="selectin"` at `models/extraction.py:58-60` and `models/user_story.py:51-59` adds SELECTs a call-site count cannot see | D23's "**two** statements more" still holds as a delta. The baseline the spec quotes is wrong and must not be repeated as a measurement |

## The arithmetic the source spec never did

D9 fixes no token cap: *"El proyecto entero entra completo"*. D20 says the impact *"se mide y se
anota"*. With the two bounds that are actually in the code (Δ1, Δ2), the worst case is computable
before running anything:

- other stories: `1000 × 2000 chars = 2,000,000 chars`
- existing task titles: a completed run yields several tasks per story, so the same project
  contributes roughly `5 × 1000` titles at tens of characters each
- plus up to 3 few-shot examples and up to 20 negative examples

Roughly **2×10⁶ characters ≈ 5×10⁵ tokens of prompt** against a **2048-token output cap and no
input cap**. That is not a latency problem arriving slowly: it exceeds the context window of every
provider this codebase adapts. The 2000-char per-story cap is what makes the number finite, and the
1000-file cap is what makes it reachable by a single CSV upload.

The decision is **not reopened** — D9 says no cap and D20 says measure and annotate. What this slice
owes is that the measurement be scheduled with both outcomes specified, because the source spec
anticipates only one:

1. the prompt fits and the change records its measured size and duration; or
2. the provider rejects the prompt and, by D22, that run **consumes a version number** while
   producing nothing.

Outcome (2) is the important one, and it changes the meaning of C9. The spec presents C9 ("un fallo
quema un número") as a hazard of a broken provider key. Measured this way, a burned number is also
the **ordinary** result of a large project: a user with a 1000-story import who presses Extract
once may just lose a version number to context size, repeatedly, with nothing deleted (D12) and no
cap to lower. So the bench must record the failure as a legitimate measured outcome rather than a
test to be retried until it passes, and the annotated known limitation must state the real number.
If (2) is what happens, that is a **new decision for the user** — not something this change may
resolve by inventing a cap, truncation, or a pagination shortcut it was told not to use.

## Two bench sizes in the source spec, and what each proves

The spec asks for two different runs and it is easy to read them as one:

| Where | Sizes | What it proves |
| --- | --- | --- |
| D20 "Bench" | three projects of **1 / 50 / 200** stories, against a Neon-like database, not the dev pooler | latency and prompt size as the project grows |
| D23 "Prueba obligatoria" and the acceptance list | one project of **1000** stories created by the CSV import | that the unpaginated context read does **not** silently truncate where `list_page`'s 100-row cap would have |

They are separate obligations and this slice schedules both. The 1000-story run is the one that can
land in outcome (2); the 1/50/200 ladder is the one that produces the curve. Neither may be
substituted for the other, and the dev pooler is excluded by name because of the ~2 s per statement
floor recorded as open debt 2 in *"Storico — deuda de ingeniería abierta por decisión"*.

## Boundaries of this slice

**In:** the `prompt_config` key content D8 delegates here (`few_shots`, `project_context`,
`story_text`, `usage`, `negative_examples_omitted`); the D9 project-context blocks in the template;
the D7 negative-example block with D19's cap of 20 and its self-announcing truncation; D23's two
unpaginated context ports with the exclusion in the `WHERE`; the three Qdrant payload keys, the
`search_similar` signature change and the `has_invalid_tasks` refresh on mark and on revoke; `usage`
capture across the four adapters; and both bench obligations above.

**Out:** schema and identity (a); HTTP contract, permissions and UI (b).
**Out (0.9.0 entirely):** LLM-as-a-Judge and per-task scores, an input token cap or any truncation,
comparison-metrics views, timing middleware, fuzzy propagation of the mark, and the
`workspace_llm_config.max_tokens` behaviour the runner overrides (recorded, not fixed).

**Fixed by decision, not configurable:** D19's 20 — *"El 20 es una constante del feature, no
configuración por workspace en 0.9.0"*.
