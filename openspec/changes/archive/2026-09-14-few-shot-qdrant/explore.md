# Exploration: few-shot-qdrant

## (1) Exact current data flow for few-shot + RAG

### Few-Shot Examples (Manual)

- Stored per workspace in `workspace_prompts.few_shot_examples` (JSONB column)
- Loaded via `resolve_prompt()` in `api/routes/workspace_settings.py`
- Passed to `ExtractionService.extract()` via `few_shot_examples` parameter
- In `extraction_service.py`:
  - Rendered **first** by Jinja2 template (`task_generation.j2`) via `{% for ex in few_shot_examples %}`
  - Section header: `## Few-Shot Examples (Style Reference)`
  - Format per example: `User Story: {{ ex.user_story }}\nTasks:\n{{ ex.tasks }}\n---`

### RAG (Retrieval-Augmented Generation)

- Triggered automatically in `ExtractionService.extract()` via `_fetch_rag_examples(raw_text)`
- Uses `VectorStorePort.search_similar(text, limit, threshold)` with config from `RAGConfig`
- In `qdrant_adapter.py`:
  1. Embed user story via `EmbeddingService.embed()` (Ollama nomic-embed-text, 768d)
  2. Search Qdrant collection `storico_extractions` (no workspace filter)
  3. Returns list of `ExtractionExample` (user_story_text, tasks_summary, etc.)
- Formatting in `extraction_service.py`:
  - Rendered **second** via `_format_examples(examples)`
  - Section header: `## Relevant Historical Examples`
  - Format per example: `Example {i}: (confidence: X)\nUser story: {user_story_text}\nTasks:\n{tasks_summary}`
- Storage: After successful extraction, `_store_rag()` saves to Qdrant via `VectorStorePort.store_extraction()`

### Prompt Assembly (task_generation.j2)

```
[Instruction text]
{% if few_shot_examples %}
## Few-Shot Examples (Style Reference)
{% for ex in few_shot_examples %}
User Story: {{ ex.user_story }}
Tasks:
{{ ex.tasks }}
---
{% endfor %}
{% endif %}
{% if examples %}
## Relevant Historical Examples
{{ examples }}

Now break down the following user story:
{% endif %}
User story:
{{user_story}}
```

**Order**: Few-shot (style) → RAG (context) → User story

### Configuration

- RAG toggle: `vector_store` dependency (None disables RAG)
- RAG params: `rag_max_examples` (default 3), `rag_similarity_threshold` (default 0.85) from `Settings`
- Few-shot toggle: presence of `few_shot_examples` list (max 3 via schema)

## (2) Every touchpoint to change

### Backend

1. `backend/src/storico/domain/services/extraction_service.py`
   - Remove manual few-shot parameter from `extract()` signature
   - Remove `few_shot_examples` argument from `_prompt_manager.render_instruction()` call
   - Always fetch RAG examples (with new workspace-aware search)
   - Update `_format_examples()` to handle unified format (no section headers needed if merging)
   - Remove `_store_rag()` changes? (still store for future RAG)

2. `backend/src/storico/domain/ports/vector_store_port.py`
   - Add `workspace_id: UUID` parameter to `search_similar()` and `store_extraction()`
   - Update `ExtractionExample` to include `workspace_id`? (optional, for metadata)

3. `backend/src/storico/infrastructure/vector/qdrant_adapter.py`
   - Modify `search_similar(text, limit, threshold, workspace_id)` to add filter:

     ```python
     qdrant_models.Filter(
         must=[
             qdrant_models.MatchValue(key="workspace_id", value=str(workspace_id))
         ]
     )
     ```

   - Update `store_extraction(..., workspace_id)` to include `workspace_id` in payload
   - Ensure lazy init and collection creation unchanged

4. `backend/src/storico/infrastructure/vector/embedding_service.py`
   - No change (still uses Ollama nomic-embed-text)

5. `backend/src/storico/infrastructure/llm/prompt_manager.py`
   - Update `render_instruction()` to no longer accept `few_shot_examples` parameter
   - Remove `kwargs["few_shot_examples"] = few_shot_examples`
   - Template now expects only `examples` (from RAG) and `user_story`

6. `backend/src/storico/infrastructure/llm/prompts/task_generation.j2`
   - Remove `{% if few_shot_examples %}` block entirely
   - Keep only `{% if examples %}` section (renamed to `## Few-Shot Examples` or similar)
   - Update example formatting to match desired style (may need to adjust)

7. `backend/src/storico/domain/entities/workspace_prompt.py`
   - Remove `few_shot_examples` field (or keep for migration? but feature removed)
   - Keep `system_prompt` and `instruction_template`

8. `backend/src/storico/infrastructure/database/models/workspace_prompt.py`
   - Remove `few_shot_examples: Mapped[dict | None] = mapped_column(JSON, nullable=True, default=None)`

9. `backend/src/storico/api/schemas/workspace_prompt.py`
   - Remove `FewShotExample` and `few_shot_examples` from `PromptRequest` and `PromptResponse`

10. `backend/src/storico/api/routes/workspace_settings.py`
    - Remove `/prompts` GET/PUT endpoints (or keep for system/instruction only)
    - Update `resolve_prompt()` to return only system/instruction

11. `backend/src/storico/infrastructure/tasks/extraction_task.py`
    - Remove `few_shot_examples` from `resolve_workspace_prompt()` usage
    - Remove passing `few_shot_examples` to `extraction_service.extract()`

12. `backend/src/storico/api/dependencies.py`
    - No direct changes (uses `get_vector_store` and `get_prompt_manager`)

13. `backend/src/storico/config/settings.py`
    - No change (RAG settings remain)

### Frontend

1. `frontend/src/components/react/FewShotExamplesEditor.tsx`
   - Remove component entirely (no longer needed)

2. `frontend/src/types/workspace.ts`
   - Remove `FewShotExample` interface
   - Update `WorkspacePrompt` to remove `few_shotExamples` field

3. `frontend/src/schemas/workspace.ts`
   - Remove `fewShotExampleSchema` and `fewShotExamples` from `promptConfigSchema`

4. Update any workspace settings UI that uses the editor (likely in a settings page)

### Tests

- Remove `backend/tests/test_few_shot_examples.py`
- Update any tests referencing few-shot examples

## (3) The workspace-isolation gap and its design implication

### Current Gap

- `QdrantAdapter.search_similar()` **does not filter by workspace**
- All workspaces share the same vector collection (`storico_extractions`)
- RAG examples could leak across workspaces (privacy issue)
- Embedding similarity is global, not scoped to workspace domain

### Design Implication

- **Multi-tenancy requirement**: Each workspace must only see its own extractions for RAG
- **Solution**: Add `workspace_id` filter to vector search (as noted in touchpoints)
- **Tradeoff**:
  - Increases query complexity (requires payload filtering)
  - Reduces cross-workspace knowledge sharing (may be desirable for data isolation)
  - Requires migration: existing points lack `workspace_id` (must be backfilled or ignored)

### Alternative Approaches

1. Separate collection per workspace:
   - High overhead (many collections), not recommended
2. Encrypted workspace-specific embeddings:
   - Overkill, breaks similarity search
3. Accept global RAG with opt-out:
   - Privacy risk, not suitable for SaaS

**Decision**: Implement workspace filtering in Qdrant adapter via payload filter on `workspace_id`.

## (4) The cloud-embeddings/Qdrant Cloud gap and options compatible with the existing 768d collection schema

### Current Gap

- `EmbeddingService` uses **Ollama nomic-embed-text** (768 dimensions)
- **Not available on Vercel** (serverless, no persistent Ollama service)
- Qdrant Cloud is target for production, but embedding generation must work there

### Options for Cloud-Compatible Embeddings (768d)

1. **Switch to cloud embedding API with 768d output**:
   - `text-embedding-004` (Google) -> 768d ✅
   - `text-embedding-3-small` (OpenAI) -> 768d or 1536d (can truncate to 768d) ✅
   - `embed-english-light-v3.0` (Cohere) -> 384d ❌ (wrong size)
   - `embed-multilingual-light-v3.0` (Cohere) -> 384d ❌

2. **Keep Ollama but host it externally**:
   - Deploy Ollama on a cloud VM (e.g., AWS EC2) accessible from Vercel
   - Adds operational complexity, latency

3. **Use hybrid approach**:
   - Development: Ollama local
   - Production: Cloud API (Google text-embedding-004) with 768d output
   - Requires swapping `EmbeddingService` implementation based on env

### Recommended Path

- **Short-term**: Keep Ollama for MVP, accept Vercel limitation (dev only)
- **Long-term**: Abstract embedding provider via `EmbeddingPort` (like LLMPort)
  - Implement `GoogleEmbeddingAdapter` (768d) and `OllamaEmbeddingAdapter`
  - Configure via workspace setting or global flag

### Collection Schema Compatibility

- Existing collection: `vector_size=768`, distance=COSINE
- Any 768d embedding is compatible
- If switching to 1536d model (e.g., OpenAI text-embedding-3-large), would need:
  - Recreate collection with 1536d
  - Re-embed all points (backfill required)
  - Or truncate to 768d (information loss)

## (5) Open questions/tradeoffs

### Config Fields

- Should RAG settings (`max_examples`, `similarity_threshold`) be workspace-configurable?
  - Currently global via `Settings`; could move to `workspace_prompts` or new table
  - Tradeoff: flexibility vs complexity
- Should similarity threshold be exposed in UI? (Advanced setting)

### Migration of few_shot_examples column

- **Option 1**: Drop column immediately (data loss)
  - Simple, but removes user-configured examples
- **Option 2**: Keep column, ignore after migration to RAG-only
  - Allows fallback if RAG fails, but adds complexity
- **Option 3**: Migrate existing few-shot examples to Qdrant as seed data
  - Preserves user work, enables immediate RAG utility
  - Requires embedding generation for each example (batch job)

### Re-embedding Existing Points

- All existing points in Qdrant lack `workspace_id`
- **Options**:
  1. Set `workspace_id=null` and treat as global (not recommended)
  2. Backfill `workspace_id` by joining with `extractions` table (requires extraction_id linkage)
  3. Ignore old points (they will not appear in workspace-filtered searches)
  4. Delete and re-store all extractions (expensive but clean)

### Open Questions

1. Should RAG examples include confidence score weighting in search? (currently pure similarity)
2. How to handle cold start (no RAG examples) - fall back to instruction-only?
3. Should we limit RAG to extractions from same LLM model? (currently model-agnostic)
4. What is the impact on latency? (extra embedding + Qdrant call per extraction)
5. Should we add a toggle to disable RAG per workspace? (for performance-sensitive users)

## (6) Rough sizing and risk signal

### Sizing

- **Backend changes**: ~15 files modified (estimated 200-300 lines changed)
- **Frontend changes**: ~4 files removed/modified (estimated 50-100 lines removed)
- **Testing**: Remove 1 test file, update others
- **Migration**: Optional backfill script for few-shot examples to Qdrant (one-time)

### Risk Signals

- **High risk**:
  - Breaking change to extraction prompt format (removes few-shot section)
  - Requires coordination with frontend (settings UI removal)
  - Workspace isolation change affects all RAG results (may impact quality)
- **Medium risk**:
  - Qdrant adapter changes (adding filter) - tested via existing search tests
  - Embedding service remains unchanged (Ollama still used)
- **Low risk**:
  - Configuration changes (RAG params stay global)
  - Database schema changes (drop JSONB column, add workspace_id to Qdrant payload)

### Risk Mitigation

- Feature flag: `use_rag_only` (default true) to toggle between old/new behavior
- Backward compatibility: Keep few-shot column until v2, ignore if present
- Monitoring: Track RAG hit/miss rates post-migration
- Documentation: Update workspace settings guide to explain RAG-only mode

## Key Learnings

1. The current few-shot + RAG dual-prompt architecture creates complexity in prompt maintenance and user configuration.
2. Workspace isolation is a critical multi-tenancy requirement that was missing in the initial vector store implementation.
3. Embedding service coupling to Ollama creates a deployment barrier for serverless environments like Vercel.
4. Migrating from user-curated few-shot examples to automatic RAG requires careful handling of existing user data to avoid trust erosion.
5. The extraction service's dependency on multiple ports (LLM, vector, prompt) makes it a sensitive integration point requiring coordinated changes.
