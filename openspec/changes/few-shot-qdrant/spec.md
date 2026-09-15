# Delta Spec: Automatic Few-Shot Examples from Qdrant

> **Change**: `few-shot-qdrant`
> **Store**: `openspec`
> **Status**: `spec`
> **Source of truth for requirements**: this file (delta). Canonical specs are
> updated during `sdd-sync`.

---

## Domain: few-shot-config

### ADDED Requirements

- **FR-CONFIG-1**: Each workspace has a few-shot retrieval configuration with
  `few_shot_enabled` (boolean, default `true`), `few_shot_limit` (integer,
  default `3`, range 1–10), and `few_shot_threshold` (float, default `0.85`,
  range 0.0–1.0), stored on `workspace_prompts`.
- **FR-CONFIG-2**: A workspace admin (ADMIN or OWNER) can read and update the
  configuration through the workspace settings API; non-admins are rejected with
  403.
- **FR-CONFIG-3**: The free-text `few_shot_examples` input is no longer accepted
  by the API; posting examples is rejected with 422.
- **FR-CONFIG-4**: Defaults are applied when a workspace has no explicit
  configuration row.

### Scenarios

- **S-CONFIG-1 (read defaults)**: Given a workspace with no prompt row, when an
  admin reads the prompt config, then `enabled=true`, `limit=3`, `threshold=0.85`.
- **S-CONFIG-2 (update)**: Given an admin, when they PUT `{enabled: false,
  limit: 5, threshold: 0.9}`, then a subsequent GET returns those values.
- **S-CONFIG-3 (validation)**: Given an admin, when they PUT `limit=0` or
  `threshold=1.5`, then the request fails with 422 and no change is persisted.
- **S-CONFIG-4 (authorization)**: Given a non-admin member, when they PUT the
  config, then the response is 403 and the config is unchanged.
- **S-CONFIG-5 (legacy input rejected)**: Given any member, when they POST
  `few_shot_examples`, then the response is 422.

### Acceptance Criteria

- [ ] Migration `0020` adds the three columns with server defaults and a non-null
      constraint on `few_shot_enabled`.
- [ ] `WorkspacePrompt` entity, ORM model, Pydantic schema, and route are updated
      consistently; no code path reads `few_shot_examples` after the seed job.
- [ ] OpenAPI schema no longer exposes `fewShotExamples`.

---

## Domain: embedding-providers

### ADDED Requirements

- **FR-EMB-1**: The system exposes an `EmbeddingPort` with
  `async embed(text: str) -> list[float]` and a `dimensions: int` property.
- **FR-EMB-2**: Three adapters implement the port: Ollama (`nomic-embed-text`,
  768d, local dev), Google (`text-embedding-004` or the current equivalent,
  768d native), and OpenAI (`text-embedding-3-small`, 768d via the `dimensions`
  parameter).
- **FR-EMB-3**: The active adapter is selected by
  `STORICO_EMBEDDING_PROVIDER` (`ollama` | `google` | `openai`); production uses
  a cloud provider.
- **FR-EMB-4**: At startup/collection-ensure time the embedding `dimensions` is
  validated against the Qdrant collection vector size; a mismatch fails fast with
  a clear error instead of silently storing incompatible vectors.
- **FR-EMB-5**: Embedding failures degrade gracefully: the affected search/store
  returns no results / skips storage without failing the extraction.

### Scenarios

- **S-EMB-1 (provider selection)**: Given `STORICO_EMBEDDING_PROVIDER=google`,
  when the factory is resolved, then a Google adapter is returned with
  `dimensions == 768`.
- **S-EMB-2 (mismatch)**: Given a 1536d provider and a 768d collection, when the
  vector store is constructed, then startup raises an explicit dimension-mismatch
  error.
- **S-EMB-3 (graceful failure)**: Given the embedding API times out, when an
  extraction runs, then extraction still completes and no examples are injected.

### Acceptance Criteria

- [ ] Unit tests cover each adapter with a mocked SDK and assert 768d output
      length and error mapping.
- [ ] The factory test covers provider selection and unknown-provider rejection.

---

## Domain: few-shot-retrieval

### ADDED Requirements

- **FR-RET-1**: `ExtractionService.extract` no longer accepts
  `few_shot_examples`; it resolves retrieval config and performs a workspace-scoped
  similarity search before rendering the prompt.
- **FR-RET-2**: Retrieved examples render under a single
  `## Few-Shot Examples` section using the existing plain-text format
  (`User story: ...` / `Tasks: ...`), preserving parseability by `TaskParser`.
- **FR-RET-3**: When `few_shot_enabled` is false, or the search returns no
  results, the section is omitted entirely (instruction-only prompt).
- **FR-RET-4**: Retrieval uses the workspace's `limit` and `threshold` values,
  not global settings.
- **FR-RET-5**: Retrieval is best-effort: a search failure never fails the
  extraction.

### Scenarios

- **S-RET-1 (examples injected)**: Given two similar past extractions in the same
  workspace, when extraction runs, then the prompt contains a `## Few-Shot
  Examples` section with those examples.
- **S-RET-2 (cold start)**: Given a workspace with no history, when extraction
  runs, then the prompt contains no few-shot section and the user story.
- **S-RET-3 (disabled)**: Given `enabled=false`, when extraction runs, then no
  similarity search is performed and no section is rendered.
- **S-RET-4 (limit respected)**: Given `limit=2` and five similar examples, then
  at most two are injected.
- **S-RET-5 (search failure)**: Given Qdrant is unreachable, when extraction runs,
  then extraction succeeds with no examples.

### Acceptance Criteria

- [ ] `task_generation.j2` contains exactly one examples section.
- [ ] `prompt_manager.render_instruction` no longer references
      `few_shot_examples`.
- [ ] The stale `test_few_shot_examples.py::TestFewShotExampleFormatting` tests
      are replaced by tests for the unified rendering and cold-start omission.

---

## Domain: vector-store-isolation

### MODIFIED Requirements

- **FR-VEC-1 (modified)**: `VectorStorePort.search_similar` receives a required
  `workspace_id` and returns only examples stored for that workspace.
- **FR-VEC-2 (modified)**: `VectorStorePort.store_extraction` persists the
  `workspace_id` alongside the vector payload.
- **FR-VEC-3 (added)**: `QdrantAdapter` ensures a keyword payload index on
  `workspace_id` when the collection is created or first used.
- **FR-VEC-4 (added)**: Points stored before this change lack `workspace_id` and
  are excluded from every filtered search (accepted consequence).
- **FR-VEC-5 (added)**: The one-time seed job embeds each workspace's legacy
  `few_shot_examples` and upserts them with that workspace's `workspace_id`,
  idempotently.

### Scenarios

- **S-VEC-1 (isolation)**: Given workspace A and workspace B each with similar
  extractions, when a search runs in A, then only A's examples are returned.
- **S-VEC-2 (payload)**: Given a new extraction in workspace A, when stored, then
  the Qdrant point payload contains `workspace_id == A`.
- **S-VEC-3 (legacy points)**: Given a point stored before the change (no
  `workspace_id`), when any filtered search runs, then that point is not returned.
- **S-VEC-4 (idempotent seed)**: Given the seed job runs twice, then each seeded
  example exists exactly once.
- **S-VEC-5 (async client)**: Given the Qdrant client is async, then searches and
  upserts do not block the event loop.

### Acceptance Criteria

- [ ] Tests assert the filter payload sent to Qdrant contains the workspace
      `MatchValue`.
- [ ] Tests assert `store_extraction` writes `workspace_id`.
- [ ] The seed job is re-runnable without duplicating points.

---

## Cross-Cutting Acceptance Criteria

- [ ] Backend test suite passes:
      `cd backend && conda run -n storico python -m pytest`.
- [ ] Frontend test suite passes: `cd frontend && pnpm test`.
- [ ] No code path reads or writes the deprecated `few_shot_examples` column
      except the seed job.
- [ ] `pnpm exec tsc --noEmit` reports no new errors.
- [ ] i18n keys added to both `en.json` and `es.json`.
