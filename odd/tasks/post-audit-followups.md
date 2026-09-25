# ODD Feature: post-audit-followups

> **Status**: **complete** — verified 2026-09-24. Four work units landed on `fix/public-surface-truth`,
> each with its own commit: `d0922af` (the fold, amended to carry a corrected attribution),
> `0374afe` (the proxy slash), `031d826` (the schema row), `800ae1f` (the dates). Gates green:
> frontend `tsc` clean, `464 passed (40 files)`, `astro build` complete; backend `792 passed,
> 21 skipped`, `ruff check` clean, `ruff format --check` 235 files. Nothing pushed; no PR opened.
> `make bump` is the owner's call, and it is a MINOR because `031d826` is a `feat`.
> **Created**: 2026-09-24
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/public-surface-truth` (continues from `466dea6`; the four commits of
> `public-surface-truth` are already there and `main` is untouched)
> **Receipt-driven development**: off in this clone (`gentle-ai review mode status`)
> **TDD**: `strict_tdd: true` in `openspec/config.yaml`. Runners:
> `conda run -n storico python -m pytest` (backend), `pnpm vitest run` + `pnpm exec tsc --noEmit`
> (frontend).

## Problem

The audit of 2026-09-24 left four items open. The owner asked for three of them, then `make bump`.

### P1 — the unfiltered list endpoints cost one round trip per workspace

Measured through the Astro proxy against the running dev servers, three calls each, same session:

| Endpoint | Time |
| --- | --- |
| `GET /api/v1/stories/?workspace_id=…` | 5.3s |
| `GET /api/v1/stories/` (no filter) | **31.7s** |
| `GET /api/v1/tasks/?workspace_id=…` | 5.9s |
| `GET /api/v1/tasks/` (no filter) | **25.6s** |
| `GET /api/v1/extractions/` (no filter) | **30.4s** |

The unfiltered branch of all three routes loops over the caller's memberships and awaits one
repository call per workspace:

```python
memberships = await member_repo.list_by_user(current_user.id)
workspace_ids = [m.workspace_id for m in memberships]
for ws_id in workspace_ids:
    all_stories.extend(await repo.list_by_workspace(ws_id))
```

This user is a member of **12 workspaces**, so one request issued 1 (user) + 1 (memberships) + 12
(list) statements against a database in `us-east-1` (`aws-0-us-east-1.pooler.supabase.com`).

**Correction, made while implementing this.** The first statement of the cause said "~800ms per
network round trip" and credited 12 round trips. Measuring the `307` inside the proxy (P2) showed
that a redirect hop costs **~0 in wall clock** — it reuses the open connection — so distance is not
where the seconds are. What costs ~2s is **the statement itself at the pooler**; a bare `SELECT 1`
already measures 800ms in `/api/v1/health`, and the arithmetic is unambiguous: removing 11 of 14
statements removed ~26s, while a redirect hop costs under the noise floor. The correction is in this
file, in the amended commit message, and in the comments of every touched file rather than only
here.

The repository already has the fitting precedent: `list_by_workspace_with_counts` was added to fold
`list_by_workspace` + `count_stories` per project into one query, and its docstring says so.

### P2 — every proxied list call pays a wasted round trip to a `307`

`docs/testing.md` records the symptom ("Cada llamada de lista cuesta un `307`") and blames the
caller for omitting the trailing slash. **The caller does send it** — measured, the browser requests
`4321/api/v1/stories/?workspace_id=…`. The slash is lost in the proxy: Astro's `[...path]` rest
parameter hands over `stories`, not `stories/`, which was verified with a throwaway probe route
(`params.path` = `"stories"` for both `/api/probe/stories/` and `/api/probe/stories`, while
`url.pathname` kept the slash). `sanitizePath` only removes `..` and `.`, so it preserves whatever it
is given — and it is given a path that already lost the slash.

`/api/v1/stories` is not a route; the backend answers `307` and Node's `fetch` follows it. The
redirect is invisible to the proxy (it sees the final 200) and costs an extra request on every list
call.

**Measured effect, stated honestly.** The extra hop cost **~0 in wall clock** here: three samples of
the slashed and the bare path through the proxy gave means of 4210ms and 4206ms. The fix removes a
wasted request, not a measurable delay in this environment; it would matter where the round trip is
real, and it removes the dependence on every caller remembering the slash.

### P3 — `/status` does not show the schema probe

`/api/v1/health/services` reports five probes (`database`, `schema`, `ollama`, `qdrant`,
`embeddings`); the page renders three of them. `schema` is the newest and the one that would have
caught the 2026-09-20 incident, where the code ran against a schema four revisions behind and 56
extractions failed with a missing column.

One wrinkle the row must respect: the schema probe publishes `status: "unknown"` — its own docstring
says "``unknown`` already is the failure" — while `/status` only models `ok`, `error` and
"unavailable". Collapsing `unknown` into "Unavailable" would erase a state the backend measured.

### P4 — two `last_updated` dates are stale, and two are not

The owner reported all four public page sections as stale. Measured per section against the last
commit that changed that section's catalog lines (`git log -L`):

| Section | `last_updated` says | en.json last change | es.json last change | Verdict |
| --- | --- | --- | --- | --- |
| `about` | July 11, 2026 | 2026-07-10 | 2026-07-10 | accurate — leave it |
| `privacy` | July 11, 2026 | **2026-09-19** | **2026-09-19** | **stale** |
| `terms` | July 11, 2026 | 2026-07-11 | **2026-07-15** | **stale in `es` only** |
| `docs` | July 11, 2026 | **2026-09-22** | **2026-09-22** | **stale** |

Setting all four to September would replace one imprecision with four false claims. Only the three
that actually moved get a new date, and each gets the date its content actually changed.

## Decisions

1. **One query per request, not one per workspace.** A `list_by_workspaces(ids)` port method,
   implemented with `WHERE … IN (…)`, replaces the loop in all three routes. `list_by_workspace`
   stays: the filtered branch and other callers still use it.
2. **The proxy must not rewrite the caller's path.** It takes the incoming pathname (which keeps the
   trailing slash) instead of Astro's rest param (which does not), and the URL builder moves to
   `frontend/src/lib/proxy-url.ts` so it can be tested without a live server. The route keeps only
   the request handling.
3. **The remaining floor is an environment fact, not a defect.** After P1 each request is 3 queries
   (~1 user, 1 memberships, 1 list); the rest is the ~800ms round trip to `us-east-1` plus
   `pool_pre_ping`. `pool_pre_ping=True` stays: it is a deliberate trade against "connection was
   closed in the middle of operation" on Supabase/Neon idle drops, documented at the engine.
4. **`unknown` is a state, not a failure.** `ServiceStatus` gains `'unknown'`, the badge gains a
   fourth state, and a locale key names it. The schema row is the only probe that publishes it today,
   and it is exactly the signal the row exists for.
5. **Pagination stays in Python.** `total = len(rows)` loads every row across the workspaces and
   slices the page in memory. That is a separate defect with a wider blast radius (port signatures),
   and it is not the 25-32s: the statements are.
6. **The proxy forwards the caller's path; it does not normalise it.** A caller that omits the
   trailing slash still gets no slash forwarded. The answer to a caller omitting it is to send it,
   which the frontend already does — not to rewrite the request silently. The bare case is asserted
   so that a future "helpful" normalisation is a deliberate act.
7. **Only the dates whose content actually moved change.** Measured per section and per locale with
   `git log -L`; `terms` in English stays at July 11 because its content did, and `about` renders no
   date at all, so there was nothing there to be stale.

## Scope boundary (not in this batch)

- Pushing `LIMIT`/`OFFSET` and a `COUNT` into SQL (decision 5).
- `pool_pre_ping` / `pool_recycle` tuning, and a local Postgres for development so dev latency stops
  being internet latency.
- Implementing `POST /batch`.

## Work units

| WU | Change | Surfaces |
| --- | --- | --- |
| WU1 | One query for the unfiltered list, in all three routes | 3 ports, 3 repositories, 3 routes, `backend/tests/test_repositories/`, `backend/tests/test_api/` |
| WU2 | The proxy stops dropping the trailing slash | `frontend/src/lib/proxy-url.ts` (new) + test, `frontend/src/pages/api/v1/[...path].ts` |
| WU3 | `/status` shows the schema probe, and `unknown` renders as itself | `frontend/src/lib/health.ts` + test, `frontend/src/pages/[locale]/status.astro`, both catalogs |
| WU4 | The three stale dates, per locale | `frontend/src/i18n/{en,es}.json` |

## Acceptance

| Claim | Check |
| --- | --- |
| The unfiltered endpoints stop scaling with the workspace count | Repo test asserting one statement per request with several workspaces; before/after timing through the proxy |
| The three unfiltered endpoints still return the same items | Existing route tests, plus an unfiltered case across two workspaces |
| `list_by_workspaces` returns the same set as the loop it replaces | Repository test over 2 workspaces with stories in each |
| The proxy preserves the trailing slash and still blocks traversal | `frontend/src/lib/__tests__/proxy-url.test.ts` |
| No list call redirects any more | The built backend URL keeps the slash for every path the frontend sends |
| `/status` renders the schema row in both locales | Browser: 5 rows, `Schema` present |
| `unknown` is distinguishable from `error` and "Unavailable" | `frontend/src/lib/__tests__/health.test.ts` + browser |
| No date claims more than its content | `git log -L` per section re-run after the edit; only the three moved dates changed |
| i18n parity | existing parity test |
| No regression | `pnpm exec tsc --noEmit`, `pnpm vitest run`, `pnpm build`, `python -m pytest`, `python -m ruff check src tests`, `python -m ruff format --check src tests` |

## Evidence

### WU1 — the fold (commit `d0922af`)

| Check | Result |
| --- | --- |
| Tests first | `test_unfiltered_list_queries.py` (3 endpoints × statement count + rows from every workspace + the no-membership path) and `test_list_by_workspaces.py` (4 per-repository contract tests) — all 7 seen failing before the change, the route ones with `read user_stories 3 times; the workspaces must fold into a single statement` |
| Statement count, not mocks | `ReadsOf` attaches `before_cursor_execute` to the real engine; a mock the route calls once would keep passing if the query were split in two |
| Live, before → after | `stories/` 31670ms → 5450ms; `tasks/` 25633ms → 4664ms; `extractions/` 30394ms → 5091ms |
| Live, final run (2 samples, min-max) | `stories/` 5261-5674ms (total 32); `tasks/` 5015-5021ms (total 230); `extractions/` 5890-6391ms (total 38) |
| Same as the filtered twins | `stories/?workspace_id=…` 4044-4097ms against 5261-5674ms unfiltered: the floor is per-statement, not per-workspace |
| Rows preserved | `total` matches the row counts the pre-fix calls reported |
| Suite | `pytest` 792 passed (781 → +11) |
| Two stale docstrings corrected | `test_tasks.py` and `test_extractions.py` described the fan-out as intended behaviour |

### WU2 — the proxy slash (commit `0374afe`)

| Check | Result |
| --- | --- |
| Root cause proven, not guessed | Throwaway probe route: `params.path` = `"stories"` for both `/api/probe/stories/` and `/api/probe/stories`, while `url.pathname` keeps the slash. The caller does send it |
| New module | `frontend/src/lib/proxy-url.ts` — takes the **request URL**, so the whole transformation is testable without a live server |
| Tests | 14, including the exact URL the browser was measured sending, and `sanitizePath` filtered against a traversal the URL parser leaves alone |
| Traversal | `..` is resolved by the URL parser before this module sees it; the result is composed **under** `/api/v1` rather than used as an absolute path, so no request can address a backend path outside the namespace |
| Proxy still serves | `stories/?workspace_id`, `stories/{id}`, `users/me`, `settings/llm` and `health` all **200** through it after the change |
| Re-measured effect | means 4210ms (slashed) vs 4206ms (bare) — **no wall-clock delta measured**, reported as such |

### WU3 — the schema row (commit `031d826`)

| Check | Result |
| --- | --- |
| Test first | `serviceStatus` returning `null` for `unknown` — seen failing, then passing |
| Four states | `ok`, `error`, `unknown`, `unavailable`; `unknown` is amber, matching the degraded banner |
| `/en/status` renders | 5 rows, "Database schema — Alembic revision applied to the database — Operational" |
| `/es/status` renders | 5 rows, "Esquema de la base de datos — Revisión de Alembic aplicada a la base de datos — Operativo" |
| i18n | `schema`, `schema_desc`, `unknown` in both catalogs, parity test green |
| Guion | step 9 updated from four rows to five |

### WU4 — the dates (commit `800ae1f`)

| Check | Result |
| --- | --- |
| Per section, per locale | `git log -L` over each catalog range: privacy 2026-09-19 (both), docs 2026-09-22 (both), terms es 2026-07-15 |
| Not touched, with reason | `terms` in English (content last changed 2026-07-11, so its July 11 is accurate) |
| Nothing to touch | `about.astro` renders no `last_updated` line at all |
| Rendered | `/en/privacy` SEPTEMBER 19, `/es/privacy` 19 DE SEPTIEMBRE, `/en/docs` SEPTEMBER 22, `/es/docs` 22 DE SEPTIEMBRE, `/en/terms` JULY 11, `/es/terms` 15 DE JULIO |
| Escape style preserved | es.json mixes literal accents and `\u` escapes; the two legacy lines keep theirs |

### WU5 — gates

| Gate | Result |
| --- | --- |
| `pnpm exec tsc --noEmit` | clean |
| `pnpm vitest run` | `464 passed (40 files)` |
| `pnpm build` | `[build] Complete!` — server built in 8.43s |
| `python -m pytest` | `792 passed, 21 skipped, 1 warning in 36.79s` (the warning is the pre-existing `Connection._cancel` one) |
| `ruff check` / `ruff format --check` | "All checks passed!" / 235 files formatted |
| SSR truncation sweep, 16 public routes | `</html>` present on all 16 |
| Browser sweep, 15 routes incl. every authenticated page | no SSR error frame, no exception, no error log, no 4xx/5xx |

## Acceptance

| Claim | Result |
| --- | --- |
| The unfiltered endpoints stop scaling with the workspace count | ✅ one statement asserted per endpoint with the caller in three workspaces; live 25-32s → 5-6s |
| The three unfiltered endpoints still return the same items | ✅ `total` 32 / 230 / 38 matches the pre-fix counts; a cross-workspace test per endpoint |
| `list_by_workspaces` returns the same set as the loop it replaces | ✅ `test_list_by_workspaces.py`, including that a workspace outside the list contributes nothing |
| The proxy preserves the trailing slash and still blocks traversal | ✅ 14 tests |
| No list call redirects any more | ✅ the built URL keeps the slash for the URL the browser sends; the redirect hop's cost was ~0, stated |
| `/status` renders the schema row in both locales | ✅ 5 rows in both |
| `unknown` is distinguishable from `error` and "Unavailable" | ✅ unit test + four-state badge |
| No date claims more than its content | ✅ `git log -L` re-run per section; only the three moved dates changed |
| i18n parity | ✅ parity test green |
| No regression | ✅ all six gates above |

## Follow-ups left open

- **Pagination still loads every row.** `total = len(rows)` and the slice happen in Python; the fix
  removed the statement count, not the full read. Pushing `LIMIT`/`OFFSET` and a `COUNT` into SQL
  changes the port signatures.
- **~5s is still the floor for a three-statement request** because a statement at that pooler costs
  ~2s. The levers are a local Postgres for development, and revisiting `pool_pre_ping=True`, which is
  a deliberate trade against Supabase/Neon idle drops and is documented at the engine.
- **`POST /batch` is still unimplemented** (`docs/deployment.md` records the gap).
- **`make bump` will produce a MINOR**, because the schema row is a `feat`. If the intent was a
  PATCH, that commit's type is the thing to change, not the bump.
