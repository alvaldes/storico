# ODD Feature: rag-per-environment

> **Status**: **code complete, uncommitted; production configuration still pending on the VM.**
> The five-file change is green (`786 passed, 21 skipped`, `ruff check` clean) and the owner's UI
> test is blocked only by the VM's `.env`, which this session cannot write.
> **Independent verification completed** — the owner asked for it to be stopped, and it had already
> reached its conclusion. It confirmed C1–C8 and C10, corrected C1, C6 and C11, refuted one sub-claim
> of C11, and could not reproduce the one-off suite failure in **18 full-suite runs**. Its findings
> are recorded as V1–V7 below. **The delivered code files hash exactly to the snapshot it verified**
> (all seven re-checked by the parent with `shasum -a 256`), so the verdicts apply to what shipped.
> The verification ran against the working tree **while this session was committing to it** — a
> process defect on the parent's side, recorded as V1.
>
> **Confirmed end to end in production on 2026-09-24**, after the VM's `.env` was completed: a real
> story extracted from `storico.vercel.app` produced 12 tasks and **one point in
> `storico_extractions_prod`** carrying the matching `workspace_id` and `user_story_id`. See
> "Production confirmation" below.
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

## Independent verification (completed 2026-09-24)

The verifier worked from C1–C11, ran ten mutations (each killed its target test, all reverted), and
reported the following. Verdicts are the verifier's; the notes are what changed as a result.

| Claim | Verdict | What needs saying |
| --- | --- | --- |
| C1 returns `False`, never raises | **CONFIRMED WITH CORRECTION** | **"Never raises" is measurably false.** `_get_client` calls `_check_dimensions()` *before* its `try` (`qdrant_adapter.py:86-87`), so a dimension mismatch raises `ValueError` out of `store_extraction` — and that path emits none of the new ERROR records, because the caller's own `except` catches it first. Pre-existing, outside the three named paths, and the port docstring is the thing that is wrong. |
| C2 one ERROR per path, stable reasons | CONFIRMED | Four mutations killed (`empty_embedding`, `client_unavailable`, the upsert severity, and dropping the log). |
| C3 `/healthz` + conditional `api-key`, no leakage | CONFIRMED | Reverting to `/health` kills two tests. |
| C4 embeddings probe shape and degradation | CONFIRMED | An unknown provider measured → `not configured`, no raise. |
| C5 the reported model is the one the adapter uses | CONFIRMED | `embedding_model_for()` is read by all three branches of `get_embedding_port`, so drift is structurally impossible; measured against real adapters for the three providers; two mutations killed. |
| C6 the 60 s cache | **CONFIRMED WITH CORRECTIONS** | (a) the reset fixture is **local to `test_health_services.py`**, not suite-wide — `tests/test_health.py` runs the real cache with no reset. (b) **The cache stores error results too**, so an operator who fixes a provider to recover without a process restart sees the stale `error` for up to 60 s. (c) **No in-flight dedup**: 10 concurrent cold calls measured **10 provider embeds**. The cost guard holds for polling and not for concurrency. |
| C7 no key material in the body | CONFIRMED | Planted key and a `ConnectError` carrying it; neither surfaced. |
| C8 suite and lint green | CONFIRMED | `786 passed, 21 skipped`, `ruff` clean, reproduced on the verified snapshot. |
| C9 the one-off suite failure | **NOT REPRODUCED** | 18 full-suite + 40 module + 60 isolated runs, all green. No order- or state-dependence found. The parent's `latency_ms` hypothesis is **not confirmed**; the cause is **unidentified**. The verifier declined to call it flaky without evidence, which is the right answer. |
| C10 the pre-existing tests it edited | CONFIRMED | They got stronger, not weaker (the exact-services dict gained a key and an explicit reason assertion). |
| C11 the settings fake is now hermetic | **CONFIRMED WITH CORRECTION, one sub-claim REFUTED** | OS environment variables still leak into it (measured). And the claim that seeding from a real `Settings` makes the previously-bad fake *unwritable* is **false** — measured: it is still writable. What actually prevents the misreport is `embedding_model_for()` reading the provider-specific field, not the fake's construction. The fake change removed a trap; it did not close the class. |

### Findings the verifier raised that were not claimed

| # | Severity | Finding |
| --- | --- | --- |
| V1 | **High (process)** | The verification target mutated mid-run because the parent committed while it worked. No corruption — the committed blobs equal the verified hashes, re-checked by the parent. The lesson is the parent's: a verifier and a committing hands are not compatible, and "stop" does not un-send a queue. |
| V2 | **Medium** | `tests/test_health.py::test_health_services_endpoint` exercises the **real** `_check_embeddings` with no patch, so the default suite makes a real — possibly billable — provider call on any machine with a live Ollama or a cloud key in env, and caches it process-wide for 60 s. Environment-dependent and untested here. **The first thing to fix next.** |
| V3 | Low-Medium | Cache stampede (C6c): the unauthenticated route's cost guard does not dedupe in-flight probes. |
| V4 | Low | The port docstring's "Never raises" (C1). Pre-existing. |
| V5 | Low | A record claim that the T1 log carries "the provider": the `extra` carries `extraction_id`, `collection` and `reason`. **Already corrected** by the Tasks rewrite before this section was written; the verifier read the earlier revision. |
| V6 | Low | A mis-provisioned prod now emits one ERROR per extraction (intended) and the probe logs exception text server-side; log volume and alerting deserve a thought. No new secret exposure. |
| V7 | Info | `pytest --cov` cannot run in this environment: `tests/conftest.py:116` hits a numpy "cannot load module more than once" `ImportError`. Pre-existing and outside this diff; branch coverage was argued from the ten mutations instead. |

## Production confirmation (2026-09-24)

The VM's `.env` held **four** variables before this batch, none of them about the RAG
(`DATABASE_URL`, `ENCRYPTION_KEY`, `AUTH_JWT_SECRET`, `AUTH_ALLOWED_ORIGINS`). Seven were appended —
`EMBEDDING_PROVIDER=google`, `GOOGLE_API_KEY`, `GOOGLE_EMBEDDING_MODEL=gemini-embedding-001`,
`EMBEDDING_DIMENSIONS=768`, `QDRANT_URL`, `QDRANT_API_KEY`,
`QDRANT_COLLECTION=storico_extractions_prod` — a backup was taken first, and the container was
**recreated** (a `restart` does not re-read `--env-file`).

A session outside this one ran the end-to-end test. Its evidence was **re-measured here** rather than
taken on trust:

| Check | Result |
| --- | --- |
| Collection `storico_extractions_prod` | `green`, **1 point**, 768 dims, Cosine |
| Point payload | `workspace_id` and `user_story_id` match the story that was extracted |
| `user_story_text` | **132 characters** — the same count the UI reported when validating the story, so the exact text was stored and not a variant |
| `/health/services` | `qdrant: ok` (517 ms, a real round trip) and `embeddings: ok` → `google` / `gemini-embedding-001` / 768 |

The 517 ms against the 8.7 ms the broken probe used to report is the signature that separates a
refused local connection from a real cloud call, which is what made the original defect invisible.

### Two findings from that run

| # | Finding | Disposition |
| --- | --- | --- |
| F5 | **`tasks_summary` looked truncated** (`"…"` in the dashboard). | **Closed, not a bug.** The stored payload is **2916 characters** and ends in a complete sentence, with no ellipsis character anywhere. It was the dashboard's table render. |
| F6 | **`confidence_score` is `null`.** | **Closed as a finding, opened as a question.** Not a calculation bug, not a deprecated field and not something the model returns: only the LLM-as-a-Judge fills it, and nothing in the product turns the judge on. See the next section. |

### F6 — the LLM-as-a-Judge is unreachable from the product

The judge is implemented (`domain/services/extraction_judge_service.py`, `prompts/single_judge.j2`)
and **wired** into the API path (`extraction_task.py:378`). It is gated by `validate`
(`extraction_task.py:404`), and:

- the frontend hardcodes `run_validation: false` (`frontend/src/lib/tasks-api.ts:107`), with no option
  to change it;
- the endpoint's own default is `False` (`api/schemas/extraction.py:61`);
- **nothing in the repository sets it to `true`**;
- and `grep -rn "validate=True" backend/tests/` returns **nothing**: the **flag-gated** path has no
  test. What *is* covered is the arithmetic on the **ungated** path: `test_extraction_service.py:283`
  pins `confidence_score == 45 / 50.0`, and `:306` covers the `LLMError` → `None` case. Neither looks
  at a boundary, which is how the two defects below survived.

The capability *is* reachable through the API — a client sending `run_validation: true` turns it on.
What cannot reach it is the web application. `AGENTS.md` states the capability in four places (core
feature #6, the executive description, the pipeline step and ADR-009), so the honest options are to
turn the judge on (one extra LLM call per extraction) or to correct those four claims, and that is the
owner's decision, not this batch's.

**Two preconditions for the "turn it on" option**, raised by the peer session that re-verified this
section and **re-measured here**:

1. **The judge's own failure path is silent.** `extraction_task.py:418-426` catches `LLMError`, logs a
   single `warning` and leaves `confidence = None`. With the flag **on**, a transient judge failure
   produces the *same* `confidence_score: null` in the row and in the point as the flag-**off** case —
   indistinguishable in the persisted data. Off, the null is intentional and consistent; on, it becomes
   ambiguous (did the judge not run, or did it fail?). If the judge is turned on, that path has to
   leave a mark in the payload or in `error_info`, not only in the logs. It is the same 
   silent-degradation shape as the RAG no-op this batch fixed.
2. **`total_score` enters unclamped, on both ends.** `extraction_judge_service.py:121,133` takes `int()`
   straight from the model's JSON with no range check, and `extraction_task.py:415` divides by a fixed
   `50.0` with the only cap being *downward* (0.5 when the judge did not approve). Measured by feeding
   crafted payloads through `_parse_judge_response`:

   | `total_score` from the model | `confidence_score` persisted |
   | --- | --- |
   | 45 | `0.9` |
   | 50 | `1.0` |
   | **75** | **`1.5`** — above the declared range |
   | **-5** | **`-0.1`** — negative, also open |
   | 75 with `approved: false` | `0.5` — the approval cap does work |

   The prompt declares `"total_score": 0-50` and five criteria at `0-10`, so a compliant model stays in
   range; nothing in the code enforces it, and `JudgeResult` is a plain class with no validation.
   Latent while the flag is off, and a precondition for turning it on rather than a detail to handle
   afterwards. A `min(1.0, …)` closes one end and a clamp of `total_score` to `[0, 50]` closes both.

   **Where the clamp goes matters, and it is not the caller.** There is a **second call site** of the
   judge that does not consult the flag at all: `domain/services/extraction_service.py:266` runs
   `if self._judge_service is not None:` and repeats the same arithmetic *and* the same silent
   `except LLMError`. It has **no production caller** — `grep -rn "extract_and_persist" backend/src`
   returns only its own definition, and the callers are tests — so F6's conclusion does not move, but a
   clamp added to `extraction_task.py:415` would fix one path and leave the other byte-identical. It
   belongs in `_parse_judge_response` or in `JudgeResult`.

   **And the parser lets a whole family of type errors through the judge's own guard.** Measured
   through `_parse_judge_response`:

   | Model output | Raised | Caught by the judge's `except LLMError`? |
   | --- | --- | --- |
   | `total_score: "abc"` | `ValueError` | **No** |
   | `total_score: null` | `TypeError` | **No** |
   | `total_score: [1]` | `TypeError` | **No** |
   | `total_score: {"x": 1}` | `TypeError` | **No** |
   | `coherence: 5` (not a dict) | `AttributeError` | **No** |
   | `coherence: null` | `AttributeError` | **No** |
   | malformed JSON (control) | `LLMError` | Yes |
   | non-dict top level (control) | `LLMError` | Yes |

   `validate()` wraps only the LLM call — `return self._parse_judge_response(raw_response)` sits
   **outside** its `try` — so nothing converts these. They reach `extraction_task.py:134`'s
   `except Exception`, which classifies them as transient: exponential backoff, `max_retries`
   attempts, and a failed extraction whose `error_info` says "unexpected error after N attempts". That
   is a **deterministic** error retried as if it were a network blip, with a message pointing at the
   wrong place. Less severe than the two silent defects, because this one does fail loudly, and the
   same family: judge output entering the system unvalidated.

   **And the obvious fix for it makes things worse.** Widening the guard to also catch
   `ValueError`/`TypeError`/`AttributeError` moves the only *visible* failure into the silent family.
   Measured by modelling the caller both ways:

   | Case | `except LLMError` (today) | Widened `except` |
   | --- | --- | --- |
   | flag off | `None` | `None` |
   | on, judge OK | `0.9` | `0.9` |
   | on, transient failure | `None` | `None` |
   | on, unusable output | **propagates `ValueError`** — visible | **`None`** — silent |

   So the three defects are not fixed in the same place, and the third must **not** be fixed by
   widening the catch: that is exactly the direction this record's own conclusion says not to take.
   The shape that respects it:

   1. **Coerce and clamp at the boundary** — in `_parse_judge_response` or in `JudgeResult` — so the
      judge's output is always a well-defined score in `[0, 50]`.
   2. **An uncoercible input becomes a classified failure**, not a swallowed one.
   3. **The persisted result has to distinguish three states, not two.** Today the `extractions` row
      can already separate "not requested" from "ran", through `prompt_config.validate`
      (`extraction_task.py:439`) — but the **Qdrant point payload cannot**: measured, it carries seven
      keys and no `prompt_config`. A `null` in the point is therefore ambiguous **by construction**,
      whatever is done to the judge.

## Still open

1. **V2** is the most concrete debt this batch creates: a test that reaches a real provider. It needs its own slice.
2. **V3, V4, V6** — recorded above with their measurements, each small, none blocking.
3. **C9/F4**: a full-suite failure with no reproduction and no known cause, after 18 full-suite runs by
   the verifier and 10 by the parent. Not called flaky, because nobody has evidence.
4. **F6 — the judge**: turn it on with tests **and the three preconditions recorded above** (a judge
   failure that leaves a mark, a score clamped at the boundary, and uncoercible output classified
   rather than swallowed), or remove the claim from `AGENTS.md` and the pipeline docs.
5. **The 19 verification points** and the now-unused `storico_extractions` collection. Deleting points
   is a destructive mutation and stays the owner's decision.
6. **`task_type` on the query side.** `GoogleEmbeddingAdapter` sends `RETRIEVAL_DOCUMENT` for both the
   stored document and the search query; Google's asymmetric task types (`RETRIEVAL_QUERY`) exist to
   improve retrieval. Quality, not correctness.
7. **A collection/embedding-model marker**, so a typo in `STORICO_QDRANT_COLLECTION` cannot silently
   mix spaces across environments — which is exactly the residual risk D2 left open.
