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

- [ ] **WU1 — the limiter, its key, its envelope and its exemptions** (backend + tests).
- [ ] **WU2 — the frontend's 429 headline in both locales**, and the documents: `docs/security.md`,
  `AGENTS.md` feature row 42, `prod.todo.md`'s row, `docs/api.md` if the repo's convention puts error
  codes there.

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
