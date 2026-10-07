# rate-limiting

> **Status**: authorized by the owner on 2026-10-07 (mechanism and numbers chosen the same day), in
> progress on branch `feat/rate-limiting`, **stacked on `docs/truth-reconciliation`**. Nothing pushed. Receipt-driven development is
> off in this clone.
> **Created**: 2026-10-07

## Goal

Close the last open security item of `prod.todo.md`: an in-application rate limit, keyed by the
authenticated user, with the health endpoints exempt.

It matters now and not later because the deployment is public with open Google and GitHub
registration, and the URL is about to be shared with six thesis evaluators.

## The owner's decisions

**Mechanism: `slowapi` inside the application**, keyed by the JWT subject, not a Caddy IP limit.
A proxy limit cannot see who the caller is, and its configuration lives on the VM outside version
control — the same class of invisible configuration this repository already documents as failing
silently. The trade accepted: an in-process limiter with in-memory storage, which is correct for one
container and would need a shared backend if the API ever runs in more than one.

**Numbers, per key, one-minute window:**

| Route | Limit |
| --- | --- |
| Reads (default) | **120/min** |
| Writes (status, labels, dependencies) | **60/min** |
| **Extraction** | **10/min** |
| CSV import | **5/min** |
| LLM probes (`/settings/llm/models`, `/settings/llm/test`) | **10/min** |
| Health (`/health`, `/health/ready`, `/health/services`) | **exempt** |

## What was measured before designing

| Claim | Evidence |
| --- | --- |
| `slowapi` is not a dependency yet | absent from `backend/pyproject.toml` and from `backend/src` |
| **The health exemption is mandatory, not prudence** | `deploy-backend.yml:135-157` polls `http://localhost:8000/api/v1/health/ready` in a bounded loop with `curl -sf` until it answers 2xx; a limit on that endpoint would fail the deploy's own gate |
| The browser does not reach the API directly | `frontend/src/pages/api/v1/[...path].ts` proxies every call |
| The proxy **always** attaches a JWT | `frontend/src/pages/api/v1/[...path].ts:67` sets `Authorization: Bearer <jwt>`, so application traffic is authenticated and therefore keyed per user |
| The proxy does **not** forward the client's address | `frontend/src/pages/api/v1/[...path].ts:58-60` builds headers from scratch — "do NOT copy from request" — and only sets `Authorization` and `Content-Type` |
| uvicorn does not reconstruct one either | `backend/Dockerfile:29`: `uvicorn ... --host 0.0.0.0 --port 8000 --factory`, no `--proxy-headers` |
| The frontend already maps `error_code` to a translated headline | `5412bb3`; a new code needs its key in both locales or the banner falls back to raw prose |

**Consequence of the last three rows, and it is designed around, not discovered later:** the IP
fallback bucket is *coarse* for anything arriving through the Vercel proxy, because the client
address the backend sees is the serverless function's. That is acceptable here — the authenticated
key is what carries the protection, and a shared fallback bucket throttling an anonymous flood is
the right outcome — but it has one honest edge: an anonymous flood through the proxy can consume the
fallback bucket that a legitimate caller with an expired token would have used.

## Design

- **`backend/src/storico/api/rate_limit.py`** (new): builds the limiter, the key function, the
  exemption set and the 429 handler. The limiter is built **inside `create_app()`**, not at module
  import: a module-level limiter keeps its in-memory counters across every app a test builds, which
  is a flakiness source with no upside.
- **Key function**: the JWT `sub` **when the token verifies**, otherwise the client address. An
  invalid, expired or absent token must **not** be able to mint fresh buckets — that is the bypass a
  naive "parse the sub without verifying" implementation ships with, and it gets its own test.
- **Limits come from `Settings`** with the numbers above as the code defaults, so a missing
  environment variable cannot silently disable the protection. Production keeps the defaults.
- **429 uses the canonical envelope**: the same `detail` + `error_code` shape as every other error
  (`api/errors.py`), with a new code in `api/error_codes.py` and the frontend key that goes with it.
  slowapi's default response body is not that shape.
- **The test suite must not trip its own limiter.** 1305 tests drive thousands of requests through
  one identity; with production numbers the suite fails on itself. The conftest raises the limits and
  says why, and a dedicated module builds apps with tight limits to test the limiter itself. The
  production defaults stay in the code, so this is not a switch that turns the feature off — it is a
  separate app instance with different settings.

## Tasks

- [x] **WU1 — the limiter, its key, its envelope and its exemptions** (backend + tests).
- [x] **WU2 — the frontend's 429 headline in both locales**, and the documents: `docs/security.md`,
  `AGENTS.md` feature row 42, `prod.todo.md`'s row, `docs/api.md` if the repo's convention puts error
  codes there. (It does — §Errores lists codes with their HTTP statuses — so `429` +
  `RATE_LIMIT_EXCEEDED` landed in that table.)

## Non-goals

- **Not** a Caddy or Vercel-level limit. The owner chose the application, and the reasoning is above.
- **Not** protection against one person creating many accounts: that is what open registration buys
  an attacker, and a rate limit does not change it. Recorded, not solved.
- **Not** a distributed limiter. In-memory storage for one container is the accepted trade; the
  limitation goes in the docs rather than in a hopeful comment.
- **Not** per-workspace quotas or billing-style accounting. The unit is the authenticated user.

## Limitations to record, not bury

- Counters live in the process; a second container would double every effective limit.
- The IP fallback is shared for proxied traffic (measured above).
- The limiter does not survive a restart, and it is not persisted: a burst across a container
  restart is not counted.

## Evidence log

(one row per work unit, added as each lands)

| Work unit | Commit | Evidence |
| --- | --- | --- |
| WU1 — limiter, key, envelope, exemptions | `813374f` | (The hash `226dcb1` named in the delegation does not resolve in this clone; `813374f` is the branch's WU1 commit — verified with `git show 813374f --stat`.) The commit touches 13 files, +637: new `api/rate_limit.py` (223 lines — limiter built in `create_app()`, verified-subject key function, tier table, health exemptions, canonical 429 handler) and `tests/test_api/test_rate_limiting.py` (301 lines); `slowapi` pinned `>=0.1.10,<0.2` in `pyproject.toml`; five endpoints gained an unused `request: Request` parameter; `.env.example` and `backend/.env.example` document the five `STORICO_RATE_LIMIT_*` variables. Focused rerun on this tree: `conda run -n storico python -m pytest tests/test_api/test_rate_limiting.py -q` → **9 passed**; full suite `conda run -n storico python -m pytest -q` → **1314 passed, 45 skipped**. |
| WU2 — the 429 headline and the documents | (working tree, uncommitted — the parent owns commits) | RED observed first in the mirror guard `src/lib/__tests__/error-codes.test.ts`: `pnpm vitest run src/lib/__tests__/error-codes.test.ts` → **2 failed, 6 passed** — `RATE_LIMIT_EXCEEDED` missing from both `errorCodes` maps, and `EXPECTED_REGISTRY_COUNT` pinning 44 against a registry of 45. GREEN for everything inside this work unit's edit surfaces: the key added to `errorCodes` in `en.json` and `es.json` (“Too many requests in a short time. Wait a moment and try again.” / “Demasiadas solicitudes en poco tiempo. Espera un momento e inténtalo de nuevo.” — no retry time invented, matching the body's “slow down and retry shortly” and the absent `Retry-After`); `pnpm vitest run src/i18n` → **79 passed across 6 files** (the neutral-Spanish and locale-parity guards among them); `pnpm exec tsc --noEmit` → exit 0; backend suite as in WU1. **Deliberately left red at handoff, and closed by the parent**: the count pin (`EXPECTED_REGISTRY_COUNT` 44 → 45) lives in `src/lib/__tests__/error-codes.test.ts`, which is outside this work unit's allowed edit surfaces — the writer stopped and asked rather than touching an unauthorized file, which is the right call. The parent then verified the number from both sides (45 `NAME = value` lines and 45 entries in `__all__` inside `error_codes.py`) before applying the one line itself: **44 → 45**. What makes that safe is the guard's own message, "the backend registry grew or shrank: update EXPECTED_REGISTRY_COUNT and the map together" — it exists to force a deliberate update when the registry moves, not to block one. The map keys count (45 + 5 route codes) and the registry count both verify once that constant moves. Prose landed in `docs/security.md` (the open item closed with the in-process and IP-fallback limitations stated), `AGENTS.md` row 42, `prod.todo.md` § Seguridad, `docs/api.md` §Errores, and this record. |
