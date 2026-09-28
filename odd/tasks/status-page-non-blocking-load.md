# ODD Feature: status-page-non-blocking-load

> **Status**: landed on `main` @ `d4498c8` (backend unit) + `606d37a` (frontend unit + this doc).
> No native review was run: the owner directed the two commits to land in place on `main`.
> **Engram**: plan `#1051` (`odd/status-page-non-blocking-load/tasks`), outcome `#1053`
> (`odd/status-page-non-blocking-load/outcome`).
> **Created**: 2026-09-28
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `main` (the owner directed the commits to land here, in place)

## Problem

`/status` took ~2.2 s to paint *anything*. The owner's report was "demora demasiado en cargar"
and the requirement was explicit: the document must appear the moment the link is clicked,
whether or not the backend answers, with a loader on the elements.

## Measured before writing the step

| What | Measured | Where |
|---|---|---|
| `GET http://localhost:4321/en/status` | **ttfb 2.19 s / 2.54 s**, size 42 KB | `curl -w '%{time_starttransfer}'` |
| `GET http://localhost:8000/api/v1/health/services` | **2.12–2.33 s** (3 runs, stable) | `curl` |
| `GET http://localhost:8000/api/v1/health` (liveness) | **1.79 s** | `curl` |
| Per-probe latencies from one live payload | db 900 ms, schema 895 ms, ollama 5.8 ms (error), qdrant 335 ms, embeddings ~0 (cached) | response body |
| Other public pages | `/en` 0.07 s, `/en/login` 0.11 s | `curl` |

Two independent causes, both real:

1. **The backend runs its five probes sequentially.** `health_services()` awaits
   `_check_database()` → `_check_schema()` → `_check_ollama()` → `_check_qdrant()` →
   `_check_embeddings()` one after another, so the route costs the *sum*. `health()` and
   `health/ready` do the same with their two DB probes.
   In-process measurement of the primitives (`/tmp/probe_timing.py`):
   `db + schema` sequential = 1.79 s; the same two under `asyncio.gather` = 1.01 s;
   **all five gathered = 1.27 s wall vs 2.15 s sequential.**
2. **`frontend/src/pages/[locale]/status.astro` fetches in the frontmatter.** With
   `output: 'server'` the document cannot start until that `await` resolves, so the page's TTFB
   *is* the backend's TTFB — and `AbortSignal.timeout(10_000)` means an unreachable or
   half-dead backend holds the user on a blank page for up to 10 s.

The residual ~900 ms per DB probe is the dev pooler round trip, not the route: `docs/` already
records the same order of magnitude ("against the dev pooler that is ~800ms" for one extra
round trip, `frontend/src/lib/proxy-url.ts`), and `pool_pre_ping=True` pays a round trip on
every checkout. Concurrency hides that latency behind the slowest probe; it does not remove it.

## Design decisions taken

- **D1 — the backend fix is concurrency, not caching.** A document-level cache would make
  "Last updated" a lie. Out of scope: `_check_embeddings()` has no timeout of its own (it
  relies on the adapter), recorded as a follow-up rather than folded in here.
- **D2 — the frontend fix moves the fetch out of SSR entirely.** Rendering the shell and
  filling it client-side is the only way to satisfy "debe levantar la página en el momento en
  que se le hace click".
- **D3 — an Astro React island, not an inline `<script>`.** `config.ts` needs `AUTH_SECRET`
  (server-only) so the client cannot import it; props are how this repo passes values down, and
  public pages already mount islands (`index.astro` → `FaqAccordion client:idle`).
  `@/lib/health` is pure TypeScript, so the tested banner/badge rules move with it, unchanged.
- **D4 — the browser talks to a new public Astro endpoint, `/api/health/services`, never to the
  backend directly and never through `/api/v1/[...path]`.** The existing catch-all answers `401`
  without an Auth.js session and `/status` is a public page. A direct browser→backend call would
  work but would tie a public page to the backend's CORS allow-list, and that list is measured
  narrow: `access-control-allow-origin` came back for `http://localhost:4321`, and was **absent**
  for `http://127.0.0.1:4321` and for `https://storico.vercel.app` against the dev backend, while
  `prod.todo.md` records production declaring **exactly one** `*.vercel.app` origin. The old SSR
  fetch never cared — server-to-server has no CORS — so a direct call would have been a silent
  regression on any other host alias. Same-origin through Astro keeps the page working on
  `localhost`, `127.0.0.1`, production and previews, and costs one server-to-server hop that sits
  off the paint path. The new route hardcodes the single backend path it forwards: it is not a
  general public proxy. Chosen by the owner over the direct call on 2026-09-28.
- **D5 — `status-probes-mirror.test.ts` keeps its guard.** It greps the page source for
  `serviceStatus(health, '…')`, `DIAGNOSTIC_PROBES` and `serviceRows`. Those three declarations
  move into the island and the test follows them: the drift guarantee survives the move, it does
  not get deleted with the file layout.

## Allowed edit surfaces

- backend: `backend/src/storico/api/routes/health.py`,
  `backend/tests/test_api/test_health_services.py`, `backend/tests/test_health.py`
- frontend: `frontend/src/pages/[locale]/status.astro`,
  `frontend/src/pages/api/health/services.ts`,
  `frontend/src/lib/status-health-api.ts`,
  `frontend/src/components/react/StatusPanel.tsx`,
  `frontend/src/components/react/__tests__/StatusPanel.test.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/lib/__tests__/status-probes-mirror.test.ts`, `docs/testing.md`

## Tasks

| # | Task | Status | Commit |
|---|---|---|---|
| 1 | Run the health probes concurrently in `/health/services`, `/health`, `/health/ready`, with a test that fails on sequential execution | done | `d4498c8` — measured live after the change: services 2.15s → 1.02–1.29s, health 1.79s → 0.88s, ready → 0.90s; payload keys/order/scopes unchanged |
| 2 | Paint `/status` from a static shell + `StatusPanel` island with per-row loaders; public `/api/health/services` endpoint; i18n keys in both locales; retarget the mirror guard; update `docs/testing.md` | done | `606d37a` — TTFB `/en/status` **2.19–2.54 s → 0.014–0.025 s**; the raw HTML already carries the 6 pending badges (`animate-pulse` ×6, `Checking` ×8) and `aria-busy`; browser: shell painted at 643 ms with every row reading "Checking…", filled at 1697 ms (4 Operational, 2 Error, green banner + amber optional note); `/api/health/services` answers in 0.96 s; `/es/status` verified too |
| 3 | Verify end to end: backend pytest + ruff, frontend vitest + `astro build`, then measure TTFB and the loader in the browser | done | delegated `gentle-ai-verify`, **green-with-caveats**: `pnpm test` 54 files / 606 tests passed, `astro build` `Complete!`, `pytest -m unit` 251 passed, health route tests 41 passed, `ruff check` + `format --check` clean, i18n parity 753 keys both locales, mirror guard still 15 `expect(` / 5 `it(` with only its target file moved, no build output in git. Caveats: the tree changed under the verifier (those were the two inline fixes below, re-tested after), and its 11:56:31 `pnpm test` ran against the final bytes. The pre-existing `RuntimeWarning: coroutine 'Connection._cancel' was never awaited` reproduces with `tests/test_health.py` alone and is not from this change |

## Two defects the writer left, caught in review and fixed inline

- `frontend/src/i18n/en.json` / `es.json`: the edit re-indented an **unrelated** line
  (`common.retry`, 4 → 6 spaces) while adding `pages.status.retry`. Noise in a diff that is
  otherwise two added keys per file; corrected.
- `docs/testing.md`: the new trap sentence dated the behaviour change `2026-09-25`, the date of
  the previous `/status` incident, not of this one. Corrected to `2026-09-28`.

## Copy decision left visible for the owner

While pending, the banner renders `pages.status.checking` as its title and the page's own
`pages.status.description` ("Check the current status of Storico services.") as its subtitle —
the SEO string reused as UI copy. It reads correctly in both locales and costs no new key, so it
stayed; it is the one line of this change a reviewer may want to rewrite.


## What the residual latency is

~900 ms per database probe is the dev pooler round trip, not the route: `pool_pre_ping=True`
pays a round trip on every checkout, and `frontend/src/lib/proxy-url.ts` already records the same
order of magnitude for one extra trip. Concurrency hides that behind the slowest probe; it does
not remove it. Removing it means a nearer database or a warm connection for the probes, which is
an infrastructure decision, not a route change.

## Follow-ups named, not bundled

- `_check_embeddings()` has no `asyncio.timeout` of its own — one hanging provider can hold the
  diagnostics route open past the frontend's timeout (the endpoint's 10 s abort now absorbs it).
- The `API Server` row changed meaning on purpose — it can no longer be proven by "the document
  arrived" — and now reports the outcome of the health call itself. Documented in
  `StatusPanel.tsx` above `apiState`; a reviewer who wants the old meaning back has to put a
  server-side call back into the document, which is the thing this unit removed.
- No auto-refresh. The page is a snapshot plus a manual Retry.
