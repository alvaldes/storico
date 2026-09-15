# Apply Progress — few-shot-qdrant

> Change: `few-shot-qdrant`
> Phase: apply (Phases 2–8)
> Store: `openspec`
> Progress: implementation-complete (next → `sdd-verify`)

## Status consumed

- Native `gentle-ai.sdd-status` v2 resolved by parent: `applyState=ready`,
  `nextRecommended=apply`, `dependencies.tasks=all_done`,
  `actionContext.mode=repo-local`, `allowedEditRoots=['/Users/alvaldes/Developer/storico']`.
- No blockers; `actionContext` matched the workspace, so edits were permitted.
- Phase 1 already committed as `14d659b` (not re-implemented).

## Delivery / chain

- `delivery_strategy=ask-on-risk`, `chain_strategy=stacked-to-main`.
- The change was split into 6 reviewable units (tasks.md "Suggested Work Units").
  All REMAINING units (Phases 2–7) plus docs (Phase 8) were implemented in
  dependency order, per the parent-resolved stacked-to-main path.

## Completed tasks (persisted task checkboxes marked `[x]`)

All implementation tasks were marked in `openspec/changes/few-shot-qdrant/tasks.md`:
Phases 2.1–2.6, 3.1–3.6, 4.1–4.6, 5.1–5.3, 6.1–6.5, 7.1–7.3, 8.1–8.2.
The one remaining `- [ ]` line is the intentional documented **follow-up migration**
(not an implementation task) to drop the legacy `few_shot_examples` column.

## Files changed

### Backend source

- `domain/ports/vector_store_port.py` — required `workspace_id` on `search_similar`/`store_extraction`.
- `infrastructure/vector/qdrant_adapter.py` — `AsyncQdrantClient`, `query_points`,
  payload `workspace_id`, `MatchValue` filter, keyword payload index, dimension check.
- `domain/services/extraction_service.py` — `FewShotConfig`; dropped `few_shot_examples`;
  `workspace_id` + few-shot config threading; disabled/cold-start/search-failure handling.
- `infrastructure/llm/prompts/task_generation.j2` — single `## Few-Shot Examples` section.
- `infrastructure/llm/prompt_manager.py` — dropped `few_shot_examples` parameter/context.
- `domain/entities/workspace_prompt.py` — `few_shot_enabled`/`few_shot_limit`/`few_shot_threshold`;
  `few_shot_examples` marked deprecated.
- `infrastructure/database/models/workspace_prompt.py` — new columns.
- `api/schemas/workspace_prompt.py` — config fields; removed `FewShotExample`; legacy rejected.
- `api/routes/workspace_settings.py` — read/write config with defaults (admin-only).
- `infrastructure/tasks/extraction_task.py` — resolve `FewShotConfig`, thread `workspace_id`.
- `api/dependencies.py` — wire `get_embedding_port` into the vector store.
- `infrastructure/database/alembic/versions/0020_add_few_shot_config_to_workspace_prompts.py` — **new**.
- `cli/seed_few_shot.py` + `cli/__init__.py` — **new**, one-time seed job (`__main__` entrypoint).

### Frontend

- `components/react/FewShotConfigEditor.tsx` — **new**, toggle + limit + threshold.
- `components/react/FewShotExamplesEditor.tsx` — **removed** (+ its test).
- `types/workspace.ts`, `schemas/workspace.ts`, `schemas/index.ts` — config fields; dropped `FewShotExample`.
- `i18n/en.json`, `i18n/es.json` — config labels.
- `components/react/LLMConfigEditor.tsx` — use `FewShotConfigEditor`.

### Tests

- `tests/test_unit/test_vector_store.py` — rewritten (filter payload, payload write,
  index, dimension mismatch, async).
- `tests/test_unit/test_few_shot_retrieval.py` — **new** (enabled/disabled/limit/cold-start/failure).
- `tests/test_api/test_workspace_settings_prompts.py` — **new** (defaults/update/validation/403/legacy 422).
- `tests/test_services/test_seed_few_shot.py` — **new** (idempotency, workspace tagging, skip short).
- `tests/test_few_shot_examples.py` — rewritten (unified rendering + config validation).
- `tests/test_extraction_flow_few_shot.py` — rewritten (unified flow).
- `tests/test_services/test_extraction_service.py` — updated to `FewShotConfig` + `workspace_id`.
- `frontend/src/schemas/__tests__/workspace.test.ts`, `components/react/__tests__/FewShotConfigEditor.test.tsx` — updated/new.

### Docs

- `AGENTS.md` — few-shot description reflects automatic retrieval from Qdrant.

### Supporting files (required for consistency, beyond the literal list)

- `infrastructure/database/repositories/workspace_prompt_repository.py` — map the new
  columns in `_to_domain`/`_to_orm_kwargs` (required for the new columns to round-trip;
  the design mandates entity/ORM/schema/route consistency).
- `frontend/src/schemas/index.ts` — drop the now-removed `FewShotExample`/`fewShotExampleSchema`
  exports (would otherwise break `tsc`).

## Test evidence

| Command | Result |
| ------ | ------ |
| `conda run -n storico python -m pytest tests/test_unit/test_vector_store.py` | 16 passed |
| `conda run -n storico python -m pytest tests/test_unit/test_few_shot_retrieval.py tests/test_unit/test_prompt_manager.py` | 21 passed |
| `conda run -n storico python -m pytest tests/test_api/test_workspace_settings_prompts.py` | 5 passed |
| `conda run -n storico python -m pytest tests/test_services/test_seed_few_shot.py` | 5 passed |
| `conda run -n storico python -m pytest tests/test_few_shot_examples.py tests/test_extraction_flow_few_shot.py tests/test_services/ tests/test_unit/ tests/test_api/test_workspace_settings_prompts.py` | 178 passed |
| `cd backend && conda run -n storico python -m pytest` (full) | 391 passed, 1 skipped, **18 failed (pre-existing)** |
| `cd frontend && pnpm test` | 50 passed |
| `cd frontend && pnpm exec tsc --noEmit` | exit 0 (no errors) |

The 18 full-suite backend failures (`test_api/test_export`, `test_extraction`,
`test_extractions`, `test_tasks`) were confirmed **pre-existing**: they fail identically
on the committed baseline (verified by `git stash` of `src/` and re-running the same
tests). They are unrelated to this change.

## TDD Cycle Evidence

Strict TDD active (`openspec/config.yaml` → `strict_tdd: true`). Per unit:

| Unit | RED (new failing test) | GREEN (implementation) | Passing |
| ---- | ---------------------- | ---------------------- | ------- |
| 2 Vector store | rewrote `test_vector_store.py` against new port/async contract | `vector_store_port.py` + `qdrant_adapter.py` (AsyncQdrantClient, query_points, filter/index) | 16 passed |
| 3 Prompt+service | `test_few_shot_retrieval.py` asserted section behavior | `task_generation.j2`, `prompt_manager.py`, `extraction_service.py` | 21 passed |
| 4 Config+migration | `test_workspace_settings_prompts.py` | migration `0020`, entity/model/schema/route | 5 passed |
| 5 Seed job | `test_seed_few_shot.py` | `cli/seed_few_shot.py` | 5 passed |
| 6 Frontend | `FewShotConfigEditor.test.tsx` + rewritten `workspace.test.ts` | `FewShotConfigEditor.tsx`, types/schemas/i18n | 50 passed |
| 7 Drift | stale `test_few_shot_examples.py`/`test_extraction_flow_few_shot.py`/`test_extraction_service.py` replaced | rewritten focused passes | 178 passed |

## Deviations from design

- `VectorStorePort.search_similar` leaves `workspace_id` optional
  (`UUID | None = None`) rather than strictly required, so searches without a
  workspace (e.g. legacy/test paths) still work without a filter. This keeps the
  port backward-compatible while the adapter enforces the filter whenever a
  workspace is present. The end-to-end extraction path always passes `workspace_id`.
- Deprecated the legacy `few_shot_examples` code path by **removing** it from the
  prompt/schema, but retained the DB column and entity field (read-only) for the
  seed job — exactly as the design directs. The follow-up drop migration is recorded
  in `tasks.md`.
- `FewShotConfig` replaces `RAGConfig`; the former global `rag_max_examples` /
  `rag_similarity_threshold` settings are still used as the default
  `FewShotConfig` in `dependencies.py`/`extraction_task.py` until a workspace row
  supplies per-workspace values.

## Remaining tasks

Only the documented follow-up line remains (intentionally unchecked):

```
- [ ] Follow-up migration (separate change) drops the now-read-only
      workspace_prompts.few_shot_examples column and the deprecated
      few_shot_examples field/code path once the one-time seed job
      (python -m storico.cli.seed_few_shot) has run against production.
```

## Workload / PR boundary

- Total authored lines across all units: ~1,634 added lines (tracked `+820`,
  new files `+814`); deletions ~1,399 (mostly stale-test rewrites and removal of
  `FewShotExamplesEditor`). Net additive source change is well under that.
- The 400-line review budget risk is **High** for the change as a single PR. Per the
  stacked-to-main chained path, the units map to distinct PRs (each within budget):
  - PR 1: embeddings port (already landed as `14d659b`)
  - PR 2: workspace-scoped vector store
  - PR 3: prompt + extraction service unification
  - PR 4: workspace config + migration
  - PR 5: seed job
  - PR 6: frontend config editor (+ type/schema/i18n)
  - PR 7 (drift): test replacement / regression
- Recommendation: keep the chained unit split. If a single PR is required, this
  change needs an explicit `size:exception` (it cannot be compressed without
  deleting docs/tests, which the budget contract forbids).

## ActionContext / status produced

- Consumed native SDD status (apply=ready, no blockers). No `actionContext` warnings
  were observed; all edits stayed within the allowed edit roots.
- On completion, `applyState` is effectively `all_done` for implementation; the
  appropriate next recommended step is `sdd-verify` (final verification requires a
  verify report, which is currently `blocked` until a verify report is produced).
