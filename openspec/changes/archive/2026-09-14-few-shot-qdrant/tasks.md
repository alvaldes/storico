# Tasks: Automatic Few-Shot Examples from Qdrant

## Review Workload Forecast

| Field | Value |
| ------- | ------- |
| Estimated changed lines | 550–700 |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | Embeddings/vector → prompt+service → config/API+migration → frontend → seed+tests |
| Delivery strategy | ask-on-risk |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test | Runtime harness | Rollback boundary |
| ------ | ------ | ----------- | -------------- | ----------------- | ------------------- |
| 1 | Embeddings port + cloud adapters | PR 1 | `conda run -n storico python -m pytest tests/test_unit/test_*_embedding_adapter.py -v` | N/A (unit, mocked SDK) | Revert `embedding_port.py`, adapters, factory, settings keys |
| 2 | Workspace-scoped vector store | PR 2 | `conda run -n storico python -m pytest tests/test_unit -k qdrant -v` | Local Qdrant via Docker Compose | Revert `vector_store_port.py`, `qdrant_adapter.py` |
| 3 | Prompt + extraction service unification | PR 3 | `conda run -n storico python -m pytest tests/test_few_shot_examples.py -v` | Run an extraction with seeded history | Revert `task_generation.j2`, `prompt_manager.py`, `extraction_service.py` |
| 4 | Workspace config + migration | PR 4 | `conda run -n storico python -m pytest tests/test_api -k prompt -v` | Workspace settings page | Revert migration `0020`, entity/model/schema/route |
| 5 | Seed job | PR 5 | `conda run -n storico python -m pytest tests/test_services -k seed -v` | `python -m storico.cli.seed_few_shot` against dev | Revert `cli/seed_few_shot.py` |
| 6 | Frontend config editor | PR 6 | `cd frontend && pnpm test src/components/react/__tests__/FewShotConfigEditor` | Workspace settings page in browser | Revert config editor, types, schemas, i18n |

## Phase 1: Embeddings Port

- [x] 1.1 `domain/ports/embedding_port.py` — `EmbeddingPort` with `embed()` + `dimensions`
- [x] 1.2 Export `EmbeddingPort` from `domain/ports/__init__.py`
- [x] 1.3 `infrastructure/vector/embedding_service.py` — adapt/wrap as `OllamaEmbeddingAdapter`
- [x] 1.4 `infrastructure/vector/google_embedding_adapter.py` — `google-genai`, 768d via `output_dimensionality`
- [x] 1.5 `infrastructure/vector/openai_embedding_adapter.py` — `openai`, 768d via `dimensions`
- [x] 1.6 `infrastructure/vector/__init__.py` — factory by `STORICO_EMBEDDING_PROVIDER`
- [x] 1.7 `config/settings.py` — `embedding_provider`, embedding model ids, cloud API keys
- [x] 1.8 Tests: each adapter (mocked SDK, 768d length, error mapping) + factory selection/rejection

## Phase 2: Workspace-Scoped Vector Store

- [x] 2.1 `domain/ports/vector_store_port.py` — required `workspace_id` on `search_similar` / `store_extraction`
- [x] 2.2 `infrastructure/vector/qdrant_adapter.py` — write `workspace_id` in payload
- [x] 2.3 `qdrant_adapter.py` — `Filter(must=[MatchValue(key="workspace_id", ...)])` on every search
- [x] 2.4 `qdrant_adapter.py` — keyword payload index on `workspace_id` at collection ensure
- [x] 2.5 `qdrant_adapter.py` — switch to `AsyncQdrantClient` and `query_points`
- [x] 2.6 Tests: filter payload asserted; payload write; legacy points excluded; async non-blocking

## Phase 3: Prompt + Service Unification

- [x] 3.1 `prompts/task_generation.j2` — remove `{% if few_shot_examples %}`; rename retained section to `## Few-Shot Examples`
- [x] 3.2 `prompt_manager.py` — drop the `few_shot_examples` parameter/context
- [x] 3.3 `extraction_service.py` — drop the `few_shot_examples` parameter; accept `workspace_id` + few-shot config
- [x] 3.4 `extraction_service.py` — skip retrieval when disabled; omit section on empty results; best-effort on failure
- [x] 3.5 `extraction_task.py` — resolve config from `WorkspacePrompt` and thread `workspace_id`
- [x] 3.6 Tests: enabled/disabled/limit/cold-start/search-failure prompt rendering

## Phase 4: Workspace Config + Migration

- [x] 4.1 Alembic `0020_*` — add `few_shot_enabled` (bool, default true, not null), `few_shot_limit` (int, default 3), `few_shot_threshold` (float, default 0.85)
- [x] 4.2 `domain/entities/workspace_prompt.py` — config fields; mark `few_shot_examples` deprecated
- [x] 4.3 `infrastructure/database/models/workspace_prompt.py` — new columns
- [x] 4.4 `api/schemas/workspace_prompt.py` — config fields; remove `FewShotExample`; reject legacy input
- [x] 4.5 `api/routes/workspace_settings.py` — read/write config with defaults; admin-only
- [x] 4.6 Tests: defaults, update, validation ranges, 403, legacy `few_shot_examples` → 422

## Phase 5: Seed Job

- [x] 5.1 `cli/seed_few_shot.py` — iterate workspaces with legacy examples; embed; idempotent upsert with `workspace_id`
- [x] 5.2 Wire the CLI entrypoint (`__main__` / project script)
- [x] 5.3 Tests: idempotent re-run; workspace tagging; empty/short examples skipped

## Phase 6: Frontend Config Editor

- [x] 6.1 `components/react/FewShotConfigEditor.tsx` — toggle + limit + threshold (shadcn)
- [x] 6.2 Remove `FewShotExamplesEditor.tsx` and its usages
- [x] 6.3 `types/workspace.ts` + `schemas/workspace.ts` — config fields; drop `FewShotExample`
- [x] 6.4 `i18n/en.json` + `i18n/es.json` — config labels/errors
- [x] 6.5 Tests: render, validation, schema round-trip

## Phase 7: Drift + Regression

- [x] 7.1 Rewrite `backend/tests/test_few_shot_examples.py` (drop `_format_few_shot` tests; add unified rendering + cold start)
- [x] 7.2 Update any tests referencing the removed `few_shot_examples` parameter
- [x] 7.3 Full suites: `cd backend && conda run -n storico python -m pytest`; `cd frontend && pnpm test`

## Phase 8: Docs / Follow-up

    - [x] 8.1 Update `AGENTS.md` (few-shot description: manual → automatic from Qdrant)
    - [x] 8.2 Record the follow-up migration to drop `few_shot_examples`

    ### Follow-up

          `workspace_prompts.few_shot_examples` column and the deprecated
          `few_shot_examples` field/code path once the one-time seed job
          (`python -m storico.cli.seed_few_shot`) has run against production.
