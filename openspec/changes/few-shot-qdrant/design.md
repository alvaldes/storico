# Design: Automatic Few-Shot Examples from Qdrant

> **Change**: `few-shot-qdrant`
> **Status**: `design`
> **Based on**: `spec.md`, `explore.md`
> **Created**: 2026-09-14

---

## Technical Approach

The extraction pipeline already retrieves historical examples from Qdrant
(`ExtractionService._fetch_rag_examples`) but renders them in a *second*
prompt section while a *manual* example set is rendered in the first. This design
collapses both into one automatic path, makes the retrieval workspace-scoped, and
removes the production blocker (Ollama-only embeddings) behind a small port.

Order of work:

1. `EmbeddingPort` + adapters + factory (no behavior change for Ollama).
2. `VectorStorePort` / `QdrantAdapter` workspace scoping (+ async client).
3. Prompt unification in `prompt_manager` / `task_generation.j2`.
4. `ExtractionService` signature + workspace config threading.
5. Workspace config columns + schema + route + migration.
6. Seed job for legacy `few_shot_examples`.
7. Frontend config editor + types/schemas/i18n.
8. Test replacement (stale `test_few_shot_examples.py`).

## Architecture Decisions

### Decision: Abstract embeddings behind `EmbeddingPort`

Keep hexagonal symmetry with `LLMPort`. `EmbeddingPort.embed(text) -> list[float]`
plus a `dimensions` property. Adapters: `OllamaEmbeddingAdapter` (wraps the
current `EmbeddingService`), `GoogleEmbeddingAdapter` (`google-genai`,
`output_dimensionality=768`), `OpenAIEmbeddingAdapter` (`dimensions=768`).

- **Why**: Vercel cannot host Ollama; a port lets production pick a cloud model
  without touching the domain.
- **Tradeoff**: one more indirection and a factory; acceptable for the isolation
  gained.

### Decision: Workspace scoping via payload filter, not per-workspace collections

Add `workspace_id` to the point payload and always send
`Filter(must=[FieldCondition(key="workspace_id", match=MatchValue(value=...))])`.
Create a keyword payload index on `workspace_id`.

- **Why**: A single collection keeps ops simple; filtering is natively supported
  and indexable in Qdrant.
- **Tradeoff**: Old points without `workspace_id` become invisible to filtered
  searches (accepted in scope).

### Decision: `AsyncQdrantClient` + `query_points`

Replace the synchronous `QdrantClient` used inside `async def`. Use `query_points`
if the pinned client deprecates `search`.

- **Why**: The current adapter blocks the event loop during extraction.

### Decision: Single prompt section

Delete the `{% if few_shot_examples %}` block; rename the retained section to
`## Few-Shot Examples`. Format stays plain text
(`User story: ...` / `Tasks: ...`) so `TaskParser`-safe output is unchanged.

### Decision: Config on `workspace_prompts`, legacy column kept for the seed job

Migration `0020` adds `few_shot_enabled` (bool, default true, not null),
`few_shot_limit` (int, default 3), `few_shot_threshold` (float, default 0.85).
`few_shot_examples` is retained (read-only) until the seed job has run; a
follow-up migration drops it.

- **Why**: A data migration that performs async HTTP embedding calls inside
  Alembic is an anti-pattern; a separate, idempotent CLI job is safer and
  re-runnable.
- **Tradeoff**: A temporary legacy column remains after this change.

### Decision: Seed job as a CLI command

`python -m storico.cli.seed_few_shot` iterates `workspace_prompts` rows with a
non-empty `few_shot_examples`, embeds each example's `user_story`/`tasks`, and
upserts a deterministic point id derived from the workspace id + example index.

- **Why**: Operator-controlled, idempotent, and testable without changing API
  surface.

## Data Flow

```text
POST /workspaces/{id}/extract/
  → extraction_task.run_background_extraction(provider, api_key, base_url, workspace_id)
    → load WorkspacePrompt (system_prompt, instruction_template,
                            few_shot_enabled, few_shot_limit, few_shot_threshold)
    → ExtractionService.extract(story, config, system_prompt, instruction_template,
                                workspace_id, few_shot_config)
        ├─ if enabled: vector_store.search_similar(story_text,
        │                 limit=few_shot_limit, threshold=few_shot_threshold,
        │                 workspace_id=workspace_id)
        │     → EmbeddingPort.embed(story_text) → Qdrant query_points(filter=workspace_id)
        ├─ _format_examples(examples) → prompt_kwargs["examples"]
        └─ prompt_manager.render_instruction(template, examples=..., user_story=...)
              → task_generation.j2 → "## Few-Shot Examples" (or omitted)
    → LLM.generate(...)
    → TaskParser.parse(...)
    → ExtractionService._store_rag(..., workspace_id=workspace_id)
```

## File Changes

| File | Change |
| ------ | -------- |
| `backend/src/storico/domain/ports/embedding_port.py` | **New** `EmbeddingPort` |
| `backend/src/storico/domain/ports/__init__.py` | Export `EmbeddingPort` |
| `backend/src/storico/infrastructure/vector/embedding_service.py` | Becomes/backs `OllamaEmbeddingAdapter` |
| `backend/src/storico/infrastructure/vector/google_embedding_adapter.py` | **New** |
| `backend/src/storico/infrastructure/vector/openai_embedding_adapter.py` | **New** |
| `backend/src/storico/infrastructure/vector/__init__.py` | Export adapters + factory |
| `backend/src/storico/domain/ports/vector_store_port.py` | `workspace_id` required on search/store |
| `backend/src/storico/infrastructure/vector/qdrant_adapter.py` | Payload `workspace_id`, filter, index, async client |
| `backend/src/storico/domain/services/extraction_service.py` | Drop manual few-shot; workspace config; rename `RAGConfig` usage |
| `backend/src/storico/infrastructure/llm/prompts/task_generation.j2` | One examples section |
| `backend/src/storico/infrastructure/llm/prompt_manager.py` | Drop `few_shot_examples` |
| `backend/src/storico/domain/entities/workspace_prompt.py` | Config fields |
| `backend/src/storico/infrastructure/database/models/workspace_prompt.py` | New columns |
| `backend/src/storico/infrastructure/database/alembic/versions/0020_*.py` | **New** migration |
| `backend/src/storico/api/schemas/workspace_prompt.py` | Config fields, drop `FewShotExample` |
| `backend/src/storico/api/routes/workspace_settings.py` | Read/write config |
| `backend/src/storico/infrastructure/tasks/extraction_task.py` | Thread config + `workspace_id` |
| `backend/src/storico/api/dependencies.py` | Embedding factory + vector store wiring |
| `backend/src/storico/config/settings.py` | Embedding provider/model/keys |
| `backend/src/storico/cli/seed_few_shot.py` | **New** one-time job |
| `frontend/src/components/react/FewShotConfigEditor.tsx` | **New** |
| `frontend/src/components/react/FewShotExamplesEditor.tsx` | **Removed** |
| `frontend/src/types/workspace.ts`, `frontend/src/schemas/workspace.ts` | Config fields |
| `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json` | Labels |
| `backend/tests/test_few_shot_examples.py` | **Rewritten** |
| `backend/tests/test_unit/test_*_embedding_adapter.py` | **New** |
| `backend/tests/test_unit/test_qdrant_adapter*.py` | Extended |

## Interfaces / Contracts

```python
# domain/ports/embedding_port.py
class EmbeddingPort(ABC):
    @property
    @abstractmethod
    def dimensions(self) -> int: ...

    @abstractmethod
    async def embed(self, text: str) -> list[float]: ...

# domain/ports/vector_store_port.py (modified)
class VectorStorePort(ABC):
    @abstractmethod
    async def search_similar(
        self, text: str, limit: int, threshold: float, workspace_id: UUID
    ) -> list[ExtractionExample]: ...

    @abstractmethod
    async def store_extraction(
        self, *, extraction_id: str, user_story_text: str, tasks_summary: str,
        model_used: str, workspace_id: UUID, confidence_score: float | None = None,
        user_story_id: str = "",
    ) -> None: ...
```

```yaml
# workspace prompt config (API, camelCase over the wire)
promptConfig:
  systemPrompt: string | null
  instructionTemplate: string | null
  fewShotEnabled: boolean      # default true
  fewShotLimit: integer        # default 3, 1..10
  fewShotThreshold: number     # default 0.85, 0.0..1.0
```

```jinja
{# task_generation.j2 (unified section) #}
{% if examples %}
## Few-Shot Examples
{{ examples }}

Now break down the following user story:
{% endif %}

User story:
{{ user_story }}
```

## Testing Strategy

- **Unit (backend)**: embedding adapters (mocked SDKs, 768d, error mapping);
  embedding factory selection; `QdrantAdapter` filter payload + payload write +
  index creation + idempotent seed; prompt rendering with/without examples.
- **Service**: `ExtractionService.extract` with mocked `VectorStorePort` —
  enabled/disabled/limit/cold-start/search-failure.
- **API**: workspace prompt config CRUD, auth, validation ranges, legacy
  `few_shot_examples` rejected.
- **Frontend**: `FewShotConfigEditor` render/validation; schema round-trip;
  settings page wiring.
- **Drift**: replace `test_few_shot_examples.py::TestFewShotExampleFormatting`.
- Commands: `cd backend && conda run -n storico python -m pytest`;
  `cd frontend && pnpm test`.

## Threat Matrix

| Threat | Vector | Control |
| -------- | -------- | --------- |
| Cross-workspace data leakage | Unfiltered vector search | Mandatory `workspace_id` filter + payload index |
| Secret exposure | Cloud embedding API keys | Keys via settings/env; never returned by the API or logged |
| Injection via retrieved examples | Malicious stored extraction text | Examples are untrusted source content, rendered as plain text; no instruction role |
| Cost abuse | Unbounded retrieval | Per-workspace `limit` cap and `enabled` toggle |
| Silent quality regression | Prompt section removal | Regression tests on rendered prompt sections |

## Migration / Rollout

1. Deploy migration `0020` (additive columns; `few_shot_examples` retained).
2. Configure `STORICO_EMBEDDING_PROVIDER` + cloud key + Qdrant Cloud URL/key.
3. Run `python -m storico.cli.seed_few_shot` (idempotent) to seed Qdrant.
4. Verify retrieval per workspace; then schedule the follow-up migration that
   drops `few_shot_examples`.
5. Rollback within the window: revert code and migration; the legacy column is
   still present.

## Open Questions

- Exact Google embedding model id to pin today (`text-embedding-004` vs
  `gemini-embedding-001`)? Resolve at implementation time against the live API;
  keep the model id configurable.
- Should `limit`/`threshold` have per-model defaults when the workspace changes
  its LLM? Out of scope; single global default.
- Follow-up: drop `few_shot_examples` — becomes its own small change.
