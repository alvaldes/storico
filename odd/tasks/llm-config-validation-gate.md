# ODD Feature: llm-config-validation-gate

> **Status**: done — eight commits on `feat/llm-config-validation-gate` (`cc22a0c`..
> `5e60f42`), plus the evidence commit that carries this line (nine against `main`);
> nothing was pushed.
> Receipt-driven development is **off** in this clone, so no native review ran; one
> independent verification did, recorded below with its findings and their disposition.
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

- **Status**: done (commit `c4103ec`)
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

- **Status**: done (commit `3c9a323`)
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

- **Status**: done (commit `1feff25`)
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

- **Status**: done (commit `3babb08`)
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

- **Status**: done (commit `7b5821a`, corrected in `5e60f42`)
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

- **Status**: done (commit `6052224`)
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

- **Status**: done (one independent `gentle-ai-verify` run over `67b996a..6052224`,
  whose two findings are fixed in `5e60f42`; see the verification section below)
- **What**: run the repo gate on the candidate and record the outcome.
- **Commands**:
  - `cd backend && .venv/bin/pytest` and `.venv/bin/ruff check src tests` and
    `.venv/bin/ruff format --check src tests`
  - `cd frontend && node_modules/.bin/vitest run` and `node_modules/.bin/tsc --noEmit`
- **Acceptance**: every command passes, the counts are recorded, and any failure is
  reported as a blocker — never as done.
- **Depends on**: T-001, T-002, T-003, T-004, T-005, T-006

### T-008 — Close the feature

- **Status**: done (this document's commit)
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
| T-001 | `c4103ec` | `llm_config_readiness.py` with `READINESS_FIELDS`, `LLM_CONFIG_INCOMPLETE_CODE`, `REQUIRED_FIELDS_BY_PROVIDER`, `CUSTOM_PROVIDER_REQUIRED_FIELDS`, `required_fields_for`, `missing_llm_config_fields`, `llm_config_is_complete`. 28 unit cases in `tests/test_unit/test_llm_config_readiness.py`: **28 passed**. `ruff check` clean; `ruff format` reformatted the two new files, then `--check` clean. |
| T-002 | `3c9a323` | `GET /settings/llm/status` guarded by `get_workspace_for_user`, plus `LLMConfigStatusResponse` and the module docstring's admin-only exception. `tests/test_api/test_workspace_settings_llm_status.py`: **10 passed**, including the no-disclosure case and a 403 for a non-member. Neighbouring settings suites together: **86 passed**. `docs/api.md` updated. |
| T-003 | `1feff25` | The route resolves the provider first, asks `missing_llm_config_fields`, and answers `400` `{detail, error_code, provider, missing}` before creating anything. Red run against the pre-change route (restored from `HEAD`): **4 failed \| 2 passed** — the two that passed are the accepting cases, which is the witness that the gate does not over-block. Green after: **49 passed**. |
| T-004 | `3babb08` | `llm-config-readiness.ts` (mirror) + `llmConfigDraftSchema` and tightened `llmConfigSchema` bounds in `schemas/workspace.ts`. Full frontend suite **28 files / 319 passed**, `tsc --noEmit` exit 0. The mirror guard was mutation-tested in six directions (backend table member dropped, backend vocabulary renamed, backend `max_length` changed, backend refusal code changed, frontend row extended, frontend custom row changed): each failed exactly one case, and the restored file was green — with the file diffed against a backup to prove the restore. |
| T-005 | `7b5821a` | The editor parses the draft before the PUT, renders a red `FieldError` per offending field (only after a save attempt), an always-live summary of the missing fields, and one toast naming them; a complete config saves from the validated data. Eight new keys in both locales. New cases: **58 passed** in that file. Red run with the guard disabled (`if (false && !parsed.success)`): **4 of the 7 new cases failed** — exactly the four that assert the refusal. |
| T-006 | `6052224` | `getLLMConfigStatus`, the `StoryDetail` gate (disabled button, admin link, member sentence, fail-open on an unreadable status), `ExtractionErrorCode` gaining `config`, and the toast/`ErrorDisplay` copy branch. Full frontend suite **29 files / 337 passed**, `tsc` exit 0. Red run with `configIncomplete = false`: **2 failed** (the two blocked-state cases) while the three availability cases still passed. Two pre-existing `StoryDetail` cases broke mid-task when the new status mock was left unset — they are green again because the default now lives in the shared `resetStores()`. `taskStore.unit.test.ts` gained the categorization case (a file outside the surfaces this task named: the mapping is tested where the other codes are). |
| T-007 | `5e60f42` | Gate and independent verification, below. The verifier's candidate-caused finding (F1) and its pre-existing follow-up whose reachability this feature's own schema blessed (F2) are both fixed in `5e60f42`; the corrected candidate re-ran the whole gate green. |
| T-008 | this document | Status, evidence, the verification record and the dispositions, written after every command above ran. |

## Verification (RDD off — independent verification, not native review)

One `gentle-ai-verify` run over `67b996a..6052224`, read-only inside the repository, with
every mutation probe in a `/tmp` copy. It wrote its own probes rather than reading the
candidate's test assertions. Gate it observed: backend **585 passed, 1 skipped** (the
skip is the pre-existing Docker-dependent integration test), `ruff check` and
`ruff format --check` clean over 210 files; frontend **29 files / 337 passed**,
`tsc --noEmit` exit 0.

What it confirmed by driving real code, not by reading tests:

- **The two implementations of the rule agree over 576 generated cases, 0 mismatches**
  (9 provider names × 4³ values, including whitespace-only), tables, vocabulary, refusal
  code and the exact-match classification included.
- **The status route**: member `200`; non-member `403`; unknown workspace `404`;
  unauthenticated `401`; and neither the stored `api_key` nor the stored `base_url`
  appears in the serialized body. Its explicit regression check: as a member,
  `GET`/`PUT /settings/llm` still return `403`, and another workspace's status is `403` —
  adding one member-readable route did not loosen the module.
- **The hazard the gate closes is real**: driving the real background path with a missing
  key produced one `failed` extraction row and left the story at `failed_extraction`; the
  gate then produced `400`, **0** extraction rows, and a story whose status it first
  forced to `extracted` so "unchanged" had teeth.
- **The mirror guard fails on drift** across seven mutations of the Python files.
- **The editor gate**: incomplete drafts perform 0 PUTs and raise the toast; out-of-range
  and malformed values get their own copy after the attempt; the pre-attempt summary
  renders without painting fields red.
- **The action gate**: disabled button, correct admin link in both locales, fall-open on
  a rejected status request, an unknown field code dropped rather than rendered, and
  `LLM_CONFIG_INCOMPLETE` → `config` end-to-end through a real `fetch` 400 body.
- **i18n**: `en`/`es` key sets at 663/663 with zero drift; the new Spanish strings use
  neutral *tú*, no voseo.

### Findings and disposition

- **F1 (fixed in `5e60f42`) — candidate-caused, low.** The length mirror built a `Map`
  keyed by field name, so the **last** `max_length` declaration won. `api_key` and
  `base_url` are each declared twice (the request body and the model probe), and mutating
  only the request-body copy passed the guard — the copy that governs what the API
  accepts. The guard now collects every declaration and asserts each one, and a new case
  fails when the declared field set changes at all. Re-probed after the fix: mutating
  only line 16 (`api_key`) and only line 15 (`base_url`) each now fails exactly one case,
  and adding a new bounded field fails too.
- **F2 (fixed in `5e60f42`) — pre-existing passthrough that this change made incoherent.**
  A whitespace-only `base_url` was reachable from the editor (the new field rule trims
  before deciding, so it read the value as "empty") and reached the adapter as a URL of
  spaces (`'%20%20%20/'` for the OpenAI SDK). The save path now trims the endpoint, so a
  value the rule reads as absent is never stored; a case pins it and fails without the
  trim. The backend passthrough for a row written through the API is a follow-up.
- **F3 (accepted, not a defect) — a correction to my probe, not to the code.** I asked
  for "non-empty `missing` ⇒ `_build_llm_port` raises". That cannot hold: the port takes
  no `model` argument. The verifier measured the asymmetry — the rule is *stricter* than
  the port in 188 of 384 combinations, all of them the blank-`model` and whitespace
  cases, which is the safe direction — and probed the real counterpart instead (the
  route's own guard): **0 counterexamples over 384 rows** for "the route accepts ⇒ the
  port builds".

Not verified by the run: the Playwright suite (already recorded in this repo as not
runnable), any real network call to a provider (adapter probing stopped at
construction), and the origin of the one pre-existing pytest resource warning.

## Follow-ups (not part of this change)

- The dead per-user `settingsStore.llm` slice (and its `AppSettings.llm` schema) still
  duplicates the vocabulary and stores API keys; the live UI only reads `export`.
- `PUT /settings/llm` still measures the raw value for `max_length` while the provider
  registry measures the trimmed one (carried over from `custom-provider-free-form-name`).
- A whitespace-only `base_url` or `api_key` written through the API (not through the
  editor, which now trims the endpoint) is passed to the adapter verbatim. The route
  normalizes nothing; `_build_llm_port` only checks truthiness (F2).
- `docs/api.md` still describes the custom-provider name rule as a lowercase slug
  (`^[a-z0-9][a-z0-9._-]{0,49}$`), which `custom-provider-free-form-name` reversed. Same
  file, unrelated paragraph — left alone rather than bundled into this change.
- `frontend/src/i18n/en.json` and `es.json` carry pre-existing duplicate keys
  (`stories.create_error` ×2, `taskEditor.invalid_drop` ×2) that a JSON-aware linter
  flags. JSON keeps the last one, so nothing is broken today; the counts are unchanged
  by this feature.
- `StoryDetail.tsx` imports `ExtractionErrorInfo` without reading it — pre-existing, and
  reported by `tsc` as an unused-import hint.
- `ErrorDisplay` is still the placeholder that renders `null`, so the failed-extraction
  panel shows nothing; the toast is the only observable failure channel. The
  configuration branch added to its `friendlyMessage` prop is therefore correct but
  currently unobservable, which is why the test asserts the toast and not the panel.

## Outcome

A workspace's LLM configuration now has a declared completeness rule, and the three
surfaces that need it read the same one: the settings form refuses to persist a draft
that cannot extract and says which field is missing, the extraction route refuses before
it creates anything, and any member can ask whether the workspace is ready before
attempting the action. The late, dirty failure is gone — a missing cloud key or a custom
provider's endpoint no longer produces a pending extraction row and a story dragged into
`failed_extraction`.

The rule is declared twice, in two languages, and that is the change's main structural
risk. It is guarded in the two places this repository already accepts for hand-kept
mirrors: a node-environment test that reads the Python file and fails on drift, plus an
API test that pins enforcement independently of the table. The verification round is
what made the guard honest: it found that the length half of it let a duplicate
declaration hide a drift, and that finding is fixed and re-probed rather than merely
reported.

Two naming deviations from the plan, both deliberate: the frontend function is
`missingLLMConfigFields` (the plan said `describeLLMConfigGaps`) so its name mirrors
`missing_llm_config_fields` on the other side of the guard, and the classification lives
in `requiredFieldsFor` rather than inline. The mirror guard also covers the four
`max_length` declarations, which closes the unguarded-50 symptom the previous feature
recorded as a follow-up.

Nothing was pushed: the branch is local, and the delivery decision beyond that is
ordinary repository policy. RDD is off in this clone, so no native review ran — the
independent verification above is the review this candidate got.
