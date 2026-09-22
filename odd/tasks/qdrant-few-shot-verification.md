# ODD Feature: qdrant-few-shot-verification

> **Status**: **landed**. Levels N0, N1, N2 and N3 all ran against real services (real Ollama embeddings, the real
> Qdrant cluster, the real chat transport) on 2026-09-22, the full N2/N3 table passes, the eight work units and
> the version bump are on `main`, and `v0.5.0` is tagged. Three findings came out of the run (F10, F11, F12) plus
> a fourth from the landing (F13); F11 corrects two claims this record had made about itself.
> **Created**: 2026-09-21
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `main` (the owner's practice for docs work here; the code fixes may want a branch).
> **Receipt-driven development**: on in this clone (decided by global).

## Problem

The `few-shot-qdrant` change shipped with `pass_with_warnings`, and its own verify report listed the
gap in words: *"Runtime-only checks still to confirm: (1) the embedding dimensions vs Qdrant collection
vector-size check, (2) the real seed job against live Qdrant / real embeddings, (3) live embedding
calls and a real workspace-scoped retrieval + end-to-end extraction — mocked SDKs only."*

Every automated proof of this feature mocks the vector store or the embedding SDK. `51 passed in
0.48s` is the measured cost of that: green tests that would stay green with Qdrant unreachable, with
the embedding model absent, and with the seed job writing point ids the server rejects.

The owner asked for a test case that proves the feature works against real services, and then
authorized the fixes and the migration it needs.

## Findings measured before writing

| # | Finding | Evidence |
| --- | --- | --- |
| F1 | **The configured database is at revision `0021`; the code is at `0026`.** Revision `0023` adds `extractions.completed_at` and the ORM declares it (`models/extraction.py:56`), so *every* extraction fails with `UndefinedColumn` until the upgrade runs. This is the same mismatch as the 2026-09-20 production incident. | `alembic current` → `0021`; `alembic heads` → `0026` |
| F2 | **`nomic-embed-text` was absent** from Ollama (only `llama3.1:8b`, `qwen3:8b`, `deepseek-r1:8b`). The default embedding provider is `ollama` + `nomic-embed-text`, so `embed()` returned `[]` and the few-shot section was **never** rendered — silently. Owner authorized; model pulled and verified at 768 dims. | `find ~/.ollama/models/manifests`; `curl /api/embeddings` → `dims 768` |
| F3 | **The seed job's point ids are invalid and the count lies.** `run_seed` builds `{workspace_id}:{index}` and Qdrant requires an unsigned integer or a UUID. `QdrantAdapter.store_extraction` swallows the rejection with a warning, then `run_seed` increments its counter anyway, printing `Seeded N few-shot example(s)` with zero points stored. | Live probe against the owner's cluster (throwaway collection, created/probed/deleted): `value <uuid>:0 is not a valid point ID, valid values are either an unsigned integer or a UUID` |
| F4 | **Nothing logs an injection.** `_fetch_rag_examples` logs `debug` on the skip paths and `warning` on failures; the success path is silent, so neither the logs nor the DB record whether RAG contributed to an extraction. | `domain/services/extraction_service.py` |
| F5 | **`STORICO_OLLAMA_BASE_URL` is not a setting.** `docker-compose.yml:60` and `README.md:69` both use it; the field is `ollama_host`, so the env name is `STORICO_OLLAMA_HOST`. `SettingsConfigDict(extra="ignore")` discards the compose value without a word, leaving `ollama_host` at `http://localhost:11434` **inside the container** — the Quick Start `make up` path cannot reach the `storico-ollama` service at all. | `config/settings.py`; `docker-compose.yml:60`; `README.md:69` |
| F6 | **The extraction model cannot stand in for the embedding model.** Measured, not assumed: `llama3.1:8b` declares `embedding length 4096` but its capabilities are `completion, tools` — no `embedding`. Ollama 0.32.5 answers `/api/embeddings` for it with HTTP 500 `This server does not support embeddings. Start it with '--embeddings'`, and that flag does not exist in this version (`ollama serve --embeddings` → `unknown flag`). Even if forced, 4096 dims contradict `OllamaEmbeddingAdapter._dimensions = 768`. | `ollama show llama3.1:8b`; two live probes; `ollama serve --help` |
| F7 | **The default suite wrote real points into the live cluster.** `tests/test_api/test_extraction.py` reached `run_background_extraction` without patching the vector store, so the task built a **real** `QdrantAdapter` with `collection_name=settings.qdrant_collection` and called the real Ollama embedding endpoint. Measured: the configured collection grew by exactly one point per full-suite run, each a `"As a user, I want to use seeded feature 0…"` story with `model_used=""`. Seven runs left seven orphan points. | point count of `storico_extractions` before/after a full suite run (grew by 1 each run); the leaking test plus `test_llm_failure_is_recorded_on_the_extraction` |
| F8 | **Two tests depended on the developer's `.env`.** `test_saving_a_key_without_a_master_key_is_refused` and `test_upgrade_refuses_to_run_without_a_master_key` established their premise with `monkeypatch.delenv("STORICO_ENCRYPTION_KEY")`, but `Settings` reads the absolute `_ENV_FILE` (repo-root `.env`), so the dotenv source kept supplying the key. They passed only while the developer's `.env` happened to lack it — which stopped being true the moment this case required one, and is also false in production. | full suite: `2 failed, 761 passed` after the key was added; both reverted to green once each test patched the lookup its production call site uses instead |
| F9 | **The Ollama chat adapter has never worked live** — the local extraction transport was broken, not just untested. `OllamaAdapter._build_payload` sent only `model`/`messages`/`options`, and Ollama's `/api/chat` **defaults to streaming NDJSON**, so a real response is several JSON objects, one per line. The single `response.json()` in `generate` then raised `json.JSONDecodeError: Extra data: line 2 column 1`. The word `stream` appeared nowhere in the adapter and `git log -S'"stream"' -- backend/src/storico/infrastructure/llm/` was empty, so this path never worked by any version; every real extraction row in the database is `gemini-2.5-flash`. `/api/chat` is called from exactly one place, so nothing else masked it. | live probe: `curl -s localhost:11434/api/chat -d '<payload without stream>'` → 5 NDJSON lines; with `"stream":false` → 1 JSON object. Capture: `tests/test_integration/test_ollama_chat_live.py` RED with `Extra data: line 2 column 1 (char 126)` |

### Answer to the owner's question (H2)

**Not feasible.** The chat models are refused by the server for embeddings, so `nomic-embed-text` is not
an optimization but a requirement of the port contract. The correct recovery is the one taken: pull the
embedding model. A second embedding-model option would need a per-model dimension source instead of the
hardcoded 768, which is a separate change and not needed to verify this feature.

### Blocker: the local extraction transport (F9)

The end-to-end extraction check in N2 was **blocked at the extraction step**, and the cause was the one
mocked test the whole feature relied on: `OllamaAdapter` called `/api/chat` without `stream: False`.
Ollama's chat endpoint defaults to streaming NDJSON, the real body is several JSON objects, and the
adapter's single `response.json()` raised `json.JSONDecodeError: Extra data: line 2 column 1 (char 126)`
— measured live on Ollama 0.32.5 before the fix. A mocked transport returns whatever dict the test wrote,
so `tests/test_unit/test_ollama_adapter.py` stayed green against a body the real server never sends.

Fixed by adding `"stream": False` to `_build_payload` (the only change; retry/backoff, timeouts and
`_parse_response` untouched), pinned in the fast unit suite, and proven by the new opt-in live test
`tests/test_integration/test_ollama_chat_live.py` (`STORICO_TEST_LIVE_OLLAMA=1`): RED with the decode
error above, GREEN after the one-key payload change. The blocker is **cleared** — the earlier claim that
"mocked SDKs only" was the gap understated it; this path had never worked by any version, so the Qdrant
+ few-shot end-to-end run can now reach the extraction step.

## Decisions

| # | Decision | Choice |
| --- | --- | --- |
| D1 | How to make the seed honest | **Both halves.** Deterministic *valid* UUID point ids (`uuid5`) so a rerun overwrites instead of duplicating, **and** a success signal from `store_extraction` so the counter cannot report work it did not do. Ids alone leave the lie in place with a different error. |
| D2 | What the success signal is | **`VectorStorePort.store_extraction` returns `bool`.** The port already documents "silently skips on any failure" — the skip was invisible to every caller. A truthy return value is the smallest change that lets the CLI count what actually landed. |
| D3 | What the injection log carries | **Count, scores, limit, threshold and `workspace_id`, never the user story text.** The story is user content in a log line; the numbers are what an evaluation needs. `logger.info` so it is visible at the default level. |
| D4 | How the compose defect is guarded | **A test that reads `docker-compose.yml` and asserts every `STORICO_*` key is a real `Settings` field.** This class of bug is invisible by construction (`extra="ignore"`), so a one-time rename would be fixed until the next rename. The README half is fixed but not parsed — a markdown table is not a contract. |
| D5 | Where the live verification lives | **A skip-gated integration test** (`tests/test_integration/test_few_shot_rag_qdrant.py`, gated on `STORICO_TEST_LIVE_QDRANT=1`) rather than a `/tmp` script, so the evidence is reproducible and the points it creates are deleted in a `finally`. |

## Tasks

- [x] T0 Measure H2 against the live Ollama and record the answer (F6).
- [x] T1 Pull `nomic-embed-text` and confirm 768 dims (F2).
- [x] T2 Fix F3: valid deterministic seed ids + honest counting, with tests. (`uuid5` ids; `VectorStorePort.store_extraction -> bool`; `24 passed`)
- [x] T3 Fix F4: `info` log on injection, with a test. (`11 passed`)
- [x] T4 Fix F5: compose + README env name, with the contract test. (`12 passed`; README table rebuilt from `settings.py`; both `.env.example` templates covered)
- [x] T5 Run `alembic upgrade head` on the configured database (authorized). `0021 -> 0026`; a Fernet master key was generated and added to the gitignored `.env` (backup kept outside the repo at `~/.storico-env-backups/`).
- [x] T6 Add the skip-gated live integration test for embeddings + Qdrant + prompt rendering. (`16 passed` with `STORICO_TEST_LIVE_QDRANT=1`)
- [x] T7 Fix F7/F8: stop the suite leaking into the live cluster, and make the two master-key tests environment-independent. (autouse guard in `tests/conftest.py` using `pytest.fail`, because the adapter's `except Exception` swallows an `AssertionError`; leak proof `7 -> 7` points)
- [x] T8 Fix F9: `"stream": False` in the Ollama chat payload, with an opt-in live test that does not mock the transport. (`2 passed`; full suite `763 passed, 21 skipped`)
- [x] T9 Clean the seven orphan Qdrant points (authorized). Cluster back to `0` points, one collection.
- [x] T10 **Re-run N2 end-to-end through the API.** Done 2026-09-22; see "T10 — the end-to-end re-run" below.
- [x] T11 Close: report outcome, pending checks, and the version decision. Landed 2026-09-22; see "T11" below.

## Verification case TC-FS-QDRANT-01

**Goal.** Prove that (a) real embeddings produce 768 dims, (b) the collection is created and indexed
correctly, (c) an extraction stores a point with its workspace tag, (d) retrieval from another
workspace never returns it, (e) the model receives `## Few-Shot Examples` only when it should, (f)
`limit`/`threshold`/`enabled` behave exactly as configured, and (g) Qdrant or embeddings being down
never breaks an extraction.

### N0 — Automated baseline (all mocked)

```bash
cd backend && .venv/bin/pytest -q \
  tests/test_unit/test_few_shot_retrieval.py tests/test_extraction_flow_few_shot.py \
  tests/test_few_shot_examples.py tests/test_services/test_seed_few_shot.py \
  tests/test_unit/test_vector_store.py tests/test_api/test_workspace_settings_prompts.py
cd frontend && pnpm vitest run src/components/react/__tests__/FewShotConfigEditor.test.tsx
```

Green here proves wiring only. It is the baseline the live levels must not contradict.

### N1 — Live infrastructure (real Ollama embeddings + real Qdrant, no LLM)

```bash
curl -s http://localhost:11434/api/embeddings -d '{"model":"nomic-embed-text","prompt":"login"}' \
  | python3 -c "import json,sys; print('dims', len(json.load(sys.stdin)['embedding']))"   # → 768

STORICO_TEST_LIVE_QDRANT=1 .venv/bin/pytest tests/test_integration/test_few_shot_rag_qdrant.py -v

curl -s -H "api-key: $STORICO_QDRANT_API_KEY" "$STORICO_QDRANT_URL/collections/storico_extractions" \
  | python3 -m json.tool
# → vectors.size 768, distance Cosine, payload_schema.workspace_id.data_type "keyword"
```

Expected from the integration test: a stored point is retrieved by its own workspace (score ~1.0),
retrieved by a **different** workspace 0 times, and the rendered prompt contains the section exactly
when the search returned something. Created points are deleted by the test.

### N2 — End-to-end through the API

```bash
cd backend && .venv/bin/uvicorn storico.api.app:create_app --factory --port 8000
cd frontend && pnpm dev            # http://localhost:4321
curl -s -o /dev/null -w '%{http_code}\n' http://localhost:8000/api/v1/health/ready   # → 200
```

| Step | Call | Expected |
| --- | --- | --- |
| Config defaults | `GET /api/v1/workspaces/{ws}/settings/prompts` | `enabled true`, `limit 3`, `threshold 0.85` |
| Config write | `PUT …/settings/prompts` `{"few_shot_limit":2,"few_shot_threshold":0.5}` | 200, persists on re-read |
| Validation | same PUT with `limit 0` / `threshold 1.5` / `few_shot_examples` | 422 each, nothing persisted |
| Authorization | same PUT as non-admin | 403, nothing persisted |
| Cold start | `POST /api/v1/workspaces/{ws}/extract/` with no prior points | 202 → `completed`, `completed_at` non-null, `tasks ≥ 1`, section absent |
| Warm start | same with a similar story and `threshold 0.5` | section present with ≥ 1 example from this workspace |
| `enabled=false` | same as warm | section absent |
| `threshold 0.99` | loosely related story | 0 hits → section absent |
| `threshold 0.0, limit 1` | similar story, 3 points | exactly 1 example |
| Isolation | populated workspace A, search as workspace B | 0 hits |

### N3 — Degradation (the spec's "Search failure is safe")

```bash
cd backend && STORICO_QDRANT_URL=http://127.0.0.1:6333 .venv/bin/uvicorn storico.api.app:create_app --factory --port 8001
cd backend && STORICO_EMBEDDING_MODEL=does-not-exist .venv/bin/uvicorn storico.api.app:create_app --factory --port 8002
```

Both must answer 202 → `completed` with `tasks ≥ 1` and a warning in the log. This is the most
important resilience assertion in the case: retrieval must never be able to fail an extraction.

### N4 — Seed job

```bash
cd backend && .venv/bin/python -m storico.cli.seed_few_shot
```

Current rows hold `few_shot_examples = null`, so the happy path needs a legacy row seeded by hand.
Expected after T2: either a valid point per example (count matches what Qdrant received) or a loud
failure — never `Seeded N` with an empty collection.

## Evidence log

| Step | Command | Result |
| --- | --- | --- |
| F1 | `alembic current` / `alembic heads` | `0021` vs `0026` |
| F3 | live Qdrant upsert with `<uuid>:0` | rejected: *not a valid point ID* |
| F6 | `ollama show llama3.1:8b` | `embedding length 4096`, capabilities `completion, tools` |
| F6 | `/api/embeddings` with `llama3.1:8b` | HTTP 500, no embedding supported |
| F2 | `ollama pull nomic-embed-text` + probe | `dims 768` |
| N0 | backend few-shot suite | `51 passed in 0.48s` |
| F9 | `curl -s localhost:11434/api/chat` without `stream` vs with `"stream":false` | NDJSON (5 lines) vs 1 JSON object |
| F9 | `git log -S'"stream"' -- backend/src/storico/infrastructure/llm/` | empty — the path never worked |
| F9 | live test RED (pre-fix) | `json.decoder.JSONDecodeError: Extra data: line 2 column 1 (char 126)` |
| F9 | live test GREEN + unit pin (post-fix) | `2 passed`; `16 passed`; full suite `763 passed, 21 skipped` |
| F9 | live Qdrant suite re-run | `16 passed` |
| N0 | frontend `FewShotConfigEditor` | `9 passed` |
| N0 | full backend suite (final state) | `763 passed, 21 skipped` |
| N1 | `STORICO_TEST_LIVE_QDRANT=1` live suite | `16 passed` — embeddings 768d, collection size/index, retrieval + isolation, prompt rendering (warm/cold/disabled/threshold/limit), degradation, and the seed job against the real server |
| N4 | seed job against live Qdrant | covered by the two live seed tests inside the 16; the CLI happy path needs a legacy row and stays unexercised by data |
| N2 | steps 1–5 (first run, pre-F9-fix) | **PASS**: defaults `true/3/0.85`; `PUT` persists `2/0.5`; `limit 0` / `threshold 1.5` / `few_shot_examples` all 422 with nothing persisted; non-member PUT **403** |
| N2 | step 6 cold start (first run) | **FAIL — blocker F9**: `status failed`, `error_info: Unexpected error during LLM generation: Extra data: line 2 column 1 (char 128)`, 0 tasks, 0 points. Reproduced twice. |
| N2 | step 12 degradation (first run) | **PARTIAL**: the `Failed to initialize Qdrant client` warning appeared on `:8001`, proving the vector-store failure was handled, but the extraction still failed on the chat transport. Now unblocked. |
| N2 | steps 6–13 (re-run) | **The "NOT RUN" claim was wrong — see F11.** A delegated re-run did execute between 00:24 and 00:43 UTC and left 8 `completed` extractions with 5–14 tasks and 7 points. Its per-step observations were never recorded, which is why this row said "not run". The verified re-run is the T10 run below. |
| F7 | leak proof after the guard | point count `7 -> 7` across a full suite run; no `storico_extractions_pytest_*` collection |
| F9 | live chat test | `STORICO_TEST_LIVE_OLLAMA=1` → `2 passed` (RED `Extra data: line 2 column 1 (char 126)` before the fix) |

## T10 — the end-to-end re-run (2026-09-22)

**How it ran.** A driver outside the repository (`/tmp/n2_drive.py`) started the API through
`/tmp/n2_launch.py`, minted its own HS256 JWT for the admin user, created fresh workspaces, and walked the
N2/N3 table. Evidence: `/tmp/n2_results_191257.jsonl` — one JSON line written to disk as each step finishes,
so a killed run keeps its findings — plus `/tmp/n2_uvicorn_8000.log`, `_8001`, `_8002`.

Preconditions measured: Ollama serving `nomic-embed-text` and `llama3.1:8b` on `127.0.0.1:11434`; no uvicorn
running; ports free; `/api/v1/health/ready` → 200. The API was started with the root logger at INFO **on
purpose** — see F12.

**The repository was not touched by the run.** `git status --porcelain | sort | sha256` was
`c55669484621e1acb2b9843dd59dd0dd0a89dad28b179805b10c514cf1026f71` before and after, HEAD `7230c33`.

### The table, all twelve steps

| # | Step | Observed | Verdict |
| --- | --- | --- | --- |
| 1 | config defaults | `enabled true`, `limit 3`, `threshold 0.85` on a fresh workspace | PASS |
| 2 | config write | 200 and the re-read holds `limit 2`, `threshold 0.5` | PASS |
| 3 | validation ×3 | 422 each, with the reason named: `greater_than_equal` (limit 0), `less_than_equal` (threshold 1.5), `extra_forbidden` (`few_shot_examples`) | PASS |
| 4 | authorization | non-member PUT → 403 `Not a member of this workspace` | PASS |
| 5 | cold start | `completed`, `completed_at` set, 7 tasks, **0** injection lines, 1 point stored | PASS |
| 6 | warm start | `completed`, 10 tasks, **1** injection line: `examples_count=1 limit=2 similarity_scores=[0.8863] threshold=0.5` | PASS |
| 7 | `enabled=false` | `completed`, 7 tasks, **0** injection lines, and the points still grew to 3 — disabling retrieval does not disable storage | PASS |
| 8 | `threshold=0.99` | `completed`, 7 tasks, **0** injection lines with a loosely related story | PASS |
| 9 | `threshold=0.0, limit=1` | `completed`, 10 tasks, exactly one example: `examples_count=1 limit=1 similarity_scores=[0.9632] threshold=0.0` | PASS |
| 10 | isolation | workspace B, searching while A holds 5 points: `completed`, 8 tasks, **0** injection lines for B; B keeps 1 point of its own | PASS |
| 11 | degradation, Qdrant unreachable (`:8001`) | `completed`, 8 tasks, 0 points stored, `WARNING … Failed to initialize Qdrant client: All connection attempts failed` | PASS |
| 12 | degradation, embedding model missing (`:8002`) | `completed`, 7 tasks, 0 points stored, `WARNING … Embedding model 'does-not-exist' not found in Ollama. Run: ollama pull does-not-exist` | PASS |

### The task counts are the corrected ones

The driver's own task assertion read the poll response's `tasks` field, which is structurally always empty
(F10), so the three FAIL rows it wrote (steps 5, 11, 12) are void. The counts above come from
`GET /api/v1/tasks/?user_story_id=…` for the same extractions, and the database agrees with the API row for
row: **7, 10, 7, 7, 10, 8, 8, 7**. Each of the eight extractions produced tasks, every story reached
`extracted`, and every extraction reached `completed` with `completed_at` set.

### Independent cross-checks (fresh processes, not the driver's own numbers)

| Check | Result |
| --- | --- |
| Points per workspace, scrolled from Qdrant | workspace A 5, workspace B 1, `:8001` 0, `:8002` 0 |
| Collection total | 18 points, all of them verification leftovers (see below), none from a real workspace |
| Repository untouched | tree fingerprint identical before and after, HEAD `7230c33` |

## Findings from the T10 run

| # | Finding | Evidence |
| --- | --- | --- |
| F10 | **The poll response's `tasks` field is always empty.** `ExtractionResponse.tasks` defaults to `[]` and none of its three construction sites (`routes/extractions.py:135` list, `:174` detail, `routes/extraction.py:288` status) passes `tasks=`. Measured: eight stories with 5–14 persisted tasks while the poll answered `tasks: []` every time. The case's original “tasks ≥ 1” criterion was written against that field and is therefore unverifiable through it; the working source is `GET /api/v1/tasks/?user_story_id=…`. Pre-existing, not part of this feature's diff. | driver rows `poll_tasks_field: 0` next to `tasks: 7…10`; `src/storico/api/routes/extractions.py` |
| F11 | **Two claims this record made about itself were wrong.** It said the N2 re-run was “NOT RUN — cancelled by the owner before the first step” and that Qdrant held “0 points after the orphan cleanup”. The database holds eight `completed` extractions (5–14 tasks, `llama3.1:8b`) created between 00:24 and 00:43 UTC in `verification-qdrant-fewshot-2` and `-2-b`, and seven points that carry their workspace ids. The re-run did execute; its per-step observations were never written down, which is why the record described it as not run. The “0 points” claim was measured *before* those extractions, not after. | workspace rows created 00:20:20 and 00:40:36 UTC, extractions completed 00:24:01 … 00:43:42 UTC; point payloads with those two workspace ids |
| F12 | **Under production's invocation, every application `logger.info` is dropped — including the injection line this case observes.** Nothing in the backend configures logging (`grep basicConfig\|dictConfig\|setLevel src/` finds only the seed CLI), and `backend/Dockerfile` runs plain `uvicorn`, whose `dictConfig` leaves the root logger at WARNING with no handler, so application records propagate to nothing and `logging.lastResort` discards INFO. A/B measured: the same warm extraction against a populated workspace logged the marker under the INFO-configured launcher and **zero** application records under plain `uvicorn` (log had 19 `INFO:` lines, all uvicorn's own, and 0 from `storico.*`). D3 chose this line as the observable; it is emitted but invisible in production, so the observable is only as good as the run's logging configuration. | `/tmp/n2_plain_uvicorn.log` (`storico_info_lines: 0`, `marker_lines: 0`) vs `/tmp/n2_results_191257.jsonl` |
| F13 | **The fidelity half is real and was measured; the double-write half was wrong and is refuted.** The module-level `_store_rag` (`infrastructure/tasks/extraction_task.py:535`) hardcodes `model_used=""` and passes no `confidence_score`, so every production-stored point loses the model and confidence while its `extractions` row records the real one — measured on point payloads for workspace `01a0c6ac-…` and `01a0c6b3-…` against `extractions.model_used = llama3.1:8b`. This row originally went further and claimed a second writer — "Last writer wins, so **every** extraction-stored point carries `model_used: ""`" and "each extraction is also embedded and upserted twice for the same point" — and that double-write claim was never true. Corrected the same way F11 corrected this record's claims about itself: the production path is `routes/extraction.py:239` → `run_background_extraction` → `_run_extraction` (`extraction_task.py:279`) → `extraction_service.extract(...)` (prompt, LLM, parse; no persistence, no vector store) → the task persists and calls module-level `_store_rag` **exactly once** (`extraction_task.py:460`). The other `_store_rag` (`domain/services/extraction_service.py:341`) has exactly one caller, `ExtractionService.extract_and_persist` (`:317`), and `grep -rn "extract_and_persist" backend/src/` returns only its own definition — no production path reaches it. Two mutually exclusive flows therefore own one `_store_rag` each: no last-writer-wins, and exactly one embed and one upsert per extraction. The duplicated flow is a code-duplication follow-up, not an I/O cost. The fidelity half was fixed on 2026-09-22 (payload fidelity, the `prod-honesty-followups` batch), so this row no longer reads as an open defect. Pre-existing and outside this feature's diff. | point payloads for workspace `01a0c6ac-…` and `01a0c6b3-…`: `model_used: ""`; `extractions.model_used = llama3.1:8b`; the refutation is the code-path reading above |

## State at T10 close (2026-09-22)

**Nothing is committed.** `git status` shows **17 modified files and 4 untracked ones** (this record, the two
new test modules, and the Qdrant live integration test) — the earlier count of “15” was itself off by two.
The work-unit commits still have to be made, with the review switch deciding whether native review runs.

**Left behind in live services** (all deliberate, none of it withdrawn):

| Where | What |
| --- | --- |
| Database | **Ten** verification workspaces, all left by this case: `verification-qdrant-fewshot` (2 **failed** extractions), `verification-qdrant-fewshot-2` (6 completed, 5–14 tasks), `verification-qdrant-fewshot-2-b` (2 completed), `verify-qdrant-2-185708` (5 completed; its delegated run died on a network timeout, so its `-2b` sibling was left with 1 extraction stuck `pending` and 0 tasks), `verify-qdrant-2-191257` (5 completed), `verify-qdrant-2b-191257` (1 completed), the two degradation workspaces `verify-qdrant-8001-191257` / `verify-qdrant-8002-191257`, and `preflight-185458` (created by the parent's pre-flight of the driver, story but no extraction). The database holds 14 workspaces in total, so four belong to real users and none of them was touched. |
| Qdrant | `storico_extractions` holds **18 points, all of them this case's leftovers**: 11 in the four `verify-qdrant-*` workspaces of the two 2026-09-22 runs and 7 in `verification-qdrant-fewshot-2` / `-2-b`. No point belongs to a real workspace, and none carries the F7 test-suite story text |
| Ollama | `nomic-embed-text` pulled (274 MB) and `nomic-embed-text` + `llama3.1:8b` served; `ollama serve` was started by this session |
| `.env` (gitignored) | `STORICO_ENCRYPTION_KEY` added; the pre-change copy is at `~/.storico-env-backups/.env.bak-20260921170846` — keep the key, losing it makes the one encrypted workspace credential unreadable |

## T11 — the landing (2026-09-22)

**The eight work units, one commit each, in this order** (`main` fast-forwarded from `7230c33`):

| Commit | Unit | Files |
| --- | --- | --- |
| `08b4f85` | `fix(llm)`: disable streaming in the Ollama chat payload (F9) | `ollama_adapter.py`, `test_ollama_adapter.py`, `test_ollama_chat_live.py` |
| `a135bb7` | `fix(vector)`: valid seed ids and an honest count (F3/D1/D2) | `seed_few_shot.py`, `vector_store_port.py`, `qdrant_adapter.py`, `test_seed_few_shot.py`, `test_vector_store.py` |
| `03a9454` | `feat(observability)`: log the few-shot injection (F4/D3) | `extraction_service.py`, `test_few_shot_retrieval.py` |
| `f209b6d` | `fix(config)`: name the Ollama setting the application reads (F5/D4) | `docker-compose.yml`, `README.md`, both `.env.example`, `test_env_contract.py` |
| `d8693b3` | `test(isolation)`: stop the suite writing into the live vector store (F7) | `tests/conftest.py`, `test_api/test_extraction.py` |
| `424d8e0` | `test(isolation)`: free the master-key tests from the developer `.env` (F8) | `test_workspace_settings_llm_config.py`, `test_encrypt_workspace_api_keys_migration.py` |
| `28ea388` | `test(integration)`: the live Qdrant few-shot suite (D5) | `test_few_shot_rag_qdrant.py` |
| `f4d7d91` | `docs(odd)`: this record | `odd/tasks/qdrant-few-shot-verification.md` |

The two isolation units were one commit in the earlier plan. They are separate here because their root causes
differ: one is the suite reaching the live cluster, the other is tests whose premise came from the developer's
`.env`.

**Gates, run before the first commit** (by a delegated read-only verifier, on this exact tree):
`ruff check src tests` clean, `ruff format --check` (234 files), `pytest -q` → **`763 passed, 21 skipped, 1 warning in 30.09s`**
and the Qdrant collection went **19 → 19** across the suite, so the F7 guard still holds. The single warning is a
third-party SQLAlchemy `RuntimeWarning`; nothing gates on warnings.

**Release**: `make bump` → `cz bump` reported `version 0.4.0 → 0.5.0`, increment MINOR, commit `78d6e23`
(`CHANGELOG.md` + the three version files), tag **`v0.5.0`**. All three manifests read 0.5.0 and `git describe`
reports `v0.5.0`. 1.0.0 was not reachable on the documented path: `.cz.toml` sets `major_version_zero = true`.

**Nine native reviews, all approved and burned** (one per commit plus the bump), each bound to its own commit
with an explicit `baseRef` and `committedOnly: true` and inspected from a detached HEAD at that commit:

| Candidate | Tier | Lenses | Model runs | Advisories |
| --- | --- | --- | --- | --- |
| `08b4f85` | medium | 1 (`review-reliability`) | 1 | `R3-live-client-private` |
| `a135bb7` | medium | 1 | 1 | `R3-adapter-upsert-result-ignored`, `R3-mock-return-contract`, `R3-uuid5-namespace`, `R3-weaker-id-assertion` |
| `03a9454` | medium | 1 | 1 | `R3-caplog-coupling`, `R3-log-fields` |
| `f209b6d` | medium | 1 | 1 | `R3-doc-db-default-mismatch`, `R3-test-regex-value-shape` |
| `d8693b3` | medium | 1 | 1 | `R3-guard-scope`, `R3-helper-placement` |
| `424d8e0` | medium | 1 | 1 | `R3-hermetic-keyless-settings` |
| `28ea388` | medium | 1 | 1 | `R3-001` to `R3-004` |
| `f4d7d91` | low | 0 | 0 | none, `non_executable_only` |
| `78d6e23` (bump) | medium | 1 | 1 | none |

Every finding is `SUGGESTION` / `informational`: none opened a correction, and each closure says so in its own
words. **Sixteen non-blocking findings across the nine candidates.** The closures carry each finding's id, lens,
location and severity but **no text**, so they are listed here as identifiers rather than paraphrased.

The bump candidate is the clean measurement of the tier trap: a version-only diff (28 changed lines across
`CHANGELOG.md` and the three manifests) came out `medium` with a lens, because `backend/pyproject.toml` is read as
a configuration change. A docs-only commit came out `low` with zero lenses and cost no model run.

**Not done, and on purpose**: nothing was pushed. Delivery follows ordinary repository policy, so `origin/main`
is still at `7230c33` and the tag exists only locally. (Dated outcome, 2026-09-22: the owner later decided
otherwise — the work and the `v0.5.0` tag are on `origin/main`, measured with `git ls-remote --tags origin`
and `git merge-base --is-ancestor`.)

**Still open after this landing**:

1. **F10**, recorded above and deliberately not fixed here: it pre-exists this feature's diff, and fixing
it would change code the verification just certified green. (F13 was on this list too, and the cost sentence
this item carried — "F13 also costs one extra embedding and upsert per extraction" — was wrong: there is
exactly one embed and one upsert per extraction, because the two `_store_rag` implementations belong to two
mutually exclusive flows; see the corrected F13 row. F13's fidelity half was fixed on 2026-09-22 in the
`prod-honesty-followups` batch, so it is no longer open.)
2. **F12**: under production's plain `uvicorn`, application INFO records are discarded, so the injection line
this feature added is invisible there. The fix is a logging configuration the backend does not have; it is a
change of its own.
3. **The 16 advisories** above, none blocking, each naming a file and a line range.
4. **The test data left in live services** (the 10 workspaces and 18 points in the table above). Removing it is a
destructive mutation and stays a decision, not an assumption.
