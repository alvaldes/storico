# ODD Feature: normalize-blank-llm-fields

> **Status**: in progress
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

- **Status**: pending
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

- **Status**: pending
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

- **Status**: pending
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
| T-001 | | |
| T-002 | | |
| T-003 | | |
| T-004 | | |
| T-005 | | |

## Follow-ups (not part of this change)

- A blank `provider` name written through the API still resolves to a custom provider
  instead of Ollama (D3). Unreachable from the UI, which offers a select.
- `GET /users/me/settings` still round-trips a per-user `llm` slice with plaintext keys
  (slice 4).
- `ErrorDisplay` still renders `null` (slice 3).
- The blank-endpoint path could also be closed by making the column `NOT NULL`/`CHECK`, a
  schema-level guarantee rather than a code one. Out of scope here.
