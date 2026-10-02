# Verification — extraction-versioning-api (slice (b))

**Head verified:** `75e679e` (`feat/extraction-versioning-api-wu6b`), the last commit of the nine-PR chain
#31 → … → #39. **Nothing is merged:** every line below describes the branch state, and production is
still at `0028`.

**The rule this file follows:** a skip is not a proof, and CI's green is not this machine's green. Each
block says where it ran, what it proved, and what it did not.

## 1. What ran where

| Layer | Command | Where | Observed |
| --- | --- | --- | --- |
| Backend suite, no marker filter | `conda run -n storico python -m pytest -q` | this machine | **1206 passed, 36 skipped** |
| Backend suite, no marker filter | same | CI (Docker runner) | **1224 passed, 18 skipped** |
| Frontend suite | `pnpm test` | both | **57 files, 665 tests passed** |
| Typecheck | `pnpm exec tsc --noEmit` | this machine | exit 0, no output |
| Build | `pnpm build` | this machine | completes (Astro + Vercel adapter) |
| Lint | `conda run -n storico python -m ruff check src tests` | both | All checks passed |
| Format | `conda run -n storico python -m ruff format --check src tests` | both | **269 files** already formatted |

The two backend numbers reconcile exactly, and the reconciliation is the evidence: **1242 collected =
1206 + 36**, and `1206 + 36 (local) − 18 (the Docker-gated ones that executed in CI) = 1224`. So every
non-integration case passed in both places, and exactly the Docker-gated eighteen ran only in CI.

### The 36 skips, attributed (they are not one class)

| File | Cases | Gate |
| --- | --- | --- |
| `test_few_shot_rag_qdrant.py` | 16 | `STORICO_TEST_LIVE_QDRANT != "1"` |
| `test_extraction_versioning_schema.py` | 12 | Docker socket unreachable |
| `test_story_deletion_record.py` | 3 | Docker socket unreachable |
| `test_migration_chain.py` | 2 | Docker socket unreachable |
| `test_ollama_chat_live.py` | 2 | `STORICO_TEST_LIVE_OLLAMA != "1"` |
| `test_projects_integration.py` | 1 | Docker socket unreachable |

**18 of the 36 are Docker-gated and 18 are environment-flag opt-ins** — a correction to the assumption
that every skip here is "no Docker". The first class runs in CI; the second class (16 Qdrant + 2 Ollama
live) **skips everywhere** unless those flags are set, and nothing in this slice has ever run against a
real Qdrant or a real Ollama.

## 2. What each layer actually proved

**The SQLite unit and API layer (1206 cases, local and CI).** The HTTP contracts end to end through the
real FastAPI app: the owner-or-admin gate's refusals and their exact codes, the extract gate's ordering
(a refusal answers 403 even with an incomplete LLM config — the config check never leaks ahead of it),
the mark's 201/409/422/404 paths with row-count witnesses, the D16 match rule (casefold equality, no
similarity call reachable), the story deletion's ordering and its four-part 503 witness, and the
designed account-delete 409. The frontend suites prove the component and store behaviour, including
that a cancelled confirmation issues no request.

**Postgres via testcontainers (18 cases, CI only).** The invariants the SQLite layer cannot witness:
the story cascade taking its extractions, tasks and marks; the `story_deletions` record surviving that
cascade because it holds identity as values and no foreign key; deleting the actor nulling `deleted_by`
and nothing else; the partial unique index's real shape; `0029` reaching the head the packaged scripts
declare; the models-vs-migrated-schema drift ratchet still empty; and the `0027` downgrade round trip.

**What the SQLite layer cannot prove, stated rather than implied.** SQLite does not enforce foreign-key
actions by default — the unit schema carries the DDL but no action fires unless a test turns the pragma
on, which the deletion cases do explicitly. Index *names* and partial-index shapes are Postgres-only by
construction. So the cascade and the record's survival are CI's evidence, not local green.

**Lint, format, typecheck, build.** Clean in both places; the build gate runs in CI as well, so a broken
island import cannot land silently.

## 3. The one thing nothing in this slice proves (cross-slice, by design)

**D10's exclusion.** Slice (b) makes invalidation marks creatable and revocable, but **no task in this
slice calls `set_has_invalid_tasks`**, and `_store_rag` is untouched. The call sites are slice (c) WU3
tasks 3.6–3.8, which must run the refresh **before** the mark's relational write (a refresh failure has
to leave no mark persisted). Until (c) lands, **every mark in production excludes nothing from few-shot
retrieval and nothing goes red** — a silent failure with no test in this change able to catch it. It is
recorded in `tasks.md`'s Slice Boundary as the slice's one cross-slice dependency, and it is repeated
here because this is the file a reader consults when asking "what is done".

## 4. Residuals this slice names instead of absorbing

- **The account-delete race.** A revoke landing between D-a-4's pre-check and the delete still surfaces
  as the raw integrity refusal (500). Translating it belongs to `UserRepository.delete`, which the unit
  deliberately does not touch.
- **A mark that already succeeded is not rolled back** when the following `PUT` fails: the mark was
  legitimately applied and un-marking it would be a second write the user never asked for.
- **A failed `GET …/invalidations` on editor open treats the task as unmarked**; a duplicate attempt
  then meets the server's 409 `TASK_ALREADY_MARKED` with its mirrored copy.
- **`StoryDetail` re-fetches tasks on version selection without a sequence guard** — the store had no
  guard before this slice either.
- **Dead code left in place by explicit decision:** `TaskRepository.list_by_workspace` (zero callers)
  and the story port/repository `delete` (zero production callers since the sanctioned deletion).
- **Four `StarletteDeprecationWarning`s** (`HTTP_422_UNPROCESSABLE_ENTITY`) in `test_api/test_tasks.py`;
  passing, not failures.

## 5. Not in this slice's evidence at all

- **The deploy.** `0029` has never been applied to production, because nothing is merged. When the chain
  merges, the deploy window's `alembic upgrade head` applies it; `0029` is additive and reads no data, so
  it needs no data plan and the D-a-3 rule does not bite.
- **Production's ability to extract.** Independent of this slice: production has no LLM configuration and
  `resolve_llm_config` falls back to an Ollama that does not exist there (D-a-6). Recreating the config in
  Configuración is the owner's pending action.
- **The release bump.** `make bump` is never a task in a change.
