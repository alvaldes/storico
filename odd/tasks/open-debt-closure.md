# ODD Feature: open-debt-closure

> **Status**: in progress on `fix/open-debt-closure`
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
| `AGENTS.md` | 7 — stack table (line 220), ADR-004 (289), block diagram (432-433, 442), layer table (461), feature #38 (548), glossary (1031-1032) |
| `docs/architecture.md` | 4 — stack table (23), diagram (66), ADR-004 (134), deploy context (143) |
| `docs/deployment.md` | 2 — service ports (30), batch row (223) |
| `README.md` | 1 — "5 services: API, Ollama, Postgres, Qdrant, Redis" (104) |

The frontend public API reference already stopped advertising the endpoint
(`frontend/src/i18n/__tests__/api-docs-copy.test.ts`), so the remaining drift is backend-side documentation.

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
| T1 | — | — | — | — |
| T2 | — | — | — | — |
| T3 | — | — | — | — |
| T4 | — | — | — | — |
| T5 | — | — | — | — |
| T6 | — | — | — | — |
