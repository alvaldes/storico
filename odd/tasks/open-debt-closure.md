# ODD Feature: open-debt-closure

> **Status**: closed on `fix/open-debt-closure` — six work-unit commits, `10ebd0b` through `6ed2667`. Not pushed:
> the operator asked for commits, not delivery, and the stacked branches are cut when they ask for them.
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)
> **Source**: `~/Documents/second-brain/00 - Inbox/Storico — deuda de ingeniería abierta por decisión.md`, points 1, 3 and 4

## Problem

Three of the four items in that note are work decided *against* in a previous session, not oversights. The note
exists so they are not rediscovered. This batch closes them.

Point 2 (the ~2s floor per statement on the Supabase pooler) is **out of scope by operator decision**: Supabase is
the development database, and the operator worries about that latency only if Neon, the production database, shows
the same behaviour. Nothing here touches it, and nothing here assumes its latency.

## Scope, measured before writing

Measured on `1e4da9d` with `git grep`, because the note names the defect, not the blast radius.

### Point 1 — pagination slices in Python

Four list endpoints fetch every row matching the filter and slice the page in memory:

| Route | Fetch | Slice |
|---|---|---|
| `api/routes/projects.py:150` | `list_by_workspace_with_counts(workspace.id)` | `all_projects[start : start + params.size]` |
| `api/routes/stories.py:133,145,153` | `list_by_workspace` / `list_by_project` / `list_by_workspaces` | `all_stories[start : start + params.size]` |
| `api/routes/tasks.py:163,173,181` | `list_by_workspace` / `list_by_story` / `list_by_workspaces` | `all_tasks[start : start + params.size]` |
| `api/routes/extractions.py:106,116,124` | `list_by_workspace` / `list_by_story` / `list_by_workspaces` | `all_extractions[start : start + params.size]` |

`total` in all four is `len()` of the full fetch.

Two facts found while measuring, both of which shape the change:

1. **No repository applies `ORDER BY`.** `SQLAlchemyProjectRepository`, `SQLAlchemyUserStoryRepository`,
   `SQLAlchemyTaskRepository` and `SQLAlchemyExtractionRepository` all build a bare `select(...).where(...)`. The
   only ordering in the whole path is a Python `sort` in the *unfiltered* branch of three routes. So today's page is
   already non-deterministic — the workspace and project branches never had an order — and `LIMIT`/`OFFSET` on an
   unordered result set is undefined behaviour, where a row can repeat on page 2 or vanish between pages. **An
   `ORDER BY` is a prerequisite for the fix, not a nicety.**
2. **`tests/test_api/test_unfiltered_list_queries.py` pins exactly one statement** reading the listed table, on the
   real engine, for the unfiltered branch of `/stories/`, `/tasks/` and `/extractions/`. That test encodes the
   ~2s-per-statement measurement, so a separate `SELECT COUNT(*)` would break it. The page's total therefore has to
   ride on the same statement as its rows.

### Point 3 — `POST /batch` does not exist

No router serves it. What exists is per-story asynchronous extraction: `asyncio.create_task(...)` in
`api/routes/extraction.py:237`, implemented by `infrastructure/tasks/extraction_task.py`, which states in its own
docstring that it *replaces* the Celery task.

Measuring the note's own row — `docs/deployment.md:223`, *"Batch processing (Redis/Celery)"* — showed it is not an
isolated case. Neither Redis nor Celery exists anywhere in the repository: `docker-compose.yml` has no Redis
service, and `backend/src`, `backend/.env.example` and `pyproject.toml` name them only to say they are absent. The
live documents still describe them as running infrastructure:

| Document | Mentions |
|---|---|
| `AGENTS.md` | 10 lines — the header's own resync note (4, which was already a *correction* rather than a claim), stack table (220), ADR-004 (289), ADR-005's service list (295), block diagram (432-433, 442-446), layer table (461), feature #38 (548), references (1031-1032) |
| `docs/architecture.md` | 4 — stack table (23), diagram (66), ADR-004 (134), deploy context (143) |
| `docs/deployment.md` | 2 — service ports (30), batch row (223) |
| `README.md` | 2 — "5 services: API, Ollama, Postgres, Qdrant, Redis" (104) and "Docker Compose orchestration with 5 services" (59) |

The frontend public API reference already stopped advertising the endpoint
(`frontend/src/i18n/__tests__/api-docs-copy.test.ts`), so the remaining drift is backend-side documentation.

Two further false claims were found sitting *inside* the sentences this cluster owns, and are corrected with them
rather than left behind by an edit that touched the line:

- `AGENTS.md:175` (executive description) advertised "semantic caching". The only cache in the tree is
  `infrastructure/cache/user_cache.py`, a 30-second in-process per-user auth cache. `AGENTS.md`'s own ADR-004
  already states there is no semantic cache, so the document contradicted itself 110 lines apart.
- `README.md` advertised a compose service count that compose does not back, in **two** places (59, 104). The first
  pass fixed only line 104 and the commit message then claimed the claim was gone; the independent verifier refuted
  that by finding line 59, which a follow-up commit fixed. The refutation is kept here rather than smoothed over: it
  is the clean demonstration that a prose sweep must be checked by something other than the sweep.

Out of scope, reported and not fixed: `docs/architecture.md` ADR-005 still reads "Status: 🔴 Pendiente
(producción)" and "Producción sin definir", while production has been running since before this note. That is a
different defect class from a component that does not exist, and the operator's scope was this cluster.

### Point 4 — `/status` renders four of five probes

`api/routes/health.py:248` publishes five probes in `services`: `database`, `schema`, `ollama`, `qdrant`,
`embeddings`. `frontend/src/pages/[locale]/status.astro` declares five rows, but one of them is a synthetic `api`
row that reads no probe. Missing: `embeddings`.

The consequence is not cosmetic: the banner reads `health.status`, which the backend degrades when *any* of the five
probes is not `ok`. An embeddings failure therefore turns the banner "degraded" while every visible row reads
Operational — a diagnosis with no visible cause.

## Decisions

| # | Decision | Choice | Consequence |
|---|----------|--------|-------------|
| D1 | What "attack point 3" means | **Operator-selected: close it as a documented non-goal.** No batch endpoint is implemented. | Cierra la fila sin agregar feature; el pendiente queda decidido, no olvidado. |
| D2 | Blast radius of the Celery/Redis claim | **Operator-selected: the whole live cluster.** All four live documents are corrected; historical `odd/tasks/*.md` records are left as written, because they are the evidence of the correction. | Candidate grows from 1 file to 4; no behaviour change. |
| D3 | Where the page's total comes from | **Extrapolated from the measured single-statement pin.** `count(*) OVER ()` on the same statement that returns the rows. PostgreSQL evaluates a window function over the whole filtered set before `LIMIT`/`OFFSET`, so it is exactly the old `len()`. | One statement on the normal path. A page past the end returns no row for the count to ride on, so that one case issues a real `COUNT` — and with `offset == 0` an empty result already means zero matching rows, so it does not even ask. |
| D4 | Ordering | **Required by D3.** Every paginated list orders by `created_at DESC, id DESC`, in SQL, for every filter shape. | Behaviour change, deliberate and documented: the workspace and project branches had no order at all; the unfiltered branch already sorted `created_at DESC` in Python, and this makes the other two match it rather than inventing a third rule. `id DESC` is the tiebreaker so two rows written in the same instant cannot swap between pages. |
| D5 | Port shape | **Operator-selected: delete the methods that lose their caller.** One `list_page` per repository replaces the paginated branch of the three `list_by_*` methods. | `list_by_workspace` survives where `export.py` still calls it; the rest go with their dedicated tests. The note's own "cambia las firmas de los puertos" is taken literally. |
| D6 | Delivery | **Operator-selected: Stacked PRs to main.** | Six work units, each landable on its own; the four endpoint slices in point 1 share one prerequisite (`list_page` + helper) and that dependency edge is recorded below. |

## What lands

**Point 1**
- `backend/src/storico/infrastructure/database/pagination.py` (new) — `with_total` and `fetch_page`.
- `ProjectRepository` / `UserStoryRepository` / `TaskRepository` / `ExtractionRepository` ports — add `list_page`,
  drop the paginated branch's dead siblings.
- The four SQLAlchemy repositories — implement `list_page`.
- The four routes — call `list_page` once; delete the `len()` total and the Python slice.
- Tests: helper, repositories, route pagination and ordering, and the obsolete `list_by_*` tests that lose their
  subject.

**Point 3**
- `docs/deployment.md` — the batch row and the Redis port row.
- `AGENTS.md` — stack table, ADR-004, block diagram, layer table, feature #38, glossary, references.
- `docs/architecture.md` — stack table, diagram, ADR-004, deploy context.
- `README.md` — the compose description.

**Point 4**
- `frontend/src/pages/[locale]/status.astro` — the `embeddings` row.
- `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json` — `pages.status.embeddings` and `embeddings_desc`.
- `frontend/src/lib/__tests__/status-probes-mirror.test.ts` (new) — the contract that would have caught it.

## Checks

- **TDD mode**: `on` (strict).
- **Source**: `openspec/config.yaml` → `strict_tdd: true`.
- **Runners**: backend `cd backend && conda run -n storico python -m pytest`; frontend `cd frontend && pnpm test`.

Every implementation task is delegated with this mode, source and runner, and requires observed RED before the
implementation. Point 3 is prose only and has no test to write first; it records that as its TDD exception instead
of inventing a checkbox.

## Tasks

| # | Task | Route | Trigger evidence | Files |
|---|------|-------|------------------|-------|
| T1 | Point 4: `/status` reports the embeddings probe | delegated writer | multi-file write (2+ non-trivial: page + i18n + new test) | `frontend/src/pages/[locale]/status.astro`, `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`, `frontend/src/lib/__tests__/status-probes-mirror.test.ts` |
| T2 | Point 3: close batch as a non-goal and purge the Celery/Redis cluster | inline | prose only; the parent already holds the exact text and the AGENTS.md governance rules, so a worker would re-derive what the parent has | 4 documents, listed above |
| T3 | Point 1a: paging helper + `list_page` for projects | delegated writer | multi-file write (helper + port + repo + route + tests) | `infrastructure/database/pagination.py`, `domain/ports/project_repository.py`, `infrastructure/database/repositories/project_repository.py`, `api/routes/projects.py`, `tests/test_repositories/test_project_repo.py`, `tests/test_repositories/test_pagination.py` |
| T4 | Point 1b: `list_page` for user stories | delegated writer | multi-file write | `domain/ports/user_story_repository.py`, `infrastructure/database/repositories/user_story_repository.py`, `api/routes/stories.py`, `tests/test_repositories/test_user_story_repo.py`, `tests/test_repositories/test_list_by_workspaces.py`, `tests/test_api/test_stories.py` |
| T5 | Point 1c: `list_page` for tasks | delegated writer | multi-file write | the task twin of T4 |
| T6 | Point 1d: `list_page` for extractions | delegated writer | multi-file write | the extraction twin of T4 |

T3 sets the pattern; T4, T5 and T6 replicate it per entity and each depends on T3.

## Delivery strategy and slice boundaries

- **Forecast** (authored changed lines, additions + deletions): ~+930 / −450 ≈ **1380**, over the ~400 budget, so
  `chained-pr` is active.
- **Delivery strategy**: `single-pr` is not used. **Chain strategy: `stacked-to-main`** (D6). Slices:

| Slice | Commits | Depends on | Landable alone |
|---|---|---|---|
| S1 | T1 | — | yes |
| S2 | T2 | — | yes |
| S3 | T3 | — | yes |
| S4 | T4 | S3 | after S3 |
| S5 | T5 | S3 | after S3 |
| S6 | T6 | S3 | after S3 |

Slice boundaries are recorded here by commit range. Per the operator's instruction, no push and no PR happens
without an explicit order; the stacked branches are cut at that point from these ranges, not before.

## Evidence

Appended as each task closes: commit id, observed RED, observed GREEN, and the verification outcome.

| Task | Commit | RED | GREEN | Verification |
|------|--------|-----|-------|--------------|
| T1 | `f1fea5e` | `expected [ Array(4) ] to include 'embeddings'` — the missing-probe assertion, no syntax error; reproduced independently by the verifier by reverting only the row and the two key pairs, restore confirmed by SHA-256 | focused `3 passed`; full suite `41 files / 467 tests passed`; `tsc --noEmit` exit 0; `astro build` complete | `gentle_review` `assess` returned `unassessable` (untracked files require an explicit declaration, so no tier could be produced), and an unassessable candidate is treated as high: the writer self-verified **and** an independent `gentle-ai-verify` ran. That verifier confirmed all five points, including that the probe regex reaches the `services` object of `health_services()` and that no other `"services":` occurrence exists in the file. |
| T2 | `e9d88bb` + the follow-up `README.md` fix | **TDD exception, declared**: prose only, with no mechanical invariant to write first. A phrase blocklist ("no live document may name Redis/Celery") is the only test this admits, and its false negatives are exactly the rewordings a real drift would use, so it was rejected as a guard rather than written to look thorough. The applicable check is that no artifact depends on the changed text: `grep` for every reference to these four documents from `backend/` and `frontend/` finds only two comments, and the frontend suite reads none of them. | `cd frontend && pnpm test` → `41 files / 467 tests passed`, unchanged, confirming nothing depended on the prose | inline, by the parent (route declared in the Tasks table). The native `assess` returned `schema-incompatible`, so the plan required an independent verifier anyway, and it earned its keep: it confirmed 7 of the 8 checks and **refuted one** — `README.md:59` still read "5 services", so the document contradicted its own line 104. Fixed in the follow-up commit. It also proved the diagram edits changed no column and that the residual `AGENTS.md` diagram drift is pre-existing, by comparing against `git show e9d88bb^:AGENTS.md`. |
| T3 | `c3f789a` | helper: `assert 0 == 5` — a past-the-end page reported a total of 0 instead of the real count (the fallback is genuinely load-bearing). Repository: three behavioural failures against `list_page` without `ORDER BY` — story counts landing on the wrong page, `created_at` order reversed, and the `id DESC` tiebreaker absent. Route: insertion order instead of `created_at DESC`. | focused `34 passed`; full suite `804 passed, 21 skipped`; `ruff check` and `ruff format --check` clean. The order test was then hardened and the suite re-run at `805 passed, 21 skipped`. | `gentle_review` `assess` → `unassessable` again (untracked files need an explicit declaration), so the plan required an independent verifier. It confirmed 8/8, including the four load-bearing claims, and executed them rather than reading them: it built the real query against SQLite with 5 projects and asserted the total was 5 and not 2 under `limit=2`; it captured engine statements to prove the fallback fires only past the end and not at `offset == 0`; and it confirmed the emitted SQL carries the ordering. It also **flagged** the tiebreaker test as a result-pin whose RED depends on SQLite returning ascending ids — true today, not durable — so the parent added `test_list_page_pins_the_order_rule_in_sql`, which asserts the ordering on the statement the database received, and proved its RED by removing `.id.desc()` (both tests fail) and restoring it. It further noted the stale `list_by_workspace_with_counts` reference in `domain/entities/project.py`'s docstring, fixed in the same commit. |
| T4 | `7d380c1` | repository: `AttributeError: ... has no attribute 'list_page'` on the new tests; route: `['feature 1', 'feature 2', 'feature 3'] == ['feature 3', 'feature 2', 'feature 1']` — the workspace branch returning insertion order, because the old code never ordered it. The total-only route tests passed against the pre-change code by design, since the old Python slice already reported `len()`. | focused `42 passed`; full suite `818 passed, 21 skipped`; `ruff` clean | `assess` → `unassessable` (`schema-incompatible`), so the plan again required an independent verifier. It confirmed 8/8, including the load-bearing check: for all three scopes it compared the emitted page SQL against the emitted `count_stmt` SQL and against its own hand-written counts, and found scopes and joins agreeing in every branch (totals 3/3/5 with the decoy workspace excluded), so the "wrong total only on a filtered page past the end" failure mode does not exist here. It **flagged** two things: passing two scope arguments silently resolved to one (latent, because the route always passes exactly one), and stale `list_by_project` references in two spec documents. The silent precedence was fixed with a guard whose RED was proven by removing it; the spec documents were classified as a dated historical change record (`Change: api-endpoints`, 2026-07-06) and left as written, on the same rule D2 applies to `odd/tasks/*.md`. |
| T5 | `9f4d3b6` | same two groups: missing `list_page`, and the workspace branch returning insertion order instead of `created_at DESC`. The writer also hit a self-inflicted `NameError` mid-task by not recomputing `offset` when deleting the Python slice — the new route tests caught it, which is the useful part of the record. | focused `49 passed`; full suite `835 passed, 21 skipped`; `ruff` clean | `assess` → `unassessable`. The independent verifier confirmed every point and ran the highest-risk check explicitly: per branch it captured both statements and compared them, reporting identical joins and `WHERE` for `workspace_id` and `workspace_ids`, and no join on either statement for `user_story_id`. It also verified the reported `NameError` fix (`offset` assigned exactly once, read only in the three `list_page` calls) and that the authorization region differs from `HEAD` only by a rewritten comment. |
| T6 | `6ed2667` | repository: missing `list_page`; route: insertion order instead of `created_at DESC`. `workspace_ids=[]` returning `([], 0)` with zero statements was already the pre-change behaviour, so it is a regression guard rather than a RED. | focused `65 passed`; full suite `849 passed, 21 skipped`; `ruff` clean | `assess` → `unassessable`. The verifier confirmed every point, including that the extraction `count_stmt` matches its page query in scope **and** joins on all three branches, that the three removed methods have no live caller while the identically named methods on the story and task repositories survive for `export.py` and `task_service.py`, and that the large `test_extraction.py` was edited in a single five-line hunk. It **flagged** one documentation overclaim, which is the same defect class as this batch: the rewritten `test_list_by_workspaces.py` docstring said its empty-list test would catch a regression that reintroduces `IN ()`, and the verifier proved an empty `IN ()` executes cleanly and returns zero rows, so only the per-repository zero-statement tests can tell "no statement" from "a statement that matched nothing". Corrected in the same commit. |

## Forecast against actual

The forecast above was **wrong, and low**: ~+930 / −450 ≈ 1380 authored lines. The measured result, from the
work-unit commits themselves (`git show --shortstat` per commit, the ODD documents excluded because they are the
record rather than the work):

| Slice | Commit | Files | Additions + deletions |
|---|---|---|---|
| S1 — point 4 | `f1fea5e` | 4 | 109 |
| S2 — point 3 | `e9d88bb` + `35244a1` | 6 | 69 |
| S3 — helper + projects | `c3f789a` | 9 | 582 |
| S4 — stories | `7d380c1` | 6 | 582 |
| S5 — tasks | `9f4d3b6` | 6 | 623 |
| S6 — extractions | `6ed2667` | 7 | 711 |
| **Total** | | **35** | **2676** |

Why it was low: the estimate treated each entity as a small diff, but every entity replicates the *full* coverage
shape — three scopes, the mid-page total, the past-the-end fallback, the zero-statement empty case, both scope-guard
cases, the decoy-workspace exclusion and the SQL ordering pin. Tests are roughly two-thirds of S3-S6.

Consequence for the delivery strategy: **S3, S4, S5 and S6 each exceed the ~400-line budget on their own**, so the
chained split does not fit the budget as sliced. One honest further slicing pass is available and is recorded here
rather than applied silently: cut each entity at the layer boundary — port + repository + repository tests, then
route + route tests — which yields eight slices of roughly 300 lines each and keeps every test with the unit it
verifies. That split cuts *within* the four entity commits, so it needs those commits re-cut when the branches are
created; it cannot be expressed as a commit range, which is why it is left as a decision rather than assumed. Per
`chained-pr`, if that split is not wanted, the recommendation is `size:exception` for S3-S6 with this table as the
rationale.

## Closure

Three debts from the operator's note are closed. Point 2 stays out of scope by decision: Supabase is the development
database, and the operator worries about that latency only if Neon, the production database, shows it.

Two findings came out of this batch that were not in the note, plus one pre-existing item. They are recorded rather
than absorbed:

- **Fixed, because an edit already touched the same sentence**: the executive description's "semantic caching"
  (`AGENTS.md:175`) and the second compose service count in `README.md`.
- **Reported, not fixed**: `docs/architecture.md` ADR-005 still reads "Status: 🔴 Pendiente (producción)" and
  "Producción sin definir", while production has been running since before the note was written. That is drift about
  deployment state — a different class from a component that does not exist — and it was outside the scope the
  operator set. It is the one live-document contradiction this batch knowingly left standing.
- **Pre-existing dead port methods**: `ProjectRepository.count_stories` and `count_by_workspace` had no caller before
  this batch either. D5 scopes the removal to methods this change strands, so they were left alone deliberately, and
  they are noted here so the next reader does not read them as this batch's miss.

A process observation worth keeping: the native risk assessment (`gentle_review` `assess`) never produced a tier in
this environment. It returned `unassessable` for every candidate — `non-zero` while untracked files were present, and
`schema-incompatible` afterwards — so the controller's plan was the high-risk one every time: writer
self-verification **plus** a separate independent verifier. Five independent verification runs were spent on this
feature as a result. They found three things the writers' own green runs did not: the second `"5 services"` in
`README.md`, the silent two-scope precedence, and the `IN ()` docstring overclaim. That is the argument for keeping
them, and also the argument for fixing `assess` before the next large batch, since a tier that always resolves to
"high" carries no risk information at all.
