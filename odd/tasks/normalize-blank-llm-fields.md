# ODD Feature: normalize-blank-llm-fields

> **Status**: done — three commits on `feat/normalize-blank-llm-fields` (`17e8e6f`..
> `7bd4ce0`), plus the evidence commit that carries this line (four against the parent
> branch); nothing was pushed. Receipt-driven development is **off** in this clone, so no
> native review ran; one independent verification did, recorded below with its findings and
> their disposition.
> **Created**: 2026-06-30
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/normalize-blank-llm-fields`, stacked on
> `feat/honest-llm-copy-and-doc-drift` (nothing pushed yet, so this branch's diff against
> its parent is exactly this slice).
> **Receipt-driven development**: off in this clone.

## Problem

Slice 2 of the review of `llm-config-validation-gate`'s follow-ups.

A blank value is not treated as "absent" consistently, so a workspace whose stored
`base_url` (or `api_key`) is whitespace passes the completeness gate and is then handed to
a provider as a real endpoint. Measured with the real code before the fix:

```txt
probe ollama base_url='   ' -> HTTPError(UnsupportedProtocol) -> la ruta responde 502
port   ollama base_url='   ' -> OllamaAdapter  cliente.base_url=URL('')
port   openai base_url='   ' -> OpenAIAdapter  cliente.base_url=URL('%20%20%20/')
port   anthropic base_url='   ' -> AnthropicAdapter  cliente.base_url=URL('%20%20%20/')
regla  ollama base_url='   ' -> missing = ()          # el gate deja pasar
llamada -> LLMResponseError: HTTP Error: Request URL is missing an 'http://'...
```

That is the dirty path this product just closed for a *missing* credential, still open for
a *blank* one: the extraction is accepted with `202`, the pending row is created, and the
failure happens inside the background task — leaving the user story in
`failed_extraction`. The model list answers a misleading `502` ("could not reach the
provider") for what is really a malformed stored value.

Reachable from two directions: `PUT /settings/llm` stores the blank string verbatim
(`Field(max_length=500)`, no normalization), and a row written before that is read back
verbatim by every consumer. `gemini` is structurally immune because its adapter ignores
`base_url`.

The root cause is that "blank means absent" was implemented **three times** with three
different meanings: `_is_set` in the readiness rule (blank is unset), `if ws_config.base_url`
in the routes (blank is set), and `if not base_url` in `_build_llm_port` (blank is set).

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | One definition | A single `normalize_optional(value)` in the domain readiness module defines "a configured value, or `None` when it is blank". `_is_set` is re-expressed in terms of it, so the rule and the normalization cannot disagree. |
| D2 | Normalize on write **and** on read | On write so the table stops accumulating junk; on read so rows already holding it behave. Read-side is what fixes the reported defect; write-side stops new occurrences. |
| D3 | Which fields | `base_url` and `api_key` only — the two the defect is about. `provider` is **not** touched: reinterpreting a blank provider name as Ollama would be a silent reinterpretation, not a normalization, and the provider registry already refuses a blank name. |
| D4 | Where, on read | Every boundary that hands the value to something that will use it: `resolve_llm_config` (what the form, the status route and the probe body see), `_probe_models` (the model list), the extraction route (what the background task receives), and `_build_llm_port` (the adapter itself). No single chokepoint exists — each consumer reads the repository directly — so the helper is the single definition and the boundaries are its call sites. |
| D5 | `_build_llm_port` keeps its own guard | It is the last line before an SDK is constructed. Its checks become "after normalization", so `if not api_key` now means what it always read as. |

## Non-goals

- No change to the completeness rule's vocabulary, per-provider requirements, or the
  refusal contract.
- No migration for rows already holding a blank value: they are handled on read (D2), so a
  rewrite is unnecessary and a data migration would be destructive for no gain.
- No trimming of *meaningful* values: a key with internal spaces or a real trailing
  character is preserved as typed; only all-whitespace collapses to `None`.
- No change to `provider`, `model`, `temperature` or `max_tokens` handling.
- No change to the provider registry's own name normalization.

## Established facts (verified)

- Readiness rule: `backend/src/storico/domain/services/llm_config_readiness.py` —
  `_is_set(value)` is `bool(value and value.strip())`, i.e. blank is unset.
- Write path: `api/routes/workspace_settings.py` `upsert_llm_config` copies
  `body.base_url` / `body.api_key` straight into the entity; `LLMConfigRequest` only
  bounds length (`api/schemas/workspace_llm_config.py`).
- Read paths that bypass normalization: `resolve_llm_config` (`ws_config.base_url or …`),
  `_probe_models` (`probe.base_url or "http://localhost:11434"` for Ollama and
  `if not probe.base_url: return []` for a custom provider), `api/routes/extraction.py`
  (`ws_config.base_url if ws_config.base_url else None`), and
  `infrastructure/tasks/extraction_task.py` `_build_llm_port` (`if not api_key`/`if not
  base_url`).
- The blank value is storable: `api_key`/`base_url` are `String(500)`/`max_length=500`
  with no strip anywhere.
- `gemini` ignores `base_url` in `_build_llm_port`, so it cannot exhibit the defect.
- Test layout that applies: `tests/test_unit/` for the helper,
  `tests/test_api/test_workspace_settings_llm_config.py` and
  `tests/test_api/test_workspace_settings_models.py` for the API boundaries,
  `tests/test_api/test_extraction.py` for the route, and
  `tests/test_unit/test_llm_port_selection.py` for the adapter.

## Tasks

### T-001 — The single definition of "blank means absent"

- **Status**: pending
- **Files to modify**: `backend/src/storico/domain/services/llm_config_readiness.py`,
  `backend/tests/test_unit/test_llm_config_readiness.py`
- **What**: add `normalize_optional(value: str | None) -> str | None` and express `_is_set`
  through it (D1), so there is exactly one comparison that decides whether a value counts.
- **Acceptance**: `.venv/bin/pytest tests/test_unit/test_llm_config_readiness.py` passes;
  new cases: `None`/`''`/whitespace → `None`; a padded real value is returned stripped; a
  value with internal spaces keeps them.
- **Allowed edit surfaces**: `backend/src/storico/domain/services/llm_config_readiness.py`,
  `backend/tests/test_unit/test_llm_config_readiness.py`

### T-002 — Stop storing blanks

- **Status**: done (commit `bb6e742`, together with T-003 — see the note below)
- **Files to modify**: `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_llm_config.py`
- **What**: `upsert_llm_config` normalizes `base_url` and `api_key` before merging (D2/D3),
  so a blank submitted value is stored as `None` instead of as a string of spaces.
- **Acceptance**: `.venv/bin/pytest tests/test_api/test_workspace_settings_llm_config.py`
  passes. Cases: PUT with `base_url="   "` stores `None` and the read-back resolves to the
  Ollama host for Ollama / to `None` for a cloud provider; PUT with a padded real endpoint
  stores the trimmed value; an omitted field still leaves the stored value untouched.
- **Depends on**: T-001
- **Allowed edit surfaces**: `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_llm_config.py`

### T-003 — Treat blanks as absent everywhere the value is read

- **Status**: done (commit `bb6e742`)

> T-002 and T-003 landed in **one commit**, which deviates from the plan. Both changes are
> edits to the same three files (`workspace_settings.py` holds the write path *and* one read
> path, and the tests for both live in the same two test files), so separating them would
> have needed partial-file staging for no review benefit. Each half is independently
> testable and was run green on its own.
- **Files to modify**: `backend/src/storico/api/routes/workspace_settings.py` (resolve +
  probe), `backend/src/storico/api/routes/extraction.py`,
  `backend/src/storico/infrastructure/tasks/extraction_task.py`,
  `backend/tests/test_api/test_workspace_settings_llm_config.py`,
  `backend/tests/test_api/test_workspace_settings_models.py`,
  `backend/tests/test_api/test_extraction.py`,
  `backend/tests/test_unit/test_llm_port_selection.py`
- **What**: apply `normalize_optional` at the four read boundaries (D4/D5). A legacy row
  holding whitespace must then behave exactly like a row holding `NULL`: the probe falls
  back to the default host instead of answering `502`, the background task receives `None`,
  and the adapter gets the provider's default rather than a URL of spaces.
- **Acceptance**: the API suites and the adapter unit suite pass. Cases: a seeded row with
  `base_url="   "` probes Ollama's default host (not a 502) and the extraction route hands
  `base_url=None` to the background task; `_build_llm_port("ollama", base_url="   ")`
  produces the configured Ollama host; `_build_llm_port("openai", api_key="   ")` raises
  `LLMError` (it would previously have built an adapter with a blank key).
- **Depends on**: T-001
- **Allowed edit surfaces**: `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/src/storico/api/routes/extraction.py`,
  `backend/src/storico/infrastructure/tasks/extraction_task.py`,
  `backend/tests/test_api/test_workspace_settings_llm_config.py`,
  `backend/tests/test_api/test_workspace_settings_models.py`,
  `backend/tests/test_api/test_extraction.py`,
  `backend/tests/test_unit/test_llm_port_selection.py`

### T-004 — Verification gate

- **Status**: pending
- **What**: run the repo gate and record it; delegate an independent verification that
  re-measures the four pre-fix probes above and confirms each one now behaves as a `NULL`
  row would.
- **Commands**: `cd backend && .venv/bin/pytest -q`, `.venv/bin/ruff check src tests`,
  `.venv/bin/ruff format --check src tests`; `cd frontend && node_modules/.bin/vitest run`
  and `node_modules/.bin/tsc --noEmit` (untouched by this slice, run as the regression
  baseline).
- **Acceptance**: every command passes and the counts are recorded.
- **Depends on**: T-001, T-002, T-003

### T-005 — Close the feature

- **Status**: done (this document's commit)
- **What**: flip the status line, write the evidence log with real commit identities and
  observed output, and record the follow-ups.
- **Depends on**: T-004

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Normalizing on write silently changes a value the user typed | An endpoint the user meant to keep loses its padding | Only all-whitespace collapses; the trim applies to `base_url`/`api_key`, never to `provider` or `model` (D3) |
| The five boundaries drift again | One consumer keeps treating blank as set | One helper, and each boundary gets a case in its own suite; the adapter is the last one, so a regression there is caught by the unit suite before any API test |
| A test pins the junk | The suite locks in the defect | The extraction case asserts the background task receives `None`, which is the corrected contract, not the current one |
| Touching `_build_llm_port` changes routing | An adapter is selected differently | Its routing branches are untouched; only the two blank checks are re-expressed after normalization, and the existing 8-case suite runs unchanged |

## Evidence log

_(each completed task records its commit identity here — no row is written before its
command has actually run)_

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `17e8e6f` | `normalize_optional` added as the single definition, with `_is_set` re-expressed through it. 13 new unit cases (**41 passed** in the file), including one that pins the two cannot disagree by asserting the derivation through the public rule. `ruff check` and `ruff format --check` clean. |
| T-002 | `bb6e742` | `upsert_llm_config` normalizes `base_url`/`api_key` both from the body and from the value carried over, so a save also repairs a legacy blank. 5 new API cases. Red run with the source reverted to the parent: included in the 22 failures below. |
| T-003 | `bb6e742` | Normalization applied at the four read boundaries: `resolve_llm_config`, `_probe_models`, the extraction route, and `_build_llm_port`. 34 new cases across four suites. Whole backend suite **624 passed, 1 skipped**; red run with the three consumer files reverted: **22 failed**, and the empty-string case correctly did **not** fail. |
| T-004 | `7bd4ce0` | Gate and independent verification, below. Its finding — a fifth boundary the slice had missed — is fixed there, with the first tests the connection route has ever had. |
| T-005 | this document | Status, evidence, the verification record and the dispositions. |

## Verification (RDD off — independent verification, not native review)

One `gentle-ai-verify` run over `841f66e..bb6e742`, read-only, with every probe in a `/tmp`
copy and `PYTHONPATH` pointed at it (it verified `storico.__file__` resolved to the /tmp
tree, and that `normalize_optional` was absent from the reverted one). Gate it observed:
backend **624 passed, 1 skipped**, `ruff check` clean, `ruff format --check` clean over 210
files; frontend **30 files / 351 passed**, `tsc` exit 0 — and it correctly flagged that the
frontend numbers are baseline evidence, since this slice touches no frontend file.

What it confirmed independently:

- **The before/after table re-measured row by row, in both trees**, using the real
  `_build_llm_port`: all four rows as claimed, with the fixed values *byte-identical to
  passing no `base_url` at all* — which is the strongest form of "blank equals absent".
- **The blank credential is refused** for openai/anthropic/gemini, where the parent built
  an SDK client with `'   '`; and a custom provider's blank key still collapses to the
  placeholder, as intended.
- **The completeness rule is behaviourally identical**: over a generated grid of 8
  providers × 17 values³ = **39,304 rows**, `differing rows: 0`.
- **The write path does not over-reach**: internal spaces preserved, omitted fields still
  untouched, a single-character value and a path-bearing endpoint preserved, all six fields
  replaced byte-identically to the parent.
- **`provider`/`model`/`temperature`/`max_tokens` unchanged**, and a whitespace provider is
  treated as a custom provider consistently by all three consumers, so no new disagreement.
- **The new tests are load-bearing**: with only the source reverted, **22 tests failed and
  zero pre-existing tests failed** (624 − 561 = 22 + the 41 uncollected from the
  import error). No failing test name exists in the parent tree.
- **The defect was specifically whitespace**: under the reverted source,
  `test_a_blank_endpoint_is_the_default_not_a_url_of_spaces[""]` **passed** while
  `["   "]` and `["\t\n"]` failed. An empty string was never the bug.

### Findings and disposition

- **F1 (fixed in `7bd4ce0`) — pre-existing, low, and the one boundary the slice missed.**
  `POST /api/v1/llm/test` (`api/routes/settings.py`) reads `base_url`/`api_key` from the
  **request body** and never normalized them: a blank endpoint reached the adapter as
  `'   '` (Ollama's branch kept spaces because they are truthy), and a blank cloud
  credential passed the `if not body.api_key` guard to build an SDK client with it. The
  verifier judged it out of the slice's stated scope (a stored workspace row) but exactly
  the defect class the slice exists to remove — in a **documented** public endpoint. Fixed
  by normalizing once at the top of the handler, and it now has the first tests that route
  has ever had: **7 cases**, all 7 failing against the parent's route.
- **F2 (accepted, informational) — the empty string is now also stored as `None`.** The
  parent stored `""` for these two fields and `resolve_llm_config` returned `""`. The
  literal claim was "`None` where it used to store spaces"; the empty string now collapses
  too. That is the defined rule and is consistent with the read side, where `""` was
  already treated as absent — recorded so the change is not discovered later as a surprise.
- **F3 (accepted, informational) — the ambient endpoint.** The verifier noted this
  environment has `OPENAI_BASE_URL`/`ANTHROPIC_BASE_URL` set, so a blank endpoint now
  resolves to the SDK's ambient value. It confirmed the candidate does **not** create a new
  ambient path: `base_url=None` already meant "use the provider's default" at the parent,
  an unconfigured workspace already resolved to `None`, and the parent's blank case sent a
  broken URL (`'%20%20%20/'`) that never reached the ambient value. The changed case is the
  blank-stored one, which is this slice's stated semantics.
- **F4 (accepted, out of scope) — the connection route's only client is dead.**
  `testLLMConnection` in `frontend/src/lib/settings-api.ts` has no importer, so the route
  this slice just fixed is reachable only by a direct API caller. Removing the dead helper
  belongs to slice 4 (the per-user LLM cleanup), not here.
- **Not verified:** the route probes were in-process with monkeypatched adapters (no ASGI
  stack, no network), and the write path was probed with a fake repository rather than
  against Postgres — the real repository stores the dataclass fields verbatim, but the DB
  round-trip was not exercised.

## Follow-ups (not part of this change)

- `testLLMConnection` (`frontend/src/lib/settings-api.ts`) is dead: no importer, and it is
  the only client of the connection-test route. Slice 4 territory.
- A blank `provider` name written through the API still resolves to a custom provider
  instead of Ollama (D3). Unreachable from the UI, which offers a select.
- The empty string is now stored as `None` for `base_url`/`api_key` (F2). Deliberate, and
  recorded so it is not read later as an unintended write-path change.
- `GET /users/me/settings` still round-trips a per-user `llm` slice with plaintext keys
  (slice 4).
- `ErrorDisplay` still renders `null` (slice 3).
- The blank-endpoint path could also be closed by making the column `NOT NULL`/`CHECK`, a
  schema-level guarantee rather than a code one. Out of scope here.
