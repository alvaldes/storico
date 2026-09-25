# ODD Feature: public-surface-truth

> **Status**: **complete** — verified 2026-09-24. Four work units landed on `fix/public-surface-truth`,
> each with its own commit (`9b97e4f`, `af05333`, `d53634b`, `b742aa0`), with tests for all three
> defects and the full gates green: frontend `tsc` clean, `448 passed (39 files)`, `astro build`
> complete; backend `781 passed, 21 skipped`, `ruff check` clean, `ruff format --check` 233 files.
> Nothing pushed; no PR opened.
> **Created**: 2026-09-24
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/public-surface-truth` (branched from a clean `main` @ `c6e8c72`)
> **Receipt-driven development**: **off** in this clone (`gentle-ai review mode status`: global on,
> clone-local off). No native review lineage was started.
> **TDD**: `strict_tdd: true` in `openspec/config.yaml`. Runners:
> `conda run -n storico python -m pytest` (backend), `pnpm vitest run` + `pnpm exec tsc --noEmit`
> (frontend).

## Problem

Three public, unauthenticated surfaces of Storico publish something that is not true. They were
found by auditing the running dev servers (frontend `:4321`, backend `:8000`) in a real browser on
2026-09-24; none of them is covered by a test, and none is in the manual browser guion
(`docs/testing.md`).

### P1 — `/status` crashes and renders nothing (both locales)

```
TypeError: Cannot read properties of undefined (reading 'ollama')
  at Object.default (frontend/src/pages/[locale]/status.astro:144:96)
```

`status.astro` fetches `/api/v1/health` but reads `health.services.ollama | .database | .qdrant`.
The regression origin is measured, not guessed:

| Commit | Date | What it did |
| --- | --- | --- |
| `00a649f` | 2026-07-10 | Rewrote `/api/v1/health` with per-service probes, returning `services: {database, ollama, qdrant}`. `status.astro` was written against that shape. |
| `aee59ff` | 2026-09-20 | Moved the per-service probes to `/api/v1/health/services`; `/api/v1/health` became liveness with only `database` + `schema` at the top level. **The consumer was not updated.** |

Broken since 2026-09-20. The declared type lies — `HealthResponse.services` is required and does
not exist on that payload. Because Astro SSRs by streaming, the throw aborts the response after
the layout: the page renders the navbar and no content, with **no error and no message** for the
visitor.

### P2 — `/api` documents endpoints that do not exist

`frontend/src/pages/[locale]/api.astro:47-62`, copy in `frontend/src/i18n/{en,es}.json`:

| The page claims | Reality (`GET /openapi.json`) |
| --- | --- |
| `POST /api/v1/extract` | `POST /api/v1/workspaces/{workspace_id}/extract/` |
| `POST /api/v1/batch` | **no such route** — `404` |
| `GET /api/v1/status/{id}` | `GET /api/v1/workspaces/{workspace_id}/extract/status/{extraction_id}` |

Batch processing is a known, deliberately open gap (`docs/deployment.md:223`, 🔲 Pendiente), so the
page advertises an unimplemented feature as API surface.

### P3 — the OpenAPI document publishes a stale version

`backend/src/storico/api/app.py:130` hardcodes `version="0.1.0"`, so `:8000/docs` shows
"Storico API 0.1.0" while `/api/v1/health` reports `0.5.1`. The same literal was already fixed in
`health.py::_package_version`, whose docstring records that it "had been wrong since the package
reached 0.3.0" — the fix was applied to one of the two readers.

## Decisions

1. **`/status` consumes `/api/v1/health/services`, not `/api/v1/health`.** The page renders
   per-service rows (LLM runner, database, vector store); that is exactly the shape of the
   services route. Liveness answers "is the process alive", which is not what a status page shows.
2. **The page must never crash because a probe disappeared.** The response is parsed by a
   testable module (`frontend/src/lib/health.ts`) that tolerates missing service keys. A status
   page that dies when a dependency is absent is worse than useless: it is precisely the moment it
   is needed.
3. **The non-existent `/batch` row is removed, not replaced by prose.** The page is a reference,
   not a roadmap; a promise of an endpoint that 404s is the defect. Batch stays recorded as a gap
   where it already is (`docs/deployment.md`, `AGENTS.md`).
4. **`_package_version` moves to a shared module.** Two readers of the same fact must not each
   own a copy; `storico/api/version.py` becomes the single one.
5. **The public pages enter the manual guion.** All three defects are invisible to CI
   (`tsc`, `vitest`, `astro build` all pass with them present) and none is in the 8-step guion.
   That is the whole reason P1 survived five days in `main`.

## Scope boundary (not in this batch)

- The ~32s latency of the unfiltered `GET /api/v1/stories|tasks|extractions` and the `307`
  double-trip. Both are already measured and documented as traps in `docs/testing.md`.
- Implementing `POST /batch`.
- Adding a Schema row to `/status` (the schema probe is the newest signal and arguably belongs on
  a public status page, but that is new surface, not a repair).

## Work units

| WU | Change | Surfaces |
| --- | --- | --- |
| WU1 | `/status` reads the services route through a defensive, tested parser | `frontend/src/lib/health.ts` (new), `frontend/src/lib/__tests__/health.test.ts` (new), `frontend/src/pages/[locale]/status.astro` |
| WU2 | `/api` copy tells the truth; a guard forbids the retired paths | `frontend/src/pages/[locale]/api.astro`, `frontend/src/i18n/{en,es}.json`, `frontend/src/i18n/__tests__/api-docs-copy.test.ts` (new) |
| WU3 | One owner for the package version; the OpenAPI document stops lying | `backend/src/storico/api/version.py` (new), `backend/src/storico/api/app.py`, `backend/src/storico/api/routes/health.py`, `backend/tests/test_health.py` |
| WU4 | Public surfaces enter the manual guion | `docs/testing.md` |

## Acceptance

Every claim below was executed against the running dev servers and the real gates, not reasoned about.

| Claim | Result |
| --- | --- |
| P1 — `/en/status` and `/es/status` render the service rows | ✅ both render the banner, the 4 rows and "Last updated" |
| P1 — no `TypeError` in the console or the vite error channel | ✅ neither locale emits an error frame |
| P1 — the page survives a payload without a service key | ✅ `frontend/src/lib/__tests__/health.test.ts` — `serviceStatus` → `null` → "Unavailable" |
| P2 — the page no longer advertises the retired paths | ✅ guard green; page text read in both locales |
| P2 — the advertised paths exist on the backend | ✅ `401`, not `404`, for both |
| P3 — the OpenAPI version matches the installed distribution | ✅ `test_the_openapi_version_matches_the_package`; `/openapi.json` says `0.5.1` |
| i18n parity survives the copy change | ✅ parity test green; both catalogs lost `endpoint_batch_desc` |
| No regression | ✅ the six gates in WU5 |

## Evidence

### WU1 — `/status` (commit `9b97e4f`)

| Check | Result |
| --- | --- |
| New module | `frontend/src/lib/health.ts` — `HEALTH_SERVICES_PATH`, `parseServicesHealth`, `serviceStatus` |
| New tests | `frontend/src/lib/__tests__/health.test.ts` — 12 tests, written first and seen failing (`Failed to resolve import "@/lib/health"`) |
| The regression is pinned | `parseServicesHealth(LIVENESS_HEALTH_200)` → `null`, with both payloads captured verbatim from the running backend |
| `/en/status` renders | Banner "All systems operational", 4 rows all Operational, "Last updated: 9/24/2026, 7:59:03 PM", full footer |
| `/es/status` renders | "Estado del Sistema", "Todos los sistemas operativos", 4 rows Operativo, "Última actualización: 24/9/2026, 19:59:09" |
| No SSR error frame | No `__isEnhancedAstroErrorPayload` error on either locale (the check that caught the original defect) |
| Layout unchanged | Screenshot compared against the pre-fix page: same rows, same badge classes |
| Suite | `pnpm vitest run` → `437 passed (38 files)`; `pnpm exec tsc --noEmit` clean |

### WU2 — `/api` (commit `af05333`)

| Check | Result |
| --- | --- |
| New guard | `frontend/src/i18n/__tests__/api-docs-copy.test.ts` — 11 tests, written first and seen failing on all six cases it was written for |
| The guard is not vacuous | 32 declared paths parsed out of `routes/*.py` = the 30 unique paths in `/openapi.json` + the 2 legacy catch-alls (`include_in_schema=False`); four positive controls and one negative control asserted |
| The guard bites | It failed on the page as shipped (`/api/v1/batch is retired copy`) and again while writing this change, on a frontmatter comment that named the retired path |
| Advertised paths exist | `POST /api/v1/workspaces/{workspace_id}/extract/` → **401**; `GET .../extract/status/{extraction_id}` → **401**; neither is a 404 |
| `/en/api` renders | "LAST UPDATED: SEPTEMBER 24, 2026" + the two workspace-scoped paths with method badges |
| `/es/api` renders | "ÚLTIMA ACTUALIZACIÓN: 24 DE SEPTIEMBRE DE 2026" + the same two paths |
| Catalogs in parity | both locales lost `endpoint_batch_desc`; the existing parity test passes |
| Suite | `pnpm vitest run` → `448 passed (39 files)`; `pnpm exec tsc --noEmit` clean |

### WU3 — OpenAPI version (commit `d53634b`)

| Check | Result |
| --- | --- |
| New tests first | `test_the_openapi_version_matches_the_package`, `test_an_unreadable_package_version_does_not_break_the_app` — both seen failing (`assert '0.1.0' == 'unknown'`) before the fix |
| One owner | `backend/src/storico/api/version.py::package_version()`; `health.py` lost `_package_version` and its `importlib.metadata` import |
| Live before → after | `/openapi.json` `info.version` was `0.1.0`, is now `0.5.1`, equal to `/api/v1/health`'s `version` |
| Suite | `pytest` → `781 passed, 21 skipped` |
| Lint | `ruff check` "All checks passed!"; `ruff format --check` 233 files |
| Corrected claim | `test_health_services.py`'s docstring said "the frontend never called this route"; WU1 made that false, so it now records the history and the new consumer |

### WU4 — documentation (commit `b742aa0`)

| Check | Result |
| --- | --- |
| New guion steps | 9 (`/en/status`, `/es/status`, unauthenticated, with the 4 expected rows named) and 10 (`/en/api`, `/es/api`, with the `curl` that must answer `401`) |
| New traps | an Astro SSR failure truncates the HTML with no error marker (`</html>` absent is the tell) and reaches the browser over Vite's error channel; the pre-existing "the page looks empty" trap is about latency, and these two now say how to tell them apart |
| Step 9 executed | `curl -s localhost:4321/{en,es}/status \| grep -c '</html>'` → `1` for both |
| Step 10 executed | both advertised paths → `401` |
| Why it matters | recorded in the doc: `tsc`, `vitest` and `astro build` all pass with the three defects present |

### WU5 — gates

| Gate | Result |
| --- | --- |
| `pnpm exec tsc --noEmit` | clean (no output) |
| `pnpm vitest run` | `448 passed (39 files)` |
| `pnpm build` | `[build] Complete!` — server built in 8.41s, Vercel function bundled |
| `python -m pytest` | `781 passed, 21 skipped, 1 warning in 35.12s` (the warning is the pre-existing `Connection._cancel` one, also present on `main`) |
| `python -m ruff check src tests` | "All checks passed!" |
| `python -m ruff format --check src tests` | `233 files already formatted` |
| SSR truncation sweep, 16 public routes (`en` + `es`) | `</html>` present on all 16 |
| Browser sweep, 14 routes including every authenticated page | no SSR error frame, no `Runtime.exceptionThrown`, no `Log.entryAdded` error, no 4xx/5xx |
| `:8000/docs` | header reads "Storico API **0.5.1**" |

## Follow-ups left open

None of these is a defect introduced here, and none is in the authorized scope.

- **Latency, not correctness:** the unfiltered `GET /api/v1/stories|tasks|extractions` takes ~32s
  (~40 round-trips at ~800ms each against Neon), and `/api/v1/stories` costs an extra `307` because
  the frontend omits the trailing slash. Both are already recorded as measured traps in
  `docs/testing.md`.
- **`POST /batch` is still unimplemented.** Removing the row from the public reference makes the page
  honest; it does not build the feature. `docs/deployment.md` keeps it as a pending gap.
- **`/status` has no Schema row.** The newest signal in the backend is `schema` (a code/Alembic-head
  mismatch cost 56 failed extractions on 2026-09-20), and a public status page is arguably where it
  belongs. That is new surface, so it was left out of a repair.
- **The other `last_updated` dates in both catalogs** (`docs`, `about`, `privacy`, `terms`) still read
  July 11, 2026. They were out of scope; only the API page's date changed with its content.
