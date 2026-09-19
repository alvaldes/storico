# ODD Feature: llm-probe-credential-leak

> **Status**: implemented on `fix/llm-probe-credential-leak` (off `main` @ `5d4d021`), not pushed.
> Recip-driven development is **off** in this clone; the independent verification is recorded below.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/llm-probe-credential-leak`.

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
- [x] Mutation-check both tests.
- [x] Run backend `ruff check src tests`, `ruff format --check src tests`, `pytest -q`.
- [ ] Work-unit commit on the feature branch — **pending**.
- [ ] Independent verification — **pending**.
- [ ] Fast-forward into `main`, delete the branch, re-gate, push — **pending**.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Backend suite | `python -m pytest -q` | **697 passed, 1 skipped** (695 before, +2) |
| Backend lint (CI scope) | `ruff check src tests` | `All checks passed!` |
| Backend format | `ruff format --check src tests` | `224 files already formatted` |
| The credential left the URL | the fetcher test asserts on the real request | URL has no credential and no `key=`; `x-goog-api-key` carries it |
| The response stopped carrying it | the route test crafts a transport error whose message embeds the credential | 502 body contains neither the credential nor `Client error`, and does name `gemini` and `401` |
| Non-vacuity, half 1 | put `?key={api_key}` back | **both tests fail** — `assert 'AIza-…' not in 'https://gen…DER-STAND-IN'` |
| Non-vacuity, half 2 | interpolate `{e}` into the 502 again | **fails** at `assert credential not in body` |
| One place did this | `grep -rn "?key=\|key={" backend/src` | the single Gemini line; every other provider already used a header |

The credential the test uses is a stand-in, never a real key, and the assertion is on the response
body rather than on a log line, because the log is where the error is supposed to go.
