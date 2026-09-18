# ODD Feature: llm-config-validation-gate

> **Status**: in progress
> **Created**: 2026-06-30
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/llm-config-validation-gate`
> **Receipt-driven development**: off in this clone (no native review; independent
> verification is the review this candidate gets).

## Problem

Reported by the user:

> "Toda la config de LLM (proveedor, modelo,..., api key, url base) debe de validarse
> con zod pero ademas al hacer el save. Por que esta es una configuracion muy
> importante ya que no hay forma de hacer un extract si esta config esta mal. Así que
> vamos a realizar varios mensajes que informen al usuario, que aún falta elementos de
> esa configuración por definir y que por tanto es necesario que los haga para poder
> avanzar. Es importante que se muestren mensajes en rojo en el formulario y además que
> se muestren alertas tipo Toast. También hay que analizar para que al realizar una
> extracción o cualquier otra acción que requiera que ya esté configurada la
> configuración de los LLM, se le informe al usuario de que esta acción no se puede
> realizar, si no se concluye primeramente la configuración del modelo, proveedores y
> demás de la configuración del LLM."

Three defects, one root cause: **nothing in the product has a notion of "this workspace's
LLM configuration is complete"**, so the rule only exists as scattered failure branches
that fire after the user has already committed to an action.

1. **The settings form validates nothing.** `LLMConfigEditor.handleLLMSave` posts
   `model || undefined` and lets the API answer. `llmConfigSchema`
   (`frontend/src/schemas/workspace.ts:25`) is dead code — no runtime caller, already
   recorded as a follow-up in `custom-provider-free-form-name`. The admin gets a generic
   toast on rejection and no field-level red.
2. **An incomplete config is persisted silently.** `PUT /settings/llm` accepts a partial
   body, and the read path (`resolve_llm_config`) fills gaps with defaults (`ollama_host`
   for Ollama, `None` for a cloud provider's `base_url`). Nothing ever says "this will not
   extract".
3. **The dependent action fails late and dirtily.** `POST .../extract/` rejects a missing
   `model` with a `400` *before* creating the record, but a missing `api_key`
   (openai/anthropic/gemini) or `base_url` (custom provider) surfaces later as an
   `LLMError` **inside the background task** (`extraction_task.py:201`): a pending
   extraction row is already created, the user story is dragged into
   `failed_extraction`, and the user sees a generic extraction-failure toast. A
   non-admin member — the common case — cannot read the config at all (`GET /settings/llm`
   is `require_admin`), so they cannot be warned before the fact.

## Decisions (user-approved 2026-06-30)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Surfaces in scope | **Workspace Settings only** (`LLMConfigEditor`). Onboarding step 3 keeps saving a bare provider; the legacy per-user `settingsStore.llm` (no live UI) is untouched. |
| D2 | Member visibility | **New member-readable status endpoint** returning `{configured, provider, missing[]}`. A member must be able to learn the config is incomplete *before* attempting extraction. |
| D3 | Backend authority | **Fail fast.** The extraction route validates the resolved config before creating the pending record and answers `400` with a structured `error_code` and the missing fields. No more pending-then-failed for a config that was never usable. |
| D4 | Save semantics | **Block the save.** An invalid draft performs no `PUT`; the previously saved config is untouched. Red per-field messages + a missing-items summary + a toast. |
| D5 | Missing-field vocabulary | Machine codes, not prose: `model`, `api_key`, `base_url`. The API returns codes; each client maps them to its own translated copy. |
| D6 | Completeness rule per provider family | `ollama` → `model`. `openai`/`anthropic`/`gemini` → `model` + `api_key`. Any other name (custom, OpenAI-compatible) → `model` + `base_url`; `api_key` stays optional. This is exactly what `_build_llm_port` already enforces at runtime, extracted into one declared rule. |

## Non-goals

- No change to the provider-name rule, the custom-provider registry, or its endpoints.
- No new UI for onboarding step 3, and no change to its partial `{provider}` save.
- No removal of the dead `settingsStore.llm` slice (recorded as a follow-up instead).
- No backend rejection of a partial `PUT /settings/llm` body: saving step by step stays
  legal, and it is the *extraction* that refuses to start on an incomplete config.
- No connection test, no model-probe change, no validation of the key against the
  provider (a well-formed but wrong key is not detectable offline).
- No `AppSettings`/user-preferences validation.

## Established facts (verified in code)

- Form surface: `frontend/src/components/react/LLMConfigEditor.tsx`; save path
  `upsertLLMConfig` → `lib/llm-config-api.ts` → `PUT /api/v1/workspaces/{id}/settings/llm`.
- `llmConfigSchema` / `LLMConfigParams` (`frontend/src/schemas/workspace.ts:25`) is used
  **as a type only** by `lib/llm-config-api.ts`; `OnboardingModal` calls
  `upsertLLMConfig(wsId, { provider })`, so the payload schema must stay permissive about
  absent fields.
- `FieldError` already exists (`frontend/src/components/ui/field.tsx`, `text-destructive`)
  and `Toaster` is mounted in `DashboardShell.tsx:86`.
- Backend rule today: `_build_llm_port`
  (`backend/src/storico/infrastructure/tasks/extraction_task.py:201`) raises `LLMError`
  for a missing cloud `api_key` or a custom provider's `base_url`; `resolve_llm_config`
  (`backend/src/storico/api/routes/workspace_settings.py:76`) falls back to
  `settings.ollama_host` for Ollama only.
- `GET/PUT /settings/llm` depend on `require_admin`; `get_workspace_for_user`
  (`backend/src/storico/api/dependencies.py:171`) is the member-level dependency and each
  route opts in individually, so a member-readable route can live beside them.
- Structured API errors use `detail` as an object carrying a nested `detail` string plus
  `error_code` (`backend/src/storico/api/routes/tasks.py:275`), and `ApiRequestError`
  already lifts `error_code` off that object (`frontend/src/lib/api.ts:76`).
- Frontend test convention for a rule declared in both languages is a node-environment
  guard that reads the Python file (`frontend/src/lib/__tests__/provider-name-mirror.test.ts`).
- i18n: `frontend/src/i18n/__tests__/neutral-spanish.test.ts` enforces neutral Spanish and
  `en.json`/`es.json` key parity, so every new key lands in both files.
- Gates: `cd backend && .venv/bin/pytest` and `.venv/bin/ruff check src tests`;
  `cd frontend && node_modules/.bin/vitest run` and `node_modules/.bin/tsc --noEmit`.

## Tasks

### T-001 — Backend: the completeness rule, declared once

- **Status**: pending
- **Files to modify**: `backend/src/storico/domain/services/llm_config_readiness.py` (new),
  `backend/tests/test_unit/test_llm_config_readiness.py` (new)
- **What**: a pure domain module holding `REQUIRED_FIELDS_BY_PROVIDER`,
  `CUSTOM_PROVIDER_REQUIRED_FIELDS` (D5/D6 spelling: `model`, `api_key`, `base_url`),
  `provider_required_fields(provider)` and `missing_llm_config_fields(...)` returning the
  missing codes in a stable order. No I/O, no settings import.
- **Acceptance**: `.venv/bin/pytest tests/test_unit/test_llm_config_readiness.py`, `ruff`
  clean. Cases: each known provider; a custom name; `api_key` optional for a custom
  provider; whitespace-only values count as missing; an unknown name never raises.
- **Allowed edit surfaces**: `backend/src/storico/domain/services/llm_config_readiness.py`,
  `backend/tests/test_unit/test_llm_config_readiness.py`

### T-002 — Backend: member-readable config status

- **Status**: pending
- **Files to modify**: `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_llm_status.py` (new), `docs/api.md`
- **What**: `GET /api/v1/workspaces/{workspace_id}/settings/llm/status` guarded by
  `get_workspace_for_user` (not `require_admin`), answering
  `{configured, provider, missing[]}` built from `resolve_llm_config` +
  `missing_llm_config_fields`. The route never echoes the `api_key` or `base_url`; it
  reports only the codes. Update the module docstring, whose "all routes require admin"
  claim stops being true here, and say why this one is the exception.
- **Acceptance**: `.venv/bin/pytest tests/test_api/test_workspace_settings_llm_status.py`,
  `ruff` clean. Cases: member gets `200`; no config row → `configured=false`,
  `missing=["model"]`; openai with key+model → `configured=true`; custom without base URL
  → `missing` contains `base_url`; a non-member gets `403`; the response carries no
  credential.
- **Depends on**: T-001
- **Allowed edit surfaces**: `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_llm_status.py`, `docs/api.md`

### T-003 — Backend: extraction refuses to start on an incomplete config

- **Status**: pending
- **Files to modify**: `backend/src/storico/api/routes/extraction.py`,
  `backend/tests/test_api/test_extraction.py`, `docs/api.md`
- **What**: before creating the pending extraction, validate the resolved selection with
  `missing_llm_config_fields` and, when non-empty, raise `HTTPException(400)` with
  `detail={"detail": ..., "error_code": "LLM_CONFIG_INCOMPLETE", "missing": [...],
  "provider": ...}` — the structured shape the frontend already parses. The existing
  "no model configured" `400` folds into this rule; the story stays in its current status
  and no extraction row is created. `_build_llm_port` keeps its checks as the last line of
  defence.
- **Acceptance**: `.venv/bin/pytest tests/test_api/test_extraction.py`, `ruff` clean.
  Cases: zero stories/extractions created on refusal; `LLM_CONFIG_INCOMPLETE` plus the
  exact `missing` list for a missing model, a missing cloud key, and a missing custom base
  URL; `202` for a complete Ollama config (model only) and for a complete custom provider.
- **Depends on**: T-001
- **Allowed edit surfaces**: `backend/src/storico/api/routes/extraction.py`,
  `backend/tests/test_api/test_extraction.py`, `docs/api.md`

### T-004 — Frontend: readiness mirror and the zod schemas that consume it

- **Status**: pending
- **Files to modify**: `frontend/src/lib/llm-config-readiness.ts` (new),
  `frontend/src/schemas/workspace.ts`, `frontend/src/schemas/index.ts`,
  `frontend/src/lib/__tests__/llm-config-readiness.test.ts` (new),
  `frontend/src/lib/__tests__/llm-config-readiness-mirror.test.ts` (new),
  `frontend/src/schemas/__tests__/workspace.test.ts`
- **What**:
  - `describeLLMConfigGaps(config)` returning `ReadinessField[]` (`model` | `apiKey` |
    `baseUrl`), mirroring the backend table, plus `isLLMConfigComplete`.
  - A node-environment guard, in the style of `provider-name-mirror.test.ts`, that reads
    `backend/src/storico/domain/services/llm_config_readiness.py` and fails when the two
    declared tables drift.
  - `llmConfigSchema` keeps its job as the PUT payload contract (permissive about absent
    fields, so `OnboardingModal`'s `{ provider }` still type-checks) but gains the
    field-level bounds: `provider` 1–50, `model` ≤100 and non-empty when present,
    `temperature` 0–2, `maxTokens` integer 256–8192, `baseUrl` ≤500 and an absolute
    `http`/`https` URL when present, `apiKey` ≤500.
  - A new `llmConfigDraftSchema` = those fields required-to-be-present as the form holds
    them, plus a `superRefine` that raises one issue per missing field (path = the field,
    message = the code) using `describeLLMConfigGaps`.
  - Both exported and typed from `schemas/index.ts`.
- **Acceptance**: `node_modules/.bin/vitest run src/lib src/schemas` and
  `node_modules/.bin/tsc --noEmit` pass. The mirror guard fails when either table is
  mutated (mutation-tested in the task's red run).
- **Allowed edit surfaces**: `frontend/src/lib/llm-config-readiness.ts`,
  `frontend/src/schemas/workspace.ts`, `frontend/src/schemas/index.ts`,
  `frontend/src/lib/__tests__/llm-config-readiness.test.ts`,
  `frontend/src/lib/__tests__/llm-config-readiness-mirror.test.ts`,
  `frontend/src/schemas/__tests__/workspace.test.ts`

### T-005 — Frontend: the editor validates, shows red and refuses to save

- **Status**: pending
- **Files to modify**: `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`
- **What**: parse the draft with `llmConfigDraftSchema` on save; when it fails, perform no
  `PUT`, render a red `FieldError` under each offending field, render a summary of the
  missing items above the save button, and raise one `toast.error` naming them (D4). A
  field's error clears as the user fixes that field. A complete config saves exactly as
  today. When the *loaded* config is already incomplete, the same summary is visible
  before any save attempt, so the failure is never a surprise. All copy in both locales,
  neutral Spanish.
- **Acceptance**: `node_modules/.bin/vitest run` and `tsc --noEmit` pass; new cases assert
  that an incomplete draft performs no `upsertLLMConfig` call, that each missing field has
  its own red message, that the toast fires, and that fixing the field clears it.
- **Depends on**: T-004
- **Allowed edit surfaces**: `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`

### T-006 — Frontend: the extraction action is gated

- **Status**: pending
- **Files to modify**: `frontend/src/lib/llm-config-api.ts`,
  `frontend/src/components/react/StoryDetail.tsx`, `frontend/src/stores/taskStore.ts`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/__tests__/StoryDetail.test.tsx`
- **What**:
  - `getLLMConfigStatus(wsId)` in `lib/llm-config-api.ts` (D2).
  - `StoryDetail` asks for the status once per workspace mount and, when the config is
    incomplete, disables the extract button and shows the reason next to it: an admin gets
    a link to Workspace Settings, a member is told to ask an admin (the role is already on
    `currentWorkspace`).
  - `ExtractionErrorCode` gains `config`; `categorizeExtractionError` maps a `400` with
    `error_code === 'LLM_CONFIG_INCOMPLETE'` to it, so the toast effect in `StoryDetail`
    reports the same message with the same link when the backend refuses (defence in
    depth: the button gate is an optimisation, the API is the authority).
  - New keys in both locales, neutral Spanish.
- **Acceptance**: `node_modules/.bin/vitest run` and `tsc --noEmit` pass; cases cover the
  disabled button with the admin link, the member copy, an enabled button on a complete
  config, and a `LLM_CONFIG_INCOMPLETE` rejection producing the config toast rather than a
  generic extraction failure.
- **Depends on**: T-002, T-003
- **Allowed edit surfaces**: `frontend/src/lib/llm-config-api.ts`,
  `frontend/src/components/react/StoryDetail.tsx`, `frontend/src/stores/taskStore.ts`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/__tests__/StoryDetail.test.tsx`

### T-007 — Verification gate

- **Status**: pending
- **What**: run the repo gate on the candidate and record the outcome.
- **Commands**:
  - `cd backend && .venv/bin/pytest` and `.venv/bin/ruff check src tests` and
    `.venv/bin/ruff format --check src tests`
  - `cd frontend && node_modules/.bin/vitest run` and `node_modules/.bin/tsc --noEmit`
- **Acceptance**: every command passes, the counts are recorded, and any failure is
  reported as a blocker — never as done.
- **Depends on**: T-001, T-002, T-003, T-004, T-005, T-006

### T-008 — Close the feature

- **Status**: pending
- **What**: flip the status line, write the evidence log with real commit identities and
  observed output, and record the follow-ups this change creates.
- **Depends on**: T-007

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| The completeness rule is declared twice (Python + TypeScript) | One side drifts and the UI gates on a different rule than the API enforces | One declared table per side plus a node-environment mirror guard that reads the Python file, the `provider-name-mirror.test.ts` pattern; the API test pins enforcement independently |
| `maxTokens`/`temperature` bounds reject a value saved through the API before this change | An admin opening Settings sees a field error on an untouched form | The bounds are exactly the control's existing `min`/`max`, and the error is visible and fixable rather than silent; recorded as a follow-up if a real row hits it |
| A member-readable status route leaks configuration detail | Credential or endpoint disclosure to a non-admin | The response carries only `configured`, `provider` and field *codes*; a test asserts the serialized body contains neither the key nor the base URL |
| Blocking the save frustrates a legitimate step-by-step configuration | An admin who cannot save a partial config loses work | The draft is local state, so nothing is lost by staying on the page; D4 is the user's explicit choice, and D6 keeps every genuinely optional field optional |
| `LLM_CONFIG_INCOMPLETE` keeps the generic `statusText` as `Error.message` | The toast reads "Bad Request" | `categorizeExtractionError` + the toast effect map the code to translated copy; the mapping is a tested case, not an assumption |
| Onboarding still saves a bare `{ provider }` | The first extraction after onboarding is refused | By design (D1): the gate names exactly what is missing and links the admin to the fix |

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
| T-006 | | |
| T-007 | | |
| T-008 | | |

## Follow-ups (not part of this change)

- The dead per-user `settingsStore.llm` slice (and its `AppSettings.llm` schema) still
  duplicates the vocabulary and stores API keys; the live UI only reads `export`.
- `llmConfigSchema.provider` mirrors the 50-character bound by hand, unguarded.
- `PUT /settings/llm` still measures the raw value for `max_length` while the provider
  registry measures the trimmed one (carried over from `custom-provider-free-form-name`).
