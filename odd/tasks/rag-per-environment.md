# ODD Feature: rag-per-environment

> **Status**: **code complete, uncommitted; production configuration still pending on the VM.**
> The five-file change is green (`786 passed, 21 skipped`, `ruff check` clean) and the owner's UI
> test is blocked only by the VM's `.env`, which this session cannot write.
> **Independent verification was started and stopped by the owner** before it reported, so this
> candidate carries no independent verdict — recorded plainly rather than glossed, and one
> full-suite failure observed during review was never reproduced (see F4).
> **Created**: 2026-09-24
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/rag-per-environment`.
> **Receipt-driven development**: **off** in this clone (decided by clone_local); global is on. The
> switch was re-read this session, not copied forward — the mistake `rich-store-errors.md` records.

## Problem

An extraction made from **production** (`https://storico.vercel.app`, workspace
`01a0d487-228b-7660-9e05-0ae0ddd69fd2`) produced **no point in Qdrant**. The collection stayed at
19 points before and after, and a payload filter on that `workspace_id` returned `0`. The dashboard
screenshot and a scroll of the collection agree: no point from that workspace exists.

Nothing failed visibly: the extraction completed and the tasks were generated. **The RAG write was a
silent no-op**, which is the backend instance of the class `rich-store-errors.md` already named —
*"silent failure is a class, not an instance."*

## Findings measured before writing

| # | Finding | Evidence |
| --- | --- | --- |
| P1 | **Production cannot reach an Ollama, and the embedding provider is global.** `ST stor…` defaults to `ollama` + `nomic-embed-text` + `STORICO_OLLAMA_HOST`; the prod container is `docker run --network host` with **no** Ollama service, and the compose `storico-ollama` is dev-only. | `GET https://storico-api.163.192.150.75.sslip.io/api/v1/health/services` → `"ollama": {"status": "error", "error": "not reachable", "latency_ms": 9.6}` against `database` at 690 ms: a local refused connection, not a network timeout |
| P2 | **The failure chain is silent, and the `bool` is discarded.** `EmbeddingService.embed` catches `ConnectError` → `logger.warning` → `return []`; `QdrantAdapter.store_extraction` → `if not embedding: return False` (**no log at all**); `_store_rag` awaits it and **drops the return value**. Because the embedding is empty, `store_extraction` returns **before** the Qdrant client is touched. | `infrastructure/vector/embedding_service.py`, `qdrant_adapter.py`, `infrastructure/tasks/extraction_task.py:557` |
| P3 | **Embeddings are global, workspace credentials are per-workspace and encrypted.** The extraction LLM is per workspace (`workspace_llm_configs`, Fernet-encrypted); `STORICO_EMBEDDING_PROVIDER` is a process setting. "Fall back to the workspace's extraction provider" therefore needs to embed with a *workspace's* decrypted credential — an architecture change, not a `try/except`. | `config/settings.py`, `workspace_llm_configs` rows |
| P4 | **There is no way to point the OpenAI embedding adapter at a custom endpoint.** `get_embedding_port` builds `OpenAIEmbeddingAdapter(api_key, model, dimensions)` with **no `base_url`**, and no `STORICO_OPENAI_BASE_URL` exists. The owner's custom provider (`https://api.nan.builders/v1/`) is therefore unreachable for embeddings even if it served `/v1/embeddings`. | `infrastructure/vector/__init__.py` |
| P5 | **Anthropic cannot embed, so no universal fallback exists.** `KNOWN_PROVIDERS = ("ollama", "openai", "anthropic", "gemini")` but embedding adapters are only `ollama`, `openai`, `google`. | `api/schemas/custom_provider.py:32`, `infrastructure/vector/` |
| P6 | **A runtime fallback would corrupt the collection, and the existing guard cannot see it.** `_check_dimensions()` compares **dimensions**, not **spaces**: vectors from two different models are incomparable even at the same 768 dims, so a mid-collection provider switch yields similarity scores that mean nothing while every check stays green. Workspace isolation prevents cross-workspace reads, not this. | `qdrant_adapter.py::_check_dimensions`, `search_similar` (always sends a `workspace_id` filter) |
| P7 | **The Qdrant health probe is wrong against Qdrant Cloud.** `_check_qdrant` sends `GET {url}/health` **without the API key**. Measured on the configured cluster: `/health` without a key → **403** (auth runs before routing), with a key → **404** (that route does not exist); `/healthz`, `/livez`, `/readyz` → **200** with a key. So the probe reports `not reachable` for a fully working cluster. | `api/routes/health.py::_check_qdrant`; four live probes |
| P8 | **One collection is shared by dev and prod.** `qdrant_collection` defaults to `storico_extractions` and both environments read the same value. Mixing `nomic-embed-text` (dev) with a cloud embedding model (prod) in one collection is exactly P6, reached by configuration instead of by a fallback. | `config/settings.py` |
| P9 | **Two claims this batch was about to repeat were stale.** F12 (`logger.info` dropped under plain `uvicorn`) was fixed by `5d10652` — verified live: with no manual `basicConfig`, application records reach stderr with the app's own formatter. F13 (`model_used: ""` on every RAG point) was fixed by `f354bfd`. Both are in `origin/main`. The 19 pre-existing points predate the fix, which is why they still carry `""`. | `git log`, local run on port 8012 |

## Decisions

| # | Decision | Choice |
| --- | --- | --- |
| D1 | Where production's embeddings come from | **Google**, `gemini-embedding-001`. The plan named `text-embedding-004` until it was probed live and answered 404 (F1); the current model honours `output_dimensionality=768`, so the vector size still matches the collection. No Ollama on the VM. |
| D2 | Whether to fall back to the extraction provider when Ollama is down | **No runtime fallback.** Rejected on P3, P5 and P6: it is impossible for Anthropic, requires embedding with per-workspace credentials, and silently changes the vector space. The environment's provider is configured **explicitly** instead. |
| D3 | How environments stay apart | **One collection per environment**: `storico_extractions_dev` (dev, `nomic-embed-text`) and `storico_extractions_prod` (prod, Google). The mechanism already exists (`STORICO_QDRANT_COLLECTION`); this is configuration plus the documentation of the contract. |
| D4 | What changes in code | **The failure stops being silent** (P2) and **the diagnostic stops lying** (P7). These two are the fix; D1/D3 are configuration. Without D4, the next misconfiguration is invisible again, which is the whole cost of this incident. |
| D5 | Interface of the store port | **Unchanged** (`store_extraction -> bool`). Visibility is obtained with a loud log plus a real health probe, not by widening a port the seed job and the extraction path both depend on. |

## Findings measured while implementing

| # | Finding | Evidence |
| --- | --- | --- |
| F1 | **The Google embedding model in the code was retired.** `text-embedding-004`, the shipped default, answers `404 NOT_FOUND: models/text-embedding-004 is not found for API version v1beta, or is not supported for embedContent`. Probing the replacement with the owner's key: `gemini-embedding-001` → **768 dims**, `text-embedding-005` → 404. Had this shipped unprobed, prod would have failed again — visibly this time, but failed. | Live probe through the real adapter and SDK with the owner's key, three model names |
| F2 | **The delegated probe reported the wrong model, and its test hid it.** `_check_embeddings` reported `settings.embedding_model`, which is the **Ollama** model for every provider: with `google` configured it named `nomic-embed-text` while the adapter called `gemini-embedding-001`. A diagnostics field lying about the deployment it describes is precisely the defect this probe exists to remove. The test was green because its hand-written settings fake allowed a combination production cannot produce — `embedding_provider="google"` beside `embedding_model="text-embedding-004"`. | RED before the fix: `AssertionError: assert 'nomic-embed-text' == 'gemini-embedding-001'`. Measured mapping: `provider=google → adapter 'gemini-embedding-001'` vs `settings.embedding_model 'nomic-embed-text'` |
| F3 | **Two independent test suites were not hermetic in the same way.** The worker's own suite passed while its model assertion was wrong, and `tests/test_integration/test_few_shot_rag_qdrant.py` skips entirely in this environment (16 skipped, environmental). A green suite was again compatible with the defect — the pattern this repository has already named twice. | Focused run green with the wrong model; the fix was found by reading the diff, not by a test |
| F4 | **One full-suite failure, never reproduced.** `test_the_embeddings_probe_is_cached_within_the_ttl` failed once (`1 failed, 785 passed`, `1 warning` instead of the usual `2`). **Ten subsequent full-suite runs passed**, and 50 isolated runs of that test passed. The hypothesis that comparing the whole result dict — which carries a live `latency_ms` measurement — is a race was **measured and not confirmed**: with an instant fake port, six fresh probes all returned `latency_ms` `0.0`. The assertion was tightened anyway (stable fields compared, call count used as the cache signal) as a determinism improvement, **not** as a diagnosis. The cause is unknown. | `/tmp/suite_1.txt` … `/tmp/suite_6.txt`, all green; 0/50 isolated failures |
| F5 | **This session cannot write any `.env` file.** The safety policy blocks `.env`, `.env.example` and `backend/.env.example` as sensitive paths. Correct for credentials, and it means the per-environment configuration in T4/T5 is documentation plus a hand-off, not something this batch could apply. | Three blocked writes, reported by the tool |

## Tasks

- [x] T1 Make an empty embedding loud in `QdrantAdapter.store_extraction`. Three failure paths
      (`empty_embedding`, `client_unavailable`, `upsert_failed`) each log one `ERROR` with
      `extraction_id`, `collection` and `reason`; `False` is still returned and nothing raises; the
      port signature is untouched. (`46 passed` focused)
- [x] T2 Fix `_check_qdrant`: `/healthz` and the `api-key` header when configured, response still
      spelled and never echoing the URL, the key or the exception.
- [x] T3 Add the embeddings probe to `/health/services` (`provider`, `model`, `dimensions`,
      `vector_length`; `ValueError` → `not configured`; empty vector or any other failure →
      `not reachable`; never raises), cached in-process for 60 s so the public route cannot amplify
      the billable call. **Plus the review fix of F2**: `embedding_model_for()` is now the single home
      of the provider→model mapping and both `get_embedding_port` and the probe read it.
- [x] T4 Document the contract: `README.md` (the env table, including that
      `STORICO_EMBEDDING_MODEL` is Ollama-only), `docs/deployment.md` (the seven production variables
      and the one-collection-per-environment table), `prod.todo.md`, and the clarifying comments in
      `config/settings.py` and `google_embedding_adapter.py`. **The two `.env.example` files could not
      be edited (F5)** — the block to paste is in the hand-off below.
- [ ] T5 Point dev at `storico_extractions_dev` — **blocked (F5)**; the line is in the hand-off.
- [ ] T6 This record. Independent verification was **stopped by the owner** before reporting; the
      candidate is therefore unverified beyond its own tests and this review.

## Hand-off: what has to be applied outside this branch

**The VM's `/home/ubuntu/storico/backend/.env`** — without this, production still stores nothing:

```bash
STORICO_EMBEDDING_PROVIDER=google
STORICO_GOOGLE_API_KEY=<the owner's Google AI key>
STORICO_GOOGLE_EMBEDDING_MODEL=gemini-embedding-001
STORICO_EMBEDDING_DIMENSIONS=768
STORICO_QDRANT_URL=https://525f1fa2-22ba-44c5-bb5d-a3b83c98a6a4.us-east-2-0.aws.cloud.qdrant.io
STORICO_QDRANT_API_KEY=<the cluster key>
STORICO_QDRANT_COLLECTION=storico_extractions_prod
```

Applying it needs the container **recreated**, not restarted: the values arrive through
`docker run --env-file`, which `docker restart` does not re-read. The flags are the ones the deploy
workflow uses (`--name storico-api --restart unless-stopped --network host --env-file …`). A push to
`main` touching `backend/**` does it automatically; there is no `workflow_dispatch`, so the workflow
cannot be triggered by hand.

**The repo's `.env.example` and `backend/.env.example`** (blocked, F5): the Qdrant block should say
there is one collection per environment, and the embeddings block should say that
`STORICO_EMBEDDING_MODEL` applies **only to Ollama**, listing the three provider→variable pairs and
noting that `text-embedding-004` is retired.

**Dev's `.env`** (blocked, F5): add `STORICO_QDRANT_COLLECTION=storico_extractions_dev`.

## Still open

1. **No independent verification** of this candidate (stopped by the owner). F2 is the kind of defect
   that a verifier exists to find, and it was found by the parent's own read of the diff instead.
2. **F4**: a full-suite failure with no reproduction and no known cause.
3. **The 19 verification points** and the now-unused `storico_extractions` collection. Deleting points
   is a destructive mutation and stays the owner's decision.
4. **`task_type` on the query side.** `GoogleEmbeddingAdapter` sends `RETRIEVAL_DOCUMENT` for both the
   stored document and the search query; Google's asymmetric task types (`RETRIEVAL_QUERY`) exist to
   improve retrieval. Quality, not correctness.
5. **A collection/embedding-model marker**, so a typo in `STORICO_QDRANT_COLLECTION` cannot silently
   mix spaces across environments.
