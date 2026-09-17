# ODD Feature: custom-provider-model-discovery

> **Status**: done — landed on `main` as six commits (`f195381`..`3905844`); the feature branch was fast-forwarded and deleted
> **Created**: 2026-09-17
> **Workflow**: Organic Driven Development (ODD)

## Problem

A workspace can be configured with a provider name outside the four first-class
providers (`ollama`, `openai`, `anthropic`, `gemini`) — e.g. `deepseek`, `groq`,
`together`. Two independent defects make that configuration useless:

1. **No model discovery.** `list_available_models` in
   `backend/src/storico/api/routes/workspace_settings.py` handles only the four
   known providers and falls through to `return []` for anything else. The
   frontend therefore never receives a model list for a custom provider and the
   user has no suggestions and no "refresh" affordance.

2. **Extraction silently uses Ollama.** `_run_extraction` in
   `backend/src/storico/infrastructure/tasks/extraction_task.py` branches on
   `gemini` / `openai` / `anthropic` and sends **every other provider** to
   `OllamaAdapter(base_url=base_url or settings.ollama_host)`. A workspace
   configured as `deepseek` with a valid API key and base URL hits a local Ollama
   host instead of the configured endpoint. The custom provider is decorative.

## Decisions (user-approved 2026-09-17)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Scope | Model discovery **and** extraction routing. Fixing only discovery would leave the feature inert. |
| D2 | URL probing | Try `{base}/models` first; if it fails and the base does not already end in `/v1`, retry `{base}/v1/models`. Covers DeepSeek (`https://api.deepseek.com`) and Groq (`https://api.groq.com/openai/v1`) as documented, and tolerates a version-less root. |
| D3 | Custom-provider model field | Always free text, with the discovered list offered as suggestions. Never selection-only: the real model id may be absent from the list, or the endpoint may not expose `/models` at all. |
| D4 | API key for discovery | Optional. Send `Authorization: Bearer <key>` only when a key is stored, so local OpenAI-compatible servers (LM Studio, vLLM, llama.cpp) work unauthenticated. |

## Non-goals

- No new first-class provider. `deepseek`/`groq` stay custom names; the code path
  is "OpenAI-compatible", not "know about DeepSeek".
- No change to how `ollama`, `anthropic` or `gemini` discovery works.
- No provider-specific model allow-lists or capability filtering.
- No change to the workspace LLM config schema or its migration state.

## Established facts (verified in code)

- `KNOWN_PROVIDERS = ['ollama', 'openai', 'anthropic', 'gemini']` in
  `frontend/src/components/react/LLMConfigEditor.tsx:38`; `isCustomProvider` is
  derived from membership.
- `provider` is a free-text `str | None = Field(None, max_length=50)` in
  `backend/src/storico/api/schemas/workspace_llm_config.py`, so custom names
  already persist. No schema change needed.
- `api_key` and `base_url` already persist on the workspace LLM config row.
- The extraction route resolves `provider` from the workspace config and defaults
  to `"ollama"` (`backend/src/storico/api/routes/extraction.py:188-190`), so an
  explicit `provider == "ollama"` branch is safe and the unknown-provider branch
  can mean "OpenAI-compatible".
- `OpenAIAdapter` already accepts `base_url` (`openai_adapter.py:26-41`).
- Frontend already auto-fetches models on **every** `llmConfig.provider` change
  (`LLMConfigEditor.tsx` `useEffect`). In custom mode the provider field is a free
  text input whose `onChange` writes `provider` on each keystroke, so typing
  `deepseek` currently fires eight backend requests, each probing an external
  endpoint. Must be fixed as part of T3.
- In custom mode the Base URL placeholder renders `https://api.anthropic.com`
  (the ternary only special-cases `openai`). Must be fixed as part of T3.

## Tasks

### T-001 — Backend: OpenAI-compatible model discovery for custom providers

- **Status**: done (commit `90b234c`)
- **Files to modify**: `backend/src/storico/api/routes/workspace_settings.py`
- **Files to create**: `backend/tests/test_api/test_workspace_settings_models.py`
- **What**:
  - Add a reusable `fetch_openai_compatible_models(base_url, api_key)` that probes
    candidate URLs in order per D2 and returns `list[ModelInfo]` from the first
    candidate that yields a parseable `data[]` payload.
  - Send the `Authorization: Bearer` header only when `api_key` is truthy (D4).
  - Route the custom/unknown branch of `list_available_models` through it,
    requiring a `base_url` (a custom provider without one has no endpoint to
    probe; return `[]` rather than guessing).
  - Keep `openai` behaviour intact: no `base_url` means the OpenAI default
    `https://api.openai.com/v1/models`.
- **Acceptance**: tests cover — probe order, `/v1` suffix not duplicated, missing
  key still probes, `base_url` absent yields `[]`, 404 on first candidate falls
  through to the second, both candidates failing surfaces the existing 502.
- **Allowed edit surfaces**: `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_models.py`

### T-002 — Backend: route custom providers to the OpenAI-compatible adapter

- **Status**: done (commit `9b6ab1c`)
- **Files to modify**: `backend/src/storico/infrastructure/tasks/extraction_task.py`
- **Files to create**: `backend/tests/test_api/test_extraction_provider_routing.py`
- **What**:
  - Restructure the adapter selection so `ollama` is matched explicitly and an
    unknown/custom provider builds `OpenAIAdapter(api_key=..., base_url=...)`.
  - Preserve the existing `LLMError` messages for `gemini`/`openai`/`anthropic`
    when their key is missing.
  - A custom provider without `base_url` must raise a clear `LLMError` naming the
    missing Base URL instead of silently reaching Ollama.
  - `provider` default stays `"ollama"`, so an unset provider is unaffected.
- **Acceptance**: tests assert the adapter type and constructor kwargs selected for
  `ollama`, each known provider, and a custom provider; plus the missing-base-url
  error path.
- **Depends on**: nothing (independent of T-001, but must not be written in parallel).
- **Allowed edit surfaces**: `backend/src/storico/infrastructure/tasks/extraction_task.py`,
  `backend/tests/test_api/test_extraction_provider_routing.py`

### T-003 — Frontend: custom-provider model discovery UX

- **Status**: done (commit `5a9e395`)
- **Files to modify**: `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`
- **What**:
  - In custom mode keep the model field an always-editable text input per D3, and
    surface `availableModels` as suggestions for it.
  - Add a refresh button in custom mode, enabled without an API key per D4.
  - Stop the per-keystroke fetch storm: debounce the custom provider name or only
    fetch on an explicit action. A user typing a provider name must not fire one
    external probe per character.
  - Fix the custom-mode Base URL placeholder to an OpenAI-compatible example
    (`https://api.openai.com/v1`) instead of `https://api.anthropic.com`.
  - New i18n keys in **both** `en.json` and `es.json`, same key set. Spanish copy
    is neutral international Spanish (tú register), never voseo — enforced by
    `frontend/src/i18n/__tests__/neutral-spanish.test.ts`.
- **Acceptance**: `pnpm exec tsc --noEmit` and `pnpm vitest run` pass; typing a
  provider name does not issue one request per keystroke; the custom model field
  always accepts typed input.
- **Allowed edit surfaces**: `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`

### T-004 — Verification gate

- **Status**: done
- **What**: run the full CI-equivalent gate and record the outcome.
- **Commands**:
  - `cd backend && .venv/bin/ruff check src tests`
  - `cd backend && .venv/bin/ruff format --check src tests`
  - `cd backend && .venv/bin/pytest -q`
  - `cd frontend && pnpm exec tsc --noEmit`
  - `cd frontend && pnpm vitest run`
  - `cd frontend && pnpm run build`
- **Acceptance**: every command passes; any failure is reported as a blocker, never
  as a done task.
- **Depends on**: T-001, T-002, T-003

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Naive `{base}/models` join 404s on a version-less root | Discovery silently returns nothing | D2 probe order; covered by `90b234c` |
| Keystroke-driven probes hammer an external provider | Rate limits, latency, noisy logs | T-003 debounce/explicit action |
| Free-text commit in the base-ui Combobox reverts on blur | User loses the typed model id | Prefer a plain `Input` with native `<datalist>` suggestions in custom mode; if a richer popover is used it must commit typed text on blur and be verified |
| An existing workspace whose provider name is not one of the four known ones loses its implicit Ollama fallback | A previously "working" (but wrong-endpoint) extraction now fails loudly | Accepted as the point of D1: calling Ollama when the workspace asked for `deepseek` is the defect. The failure names the missing Base URL |
| The installed `openai==3.14.0` rejects an empty key and reads an ambient `OPENAI_API_KEY` when passed `None` | An unauthenticated custom gateway could not be called, or would silently borrow an environment credential | Non-secret `_CUSTOM_PROVIDER_PLACEHOLDER_KEY` constant; a stored key always wins; covered by `9b6ab1c` |
| Extra `/v1` appended to a base that already has it | 404 on the second probe | Guarded on the `/v1` suffix; covered by `90b234c` |

## Evidence log

_(each completed task records its commit identity here)_

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `90b234c` | `fetch_openai_compatible_models` probes `{base}/models` then `{base}/v1/models` (guarded against a doubled `/v1`), key optional, first HTTP 200 carrying a `data` list wins, otherwise the last `httpx.HTTPError` propagates to the existing 502 mapping. `fetch_openai_models` delegates. 16 new tests. Verified: focused suite 16 passed, `ruff check` clean, `ruff format --check` clean, full backend suite 444 passed / 1 skipped. |
| T-002 | `9b6ab1c` | Adapter selection extracted from `_run_extraction` into the pure `_build_llm_port`; `ollama` is an explicit branch, unknown names route to `OpenAIAdapter`, and a custom provider without a base URL raises `LLMError` instead of reaching Ollama. Unauthenticated custom gateways get the `no-key-required` placeholder after `openai==3.14.0` was observed to reject `""` and to read an ambient `OPENAI_API_KEY` when passed `None`. 16 new tests. Verified: focused suite 16 passed, `ruff check` clean, `ruff format --check` clean, full backend suite 460 passed / 1 skipped, and `AsyncOpenAI(api_key="no-key-required", base_url=...)` constructs under 3.14.0. |
| T-003 | `5a9e395` | Custom mode no longer auto-probes (the provider field is free text, so a probe per keystroke reached the user's own provider) and the field resets moved to the two mode switches. The custom model field stays free text and gains the discovered ids as native `<datalist>` suggestions; the refresh button renders in custom mode and is enabled without a key; the hint chain reports a failed probe, then an empty list, then the typing hint, all behind a settled-probe flag. Custom Base URL / API Key placeholders no longer show Anthropic's. `llmCustomModelDesc` was dropped as newly dead. 10 new tests. |
| T-004 | — | Independent verification of the final tree. `ruff check`, `ruff format --check`, `pytest -q` (460 passed / 1 skipped), `tsc --noEmit`, `vitest run` (199 passed), `pnpm run build` — all green, working tree clean before and after. The single skip is the long-standing testcontainers/Docker one. Three build warnings and one pytest `RuntimeWarning` are all reproduced from byte-identical files, so none is candidate-caused. |

## Outcome

All four tasks are complete and independently verified. Total diff against `f195381`: 9 files, 1080 insertions, 98 deletions — above the 400-line review threshold, so this candidate wants to be reviewed as chained slices rather than one review.
