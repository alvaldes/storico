# Proposal: Automatic Few-Shot Examples from Qdrant

## Intent

Today a workspace admin must hand-write few-shot examples (`{user_story, tasks}`)
for the extraction prompt, and a second, automatic mechanism already exists but
is unused for this purpose: every completed extraction is embedded and stored in
Qdrant, and `ExtractionService` already retrieves similar past extractions
(`_fetch_rag_examples`) into a separate "Relevant Historical Examples" section.

This change replaces the manual few-shot examples with **automatic retrieval from
Qdrant**, unifies the two prompt sections into one, makes the retrieval
parameters configurable per workspace, and closes the two gaps that make the
automatic path unusable in production: **cross-workspace leakage** in vector
search and **Ollama-only embeddings** (which cannot run on Vercel serverless).

## Scope

### In Scope

- Per-workspace retrieval config: `enabled`, `limit`, `threshold` — replacing the
  `few_shot_examples` column and the free-text examples editor.
- Single unified "Few-Shot Examples" prompt section fed from Qdrant; removal of
  the duplicated "Relevant Historical Examples" section and all manual few-shot
  logic.
- Workspace isolation in vector search: `workspace_id` in the Qdrant payload and
  a mandatory filter on every similarity search.
- One-time migration of existing admin-authored `few_shot_examples` into Qdrant
  as per-workspace seeds.
- `EmbeddingPort` abstraction with cloud adapters (Google 768d, OpenAI
  768-via-`dimensions`) plus the existing Ollama adapter for local dev.
- Qdrant Cloud support (`AsyncQdrantClient`, payload index on `workspace_id`).

### Out of Scope

- Rate limiting and per-extraction cost controls.
- Trello/Jira/GitHub export connectors.
- Async batch extraction (`POST /batch`).
- Re-embedding or backfilling the existing global points via a DB join (old
  points without `workspace_id` are simply excluded from filtered searches).
- Cross-workspace example sharing / opt-in global corpus.

## Capabilities

### New Capabilities

- `embedding-providers`: provider-agnostic `EmbeddingPort` with Ollama, Google,
  and OpenAI adapters selectable by configuration; production defaults to a cloud
  provider.
- `few-shot-config`: per-workspace retrieval configuration (`enabled`, `limit`,
  `threshold`) managed from workspace settings.

### Modified Capabilities

- `few-shot-retrieval`: the extraction prompt's few-shot examples are now always
  sourced from Qdrant (workspace-scoped similarity search) instead of
  admin-authored text.
- `vector-store-isolation`: vector search and storage become workspace-scoped via
  a `workspace_id` payload field and a filter/index, eliminating cross-workspace
  example leakage.

## Approach

1. **EmbeddingPort first** — abstract embeddings (`EmbeddingPort.embed(text) ->
   list[float]` + `dimensions`), implement Ollama/Google/OpenAI adapters, and a
   factory selected by `STORICO_EMBEDDING_PROVIDER`. The existing Ollama
   `EmbeddingService` becomes the Ollama adapter so dev behavior is unchanged and
   768d stays compatible with the current collection.
2. **Workspace-scoped vector store** — extend `VectorStorePort.search_similar` /
   `store_extraction` with a required `workspace_id`; in `QdrantAdapter`, write
   `workspace_id` into every payload, create a keyword payload index on it, and
   add a `Filter(must=[MatchValue(key="workspace_id", value=...)])` to every
   search. Switch to `AsyncQdrantClient` and `query_points` if `search` is
   deprecated.
3. **Unify the prompt** — remove the manual `few_shot_examples` block from
   `task_generation.j2`; the Qdrant results render under a single "## Few-Shot
   Examples" section. `ExtractionService.extract` drops the `few_shot_examples`
   parameter and takes per-workspace retrieval config instead.
4. **Workspace config + migration** — add `few_shot_enabled` (bool, default true),
   `few_shot_limit` (int, default 3), `few_shot_threshold` (float, default 0.85)
   to `workspace_prompts`; keep `few_shot_examples` read-only for the seed job and
   drop it in a follow-up.
5. **Seed job** — a one-time CLI command reads each workspace's legacy
   `few_shot_examples`, embeds them with the active `EmbeddingPort`, and upserts
   them into Qdrant with the workspace's `workspace_id`.
6. **Frontend** — replace `FewShotExamplesEditor` (free-text examples) with a
   config editor (toggle + limit + threshold) and update types, Zod schemas, i18n.

## Affected Areas

| Area | Impact | Description |
| ------ | -------- | ------------- |
| `backend/src/storico/domain/ports/embedding_port.py` | New | `EmbeddingPort` abstraction |
| `backend/src/storico/infrastructure/vector/embedding_*.py` | New/Modified | Ollama, Google, OpenAI embedding adapters + factory |
| `backend/src/storico/domain/ports/vector_store_port.py` | Modified | `workspace_id` on search/store |
| `backend/src/storico/infrastructure/vector/qdrant_adapter.py` | Modified | Payload `workspace_id`, filter, index, async client |
| `backend/src/storico/domain/services/extraction_service.py` | Modified | Unified examples, workspace config, drop manual few-shot |
| `backend/src/storico/infrastructure/llm/prompts/task_generation.j2` | Modified | Single "Few-Shot Examples" section |
| `backend/src/storico/infrastructure/llm/prompt_manager.py` | Modified | Drop `few_shot_examples` from render context |
| `backend/src/storico/domain/entities/workspace_prompt.py` | Modified | Config fields replace `few_shot_examples` |
| `backend/src/storico/infrastructure/database/models/workspace_prompt.py` | Modified | New columns, deprecate old |
| `backend/src/storico/infrastructure/database/alembic/versions/0020_*.py` | New | Migration for config columns |
| `backend/src/storico/api/schemas/workspace_prompt.py` | Modified | Config fields replace examples |
| `backend/src/storico/api/routes/workspace_settings.py` | Modified | Prompt config read/write |
| `backend/src/storico/infrastructure/tasks/extraction_task.py` | Modified | Resolve workspace config, pass `workspace_id` |
| `backend/src/storico/api/dependencies.py` | Modified | Embedding factory wiring |
| `backend/src/storico/config/settings.py` | Modified | Embedding provider/model/keys; Qdrant Cloud |
| `backend/src/storico/cli/seed_few_shot.py` (or task) | New | One-time seed migration job |
| `frontend/src/components/react/FewShotConfigEditor.tsx` | New | Config UI replacing the examples editor |
| `frontend/src/components/react/FewShotExamplesEditor.tsx` | Removed | No longer used |
| `frontend/src/types/workspace.ts`, `schemas/workspace.ts` | Modified | Config fields |
| `frontend/src/i18n/{en,es}.json` | Modified | Config labels |
| `backend/tests/**`, `frontend/src/**/__tests__/**` | Modified | See Testing Strategy |

## Risks

| Risk | Likelihood | Mitigation |
| ------ | ------------ | ------------ |
| Prompt format change alters extraction quality | Medium | Cold-start path is instruction-only; add regression tests on rendered prompt sections |
| Cross-workspace leakage already happened historically | Medium | New searches filter by `workspace_id`; old unfiltered points are excluded |
| Embedding model swap breaks 768d compatibility | Medium | `EmbeddingPort.dimensions` validated against the collection vector size at startup |
| Seed migration partially applied | Medium | Idempotent upsert keyed by extraction id; re-runnable safely |
| Cloud embedding costs/latency at extraction time | Medium | Per-workspace `enabled` toggle and `limit` cap; graceful degradation on failure |
| Stale `test_few_shot_examples.py` masks real behavior | High | Rewrite/remove the tests as part of this change |

## Rollback Plan

- Revert the frontend to `FewShotExamplesEditor` and its schema/types.
- Restore the manual few-shot block in `task_generation.j2` and the
  `few_shot_examples` parameter in `ExtractionService` / `prompt_manager`.
- Revert the Alembic migration (config columns dropped; the legacy
  `few_shot_examples` column is only dropped in a follow-up, so it remains
  available for rollback within this change window).
- Qdrant payload additions are additive; no destructive vector rewrite is done,
  so old points remain queryable by the legacy path if needed.

## Dependencies

- `google-genai` (already present) for Google embeddings.
- `openai` (already added for the LLM adapters) for OpenAI embeddings.
- Qdrant Cloud instance + API key (`STORICO_QDRANT_URL` / `STORICO_QDRANT_API_KEY`).
- Cloud embedding API key (`STORICO_GOOGLE_API_KEY` / `STORICO_OPENAI_API_KEY`).
- Alembic migration chain continues from `0019`.

## Success Criteria

- [ ] Extraction uses only Qdrant-retrieved examples; no manual examples are read.
- [ ] Example retrieval never crosses workspaces (filtered search verified by test).
- [ ] Embeddings work in production through a cloud provider with 768d vectors.
- [ ] Workspace admins configure `enabled` / `limit` / `threshold` from settings.
- [ ] Cold start (no history, or disabled) renders a prompt with no examples section.
- [ ] Existing `few_shot_examples` are migrated into Qdrant as workspace seeds.
- [ ] The stale `test_few_shot_examples.py` suite is replaced by passing tests.
