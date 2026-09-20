# ODD Feature: llm-probe-credential-leak

> **Status**: implemented on `fix/llm-probe-credential-leak` (off `main` @ `5d4d021`), not pushed.
> Recip-driven development is **off** in this clone; the independent verification is recorded below.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/llm-probe-credential-leak`.

## Process correction: the review switch was on

**This record said receipt-driven development was "off in this clone", and for the second half of
this session that was false.** The switch read `off (decided by default)` when the session began, and
was turned on globally mid-session — `~/.gentle-ai/state.json` records `rdd_mode = 'on'` with
`rdd_mode_recorded_at = 2026-09-19T18:49:02Z`. This record's line was copied forward from the earlier
features without re-checking it, which is **the same defect this batch spent the day removing**: a
claim about state, written once and never re-read.

So native review was the expected path for this candidate and it did not run. Independent verification
did, and it found something material; its findings are recorded below. Whether that is an adequate
substitute is the maintainer's call, not this record's.

It could not have run from the parent session regardless: the `gentle_review` facade answers
`native-status-package-binary-missing` here, while a subagent's context reached the lifecycle and
returned an unresolved provider consent envelope for the last candidate. The recovery is
`node scripts/install-gentle-ai.mjs` from the installed package directory, which is a maintenance
action rather than something this session takes on its own.

## Problem

Found by the `encrypt-workspace-api-keys` verification while it was checking whether any secret could
escape. It is a **pre-existing** defect, not caused by that feature, and it is the same class of harm
that feature exists to remove — reached by transport instead of storage.

Two escape paths, both on the admin-only model probe (`POST /workspaces/{id}/settings/llm/models`):

1. **The credential travels in the URL.** `fetch_gemini_models`
   (`backend/src/storico/api/routes/workspace_settings.py:542`):

   ```python
   url = f"{GEMINI_API_BASE}/models?key={api_key}"
   ```

   That URL is what `httpx` logs at INFO for every request, so the credential lands in the server log.

2. **The credential comes back in the response body.** The route's error mapping interpolates the
   transport error verbatim:

   ```python
   raise HTTPException(status_code=502, detail=f"Failed to fetch models from {probe.provider}: {e}")
   ```

   An `httpx.HTTPStatusError`'s message contains the request URL, key and all, so a 401 from Gemini
   returns `.../models?key=AIza-...` to the caller. And the credential may be the **stored, decrypted
   one**: `_resolve_probe` falls back to the saved row when the body carries no provider, so the
   probe can be using the workspace's persisted key.

### The part that makes it a defect rather than a trade-off

The route's own docstring says why it is a `POST`:

> ``POST`` rather than ``GET`` with query parameters because the pending selection carries an API key,
> and a query string writes it into access logs.

So the route avoided the query string on its own side, and then the Gemini fetch reintroduced exactly
the hazard the docstring claims to have prevented. The module's docstring is equally explicit that
`GET /llm/status` answers "with the missing field names and never with a value". The leak contradicts
two stated contracts in the same file.

### Scope, measured

Exactly **one** place in the backend puts a credential in a URL:

```text
$ grep -rn "key={\|?key=\|api_key={" backend/src/storico --include=*.py
backend/src/storico/api/routes/workspace_settings.py:542:    url = f"{GEMINI_API_BASE}/models?key={api_key}"
```

Every other path already uses a header: `openai` and custom providers send
`Authorization: Bearer`, `anthropic` sends `x-api-key`, and `ollama` needs no credential. The Gemini
**adapter** — the one that actually performs extractions — uses `genai.Client(api_key=...)`, and the
Google SDK sends the key as a header rather than in the URL. So the raw-httpx probe is the single
deviation, and the mechanism the fix should use is the one the rest of the application already uses.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Where the Gemini credential goes | The `x-goog-api-key` header, matching what the Google SDK does on the extraction path. The URL becomes `{GEMINI_API_BASE}/models` and carries no credential. |
| D2 | What the 502 may say | The provider name and, when the failure came with a response, its status — both are ours. The exception's text is not: it is a dependency's message, it changes between versions, and in the case that prompted this it carried the credential. The full error goes to the log, where an operator can see it and a client cannot. |
| D3 | Logging the error | The route logs it server-side. After D1 the URL in that message is keyless, which is what makes logging it safe. |
| D4 | Other providers | Nothing to change — they already use headers. Verified rather than assumed, with the grep above. |
| D5 | Tests | Two assertions that would each have caught this independently: the request the probe sends carries no credential in its URL and does carry it in the header; and the 502 body contains neither the credential nor the dependency's message, even when the transport error itself contains the credential. |
| D6 | The same class one route over | `GET /api/v1/health/services` is **unauthenticated** and answered with `str(e)` for three probes. Fixed here too, because it is the same defect with a wider audience, and because the route has no consumer to break. See below. |

## The same class, one route over: the health endpoint was worse

Checking the *class* rather than the instance paid twice.

**`GET /api/v1/health/services` had no authentication and answered with `str(e)`** for its three
probes (`api/routes/health.py`). A driver's message can name an internal host, a port, a database or
a credential, and this route publishes to anyone who asks:

```text
{"status": "error", "latency_ms": 12.3,
 "error": "connection failed: postgresql://storico:sup3r-s3cret@internal-db:5432/storico"}
```

Two things made it a defect rather than a deliberate diagnostic: the route has **no authentication
dependency** at all, and **nothing consumes the field** — no reference to `health/services` exists in
`frontend/src`, so the detail was cost with no reader. The file already had the right idea in its own
`TimeoutError` branch, which returns the spelled `"connection timed out"`; the generic branch simply
did not follow it. Now each service spells its reason (`connection failed`, `not reachable`) and the
exception goes to the log.

The route had **no tests at all**, which is consistent with how this survived. `tests/test_api/test_health_services.py`
is new: it fails all three probes with messages shaped like the real thing — one of them a connection
string with a credential in it — and asserts that none of it reaches the caller while all of it
reaches the log. Mutation-checked.

One drive-by in the same file: the database probe ran `text("SELECT 1")`, a hand-written SQL string
in a route that takes no input from the caller. It compiles to `SELECT 1` with **zero bound
parameters**, so nothing could have been injected into it — the analyzer that flagged it was wrong
about the risk — but the change is free and removes raw SQL from the route, so it is now
`select(literal(1))`. The test asserts the probe still reports `ok`, which is what covers the change.

## A premise I had backwards

The record first described the log leak as happening on a *failed* probe. Measured, it is the
opposite, and worse:

```text
SUCCESS -> httpx logs: HTTP Request: GET https://example.test/v1/models?key=SUP3R-SECRET-KEY "HTTP/1.1 200 OK"
FAILURE -> no httpx record at all
```

`httpx` builds that INFO line from the response, so it exists only when a request **succeeds**. The
credential therefore landed in the log on **every successful Gemini probe** — the ordinary case,
deterministically — and not only when something went wrong. The log guard probes successfully for
that reason and says so in the test, so the next reader does not have to re-derive it.

## Non-goals

- No change to the extraction adapters, which already send credentials correctly.
- No suppression of `httpx`'s request logging: after D1 there is nothing to suppress, and silencing a
  library's request log wholesale would hide the endpoint each probe actually hit.
- A user who writes a credential into their own custom provider's `base_url` will still have that URL
  logged. That is their endpoint configuration rather than a credential we place there, and it is
  recorded as a follow-up rather than solved here.

## Tasks

- [x] Move the Gemini credential to the header.
- [x] Stop echoing the transport message; keep the status and log the rest.
- [x] Tests: no credential in the URL, credential present in the header, and a 502 whose body carries
      neither the credential nor the dependency's text.
- [x] Class-shaped guards: every credential-bearing fetcher is driven, and the log is asserted clean
      on the path where the leak actually happened.
- [x] The same class one route over: the unauthenticated health endpoint stopped publishing `str(e)`,
      and got the tests it never had.
- [x] Mutation-check both tests.
- [x] Run backend `ruff check src tests`, `ruff format --check src tests`, `pytest -q`.
- [ ] Work-unit commit on the feature branch — **pending**.
- [ ] Independent verification — **pending**.
- [ ] Fast-forward into `main`, delete the branch, re-gate, push — **pending**.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Backend suite | `python -m pytest -q` | **701 passed, 1 skipped** (695 before; +6) |
| Backend lint (CI scope) | `ruff check src tests` | `All checks passed!` |
| Backend format | `ruff format --check src tests` | `225 files already formatted` |
| The credential left the URL | the fetcher test asserts on the real request | URL has no credential and no `key=`; `x-goog-api-key` carries it |
| The response stopped carrying it | the route test crafts a transport error whose message embeds the credential | 502 body contains neither the credential nor `Client error`, and does name `gemini` and `401` |
| Non-vacuity, half 1 | put `?key={api_key}` back | **both tests fail** — `assert 'AIza-…' not in 'https://gen…DER-STAND-IN'` |
| Non-vacuity, half 2 | interpolate `{e}` into the 502 again | **fails** at `assert credential not in body` |
| One place did this | `grep -rn "?key=\|key={" backend/src` | the single Gemini line; every other provider already used a header |
| Class-shaped, not gemini-shaped | mutate the **anthropic** fetcher's URL | the URL guard fails — which the first version of these tests could not do |
| The log half is real | probe successfully and capture the `httpx` logger | `HTTP Request: GET <url> "HTTP/1.1 200 OK"` is logged; the credential is not in it |
| The health endpoint is closed | fail all three probes with credential-shaped messages | the body carries none of them, the log carries all three |
| The health probe still works | `GET /api/v1/health` | `database.status == "ok"` — which is what covers the `select(literal(1))` change |
| Format gate | `ruff format --check src tests` | 225 files — one line of the new test exceeded 100 characters and was reformatted |

The credential the test uses is a stand-in, never a real key, and the assertion is on the response
body rather than on a log line, because the log is where the error is supposed to go.

## Independent verification

Ran over `5d4d021..986ed1a` — the fix and its record, before the guards below were written. It
confirmed the core claims: the credential is out of the URL, out of the `httpx` INFO line, and out of
the 502 body, and the error is relocated to a WARNING log with its traceback preserved rather than
discarded.

It then found three things the record had not accounted for, and **stopped at a provider consent
envelope** rather than answering it — correctly, because that is the human's decision. The envelope
went unresolved and could not be submitted from the parent session (the facade reports
`native-status-package-binary-missing` there); the answer given was to skip this candidate, which is
candidate-scoped and leaves reviews enabled.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| V1 | medium | **The tests were gemini-shaped, not class-shaped.** Reintroducing `?key=` in `fetch_anthropic_models` passed the entire suite (697 passed, 1 skipped) — the fix was one provider, and nothing enforced the rule for its siblings. | **Fixed** — every credential-bearing fetcher is now driven and the assertions are on the requests they make. Re-mutating the anthropic fetcher fails the guard. |
| V2 | medium | **Nothing asserted the log was clean.** The other half of the leak had no test at all. | **Fixed** — and writing it corrected a premise: `httpx` logs the request line on **success** and nothing on a connect failure, so the credential leaked on every successful Gemini probe, not only on a failure. |
| V3 | medium | **The same class was live one route over**: `GET /api/v1/health/services`, unauthenticated, answered with `str(e)` for three probes. A sibling admin route, `POST /api/v1/llm/test`, echoes transport errors in five branches. | **Fixed for health** (with the tests it never had); **recorded** for `/llm/test`, whose message is its documented response contract. |

## Follow-ups this surfaced, recorded rather than bundled

1. **`POST /api/v1/llm/test` echoes the transport error into its response** (`api/routes/settings.py`),
   in five branches: `message=f"... connection failed: {e}"`. It is admin-only and that message is the
   route's user-facing contract, so it is a weaker case than the two fixed here — but it is the same
   shape, and the caller supplies `base_url`, so a credential placed there would be echoed back to them
   and logged. Worth one decision rather than a unilateral change to a documented response.
2. **A user who writes a credential into their own custom provider's `base_url`** will still have that
   URL logged, because it is their endpoint configuration rather than a credential we place there.
   Nothing can be done from our side beyond not echoing the URL, which the probe now does.
3. **`x-goog-api-key` is not verified against the live Gemini API** — there is no network access here.
   The evidence is that the Google SDK sends it that way on the extraction path, which is the same
   endpoint and the same credential.
4. **The two guards are class-shaped for the fetchers, not for every future request.** They drive the
   four fetchers that take a credential and assert on the requests those make. A fifth fetcher added
   later would need adding to the list — the guard would not notice it on its own, and that limit is
   worth knowing rather than assuming away.
