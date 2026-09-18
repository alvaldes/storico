# ODD Feature: llm-model-probe-selection

> **Status**: done — T-001..T-006 complete, independently verified
> **Created**: 2026-09-18
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/workspace-custom-providers`

## Problem

Reported symptom: selecting a provider in Workspace Settings does not load that
provider's models; the request fails with `502 Bad Gateway`.

```
GET http://localhost:4321/api/v1/workspaces/019f9114-…/settings/llm/models
[HTTP/1.1 502 Bad Gateway 3345ms]
```

### Root cause (reproduced, not inferred)

`list_available_models` (`backend/src/storico/api/routes/workspace_settings.py:474`)
reads **only the persisted workspace config** (`config_repo.get(workspace.id)`),
while the frontend calls it with the workspace id and nothing else
(`frontend/src/lib/llm-config-api.ts:19`). The provider the user just picked in the
select never reaches the probe.

For workspace `019f9114-0a75-7be1-8649-69e8e6def0fe` the persisted row carries
`provider = 'NaN'`, a name outside the four first-class providers, with
`base_url = 'http://localhost:11434'`. The probe therefore fell through to the
OpenAI-compatible branch and called `http://localhost:11434/models`, which is not
listening. Reproduced against the running API with a real admin JWT:

```
HTTP 502 {"detail":"Failed to fetch models from NaN: All connection attempts failed"}
elapsed 4.3s
```

Because `ollama`, `openai`, `anthropic`, `gemini` all reach the saved-config
lookup first and every unknown name shares the final OpenAI-compatible branch,
**every** provider in the select answers 502 for this workspace. The reported
"gemini" selection is the instance, not the class.

### Where `NaN` came from (out-of-band data)

`custom_providers` holds a row `name = 'NaN'` for that workspace (created
2026‑09‑17 19:11 ‑0600), and the config's `provider` is that same string. The API
cannot produce it: `CustomProviderRequest` normalises to lowercase
(`normalize_provider_name`, `backend/src/storico/api/schemas/custom_provider.py:48`),
so `'NaN'` becomes `'nan'`; and the stored bytes are `4e614e` (uppercase). Verified
directly:

```
'NaN' -> 'nan'
'Gemini' -> 'gemini'
```

So the row entered the database outside the application. The application fix in
this feature removes the *coupling* that made that row lethal; the row itself is
removed by T-004.

### Secondary defect

`handleLLMSave` (`LLMConfigEditor.tsx`) persists the config and never re-probes, so
even after saving a correct provider the list stays empty until the user finds the
refresh button.

### Latent defect the fix made reachable

`resolve_llm_config` returned `settings.ollama_host` as the resolved `base_url` for
**every** provider. The settings form loads that response into its fields and posts
them back as the pending selection, so once the probe carried the form's values a
cloud provider reached it with `http://localhost:11434` as its endpoint. Measured
against the running API before the fix:

| Pending selection | Result |
|---|---|
| `{gemini, http://localhost:11434, <valid key>}` | 200 — Gemini ignores `base_url` |
| `{openai, http://localhost:11434, <valid key>}` | **502** `Failed to fetch models from openai: All connection attempts failed` |

`GET /settings/llm` for a `gemini` workspace whose stored `base_url` is `NULL`
returned `"base_url": "http://localhost:11434"` — a fictional endpoint for that
provider, and one the user could have persisted by pressing Save. This is fixed in
the same feature (T-005) because shipping the probe without it would have traded one
wrong-endpoint bug for another.

## Decisions (user-approved 2026-09-18)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Scope | Root cause **and** data cleanup. The phantom row is removed as well, so the immediate symptom disappears with the code fix. |
| D2 | Probe inputs | The request carries the **pending** selection from the form (`provider`, `base_url`, `api_key`). The user sees the chosen provider's models without saving first. |
| D3 | Transport | `POST` with an optional JSON body, mirroring the existing `POST /api/v1/llm/test` (`backend/src/storico/api/routes/settings.py`) which already carries pending credentials. A query string would write an API key into access logs; a body does not. |
| D4 | Merge rule | A body that names a provider describes the probe **entirely**. A key or base URL omitted from the body is *missing* for that probe and is never borrowed from the saved row — borrowing would send one provider's credential to another provider's endpoint. An absent or empty body keeps today's behaviour: probe the saved config. |

## Non-goals

- No debounce/typing behaviour on the credential fields. The previous feature
  (`custom-provider-model-discovery`, T-003) deliberately chose an explicit refresh
  action for custom mode; this feature keeps that decision and only changes *which*
  provider the probe describes.
- No new first-class provider and no change to how each provider's list is fetched.
- No change to the workspace LLM config schema, its migration state, or the
  custom-provider registry API.
- No validation that the saved `provider` is present in the workspace registry. A
  name configured before the registry existed remains legitimate; a name outside
  the registry still probes its configured endpoint as an OpenAI-compatible one.

## Established facts (verified)

- `fetchAvailableModels` is the only consumer of the endpoint in the repo; no other
  frontend module, script or doc calls it (`grep` over `frontend/`, `backend/`).
- `docs/api.md:91` documents the endpoint as `GET`.
- The stored Gemini API key for the reported workspace is **valid**: a direct call
  to `https://generativelanguage.googleapis.com/v1beta/models` with it returns 200
  and includes `gemini-2.5-flash`. The Gemini adapter and the Gemini branch of the
  probe are not broken.
- A custom provider that loses its base URL is already an error case in extraction
  (`_build_llm_port` raises `LLMError`), so a workspace in this state is broken for
  extraction too — not only for discovery.
- The frontend has no ESLint configuration, so `react-hooks/exhaustive-deps` is not
  enforced; effects are still written with complete dependency lists.
- Baselines before the first write: backend `513 passed, 1 skipped`; frontend
  `24 files / 240 tests`; `ruff check` and `ruff format --check` clean.

## Tasks

### T-001 — Backend: let the probe describe the pending selection

- **Status**: pending
- **Files to modify**:
  `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_models.py`
- **What**:
  - Add a `LLMModelProbeRequest` body schema (`provider`, `base_url`, `api_key`,
    all optional, `extra="forbid"`).
  - Replace `@router.get("/llm/models")` with `@router.post("/llm/models")` taking
    that body as an optional parameter.
  - Extract the per-provider dispatch into a pure
    `_probe_models(provider, base_url, api_key)` so the routing rule is testable
    without HTTP, and keep the existing `httpx.HTTPError` → 502 mapping naming the
    provider.
  - Resolve the probe inputs per D4 and keep the saved-config branch for an absent
    or empty body.
- **Acceptance**: tests cover — an empty/absent body probes the saved config
  (existing cases retargeted to POST); a body naming a provider probes the body's
  endpoint and key while the saved row is ignored; a body naming a provider without
  a key returns `[]` and **never** sends the saved key; a pending Gemini provider
  reaches the Gemini endpoint; the 502 message still names the provider.
- **Allowed edit surfaces**: `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_models.py`

### T-002 — Frontend: probe the selection in the form, and re-probe after a save

- **Status**: pending
- **Files to modify**:
  `frontend/src/lib/llm-config-api.ts`,
  `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`
- **What**:
  - `fetchAvailableModels(wsId, probe?)` sends `POST` with the pending selection
    when one is given.
  - A single `canProbe` predicate replaces `refreshModelsNeedsApiKey`: `ollama`
    always, a known cloud provider with a non-empty key, a custom provider with a
    non-empty base URL.
  - The auto-probe effect probes the **form's** selection, debounced so a credential
    typed one character at a time does not reach the provider once per keystroke,
    and no longer skips custom providers (the reason for that skip was the very
    coupling this feature removes).
  - The model list is cleared when the provider changes, so one provider's list is
    never shown under another provider's name.
  - A successful save re-probes, so the list reconciles with what was persisted.
  - New i18n key `llmModelsNoBaseUrl` in both locales (the disabled refresh button
    for a custom provider without a base URL must not say "add your API key").
- **Acceptance**: `tsc --noEmit` and `vitest run` pass; the probe is called with the
  pending selection; a custom provider saved with a complete endpoint probes without
  the refresh button; a provider change clears the previous list; a successful save
  re-probes; typing a key does not issue one request per keystroke.
- **Allowed edit surfaces**: `frontend/src/lib/llm-config-api.ts`,
  `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`
- **Depends on**: T-001

### T-003 — Docs: the endpoint contract in `docs/api.md`

- **Status**: pending
- **Files to modify**: `docs/api.md`
- **What**: the model-list row becomes `POST`, its body is documented, and the
  pending-selection rule (D4) is stated.
- **Allowed edit surfaces**: `docs/api.md`
- **Depends on**: T-001

### T-004 — Data cleanup for the reported workspace

- **Status**: pending (operational step, no commit)
- **What**: delete the phantom `custom_providers` row `name = 'NaN'` in workspace
  `019f9114-0a75-7be1-8649-69e8e6def0fe`, and repoint that workspace's LLM config to
  `provider = 'gemini'`, `model = 'gemini-2.5-flash'`, `base_url = NULL`, keeping the
  valid API key. `model` is set explicitly because the persisted
  `deepseek-v4-flash` cannot be served by Gemini and would fail extraction.
- **Acceptance**: the probe answers 200 with Gemini models for that workspace, and
  the registry lists no `NaN` row.
- **Depends on**: T-001 (verified through the new endpoint)

### T-005 — Fix: a cloud provider must not receive the Ollama host

- **Status**: done (commit `4be3950`)
- **Files to modify**: `backend/src/storico/api/routes/workspace_settings.py`,
  `frontend/src/components/react/LLMConfigEditor.tsx`
- **Files to create**:
  `backend/tests/test_api/test_workspace_settings_llm_config.py`
- **What**: `resolve_llm_config` falls back to `settings.ollama_host` for `ollama`
  alone and resolves a cloud provider with no configured `base_url` to `None`; the
  form stops defaulting the Base URL field to `http://localhost:11434`.
- **Acceptance**: a `gemini` config with a `NULL` base URL resolves to `None`; an
  `ollama` config resolves to the Ollama host; a configured base URL survives for any
  provider; a workspace with no row keeps the Ollama default. In the form, an
  `openai` selection loaded with a `null` base URL probes with an empty one.
- **Depends on**: T-001, T-002 (the defect is only reachable once the probe carries
  the form's values)
- **Allowed edit surfaces**: `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_llm_config.py`,
  `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`

### T-006 — Verification gate

- **Status**: pending
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
| Removing `GET /llm/models` breaks an unknown consumer | A caller outside this repo 404s | Verified in-repo that the frontend is the only consumer; recorded in T-003 so the contract change is visible |
| An API key travels in a request | Key leaks into logs | D3: body, not query string; mirrors the existing `POST /api/v1/llm/test` |
| The pending body mixes with saved values | One provider's credential sent to another provider's endpoint | D4 rule, pure resolver, explicit test that the saved key is not borrowed |
| A resolved `base_url` that was never configured reaches the probe | A cloud provider probes (and extracts against) the Ollama host | T-005: the Ollama host is returned for Ollama alone, and the form keeps the field empty instead of defaulting it |
| Probing the form's selection sends a key the user has not saved yet | An outbound request the user did not expect | The probe already sent the stored key on the same user action; the request is unchanged in kind, only in source of truth |
| A custom provider saved with an unreachable base URL now auto-probes on load | A 502 surfaces at page load instead of after a click | The list is cleared and the failure is reported by the existing hint; this is the state the reported workspace was in, and T-004 removes that instance |
| `canProbe` for a custom provider requires a base URL, but the previous gate did not | A refresh that used to be clickable is now disabled | Correct: the backend returns `[]` without a base URL, so the click could never answer. The disabled title names the missing field |
| Debounce fights the test suite's default 1000 ms `waitFor` | Flaky frontend tests | Debounce is short (300 ms) and every affected assertion already awaits |

## Evidence log

_(each completed task records its commit identity here)_

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `cc9018b` | `POST /llm/models` takes an optional `LLMModelProbeRequest`; `_resolve_probe` decides between the posted selection and the saved row, and `_probe_models` holds the dispatch so the 502 names the provider actually asked. 9 new tests. Mutation-checked: making the resolver borrow the saved key/base URL from a pending body turned exactly the three no-borrowing tests red. Observed red first (`ImportError` on the two new symbols, `405` on the POST cases). Verified: focused suite 25 passed, `ruff check` and `ruff format --check` clean, full backend suite 522 passed / 1 skipped. One `unreachable-except` advisory at `workspace_settings.py:412` is a false positive in `fetch_openai_compatible_models` (pre-existing, outside the diff hunk, only shifted in line number). |
| T-002 | `fa0e130` | The form probes the selection it holds; the auto-probe fires once per provider and drops the previous list; free-text fields stay explicit; a successful save re-probes; the custom path probes on load when its saved endpoint is complete; the refresh button gained a stable `aria-label` and a `llmModelsNoBaseUrl` title. 9 tests added or retargeted. Observed red first (8 failures, exactly the new/changed cases). Verified: focused suite 44 passed, `tsc --noEmit` clean, full frontend suite 249 passed. |
| T-003 | `937f116` | `docs/api.md` documents the endpoint as `POST` with the optional body and the D4 merge rule. |
| T-004 | — | Operational. Deleted the phantom `custom_providers` row `NaN` (`01a0b211-e63c-78d3-b61b-01f6a65eb057`) and repointed workspace `019f9114-…` to `gemini` / `gemini-2.5-flash` / `base_url = NULL`, keeping the verified key. Verified against the running API: `POST /llm/models` with no body now answers **200 with 41 Gemini models**, where the same call answered 502 before. |
| T-005 | `4be3950` | `resolve_llm_config` returns the Ollama host for `ollama` alone; a cloud provider with no configured base URL resolves to `None`; the form stops defaulting the field to `http://localhost:11434`. 4 backend tests + 1 frontend test. Observed red first (the gemini case asserted `None` and got `http://ollama.test:11434`; the form test counted a leaked host). Verified against the running API: `GET /settings/llm` answers `base_url: null` and the selection the form posts returns the 41 Gemini models. |
| T-006 | — | Verification of the final tree. `ruff check` clean, `ruff format --check` 207 files already formatted, `pytest -q` **526 passed / 1 skipped / 1 warning**, `tsc --noEmit` clean, `vitest run` **24 files / 250 tests passed**, `pnpm run build` complete. The single skip is the long-standing testcontainers/Docker one, and the `RuntimeWarning` is the pre-existing SQLAlchemy one in `test_custom_provider_repo.py`. Three build warnings (`ChevronDown`/`Copy` unused in `ErrorDisplay.tsx`, two `zod` comments) are in files this candidate does not touch. |

## Outcome

All six tasks are complete and verified. Five commits: `cc9018b` (backend probe),
`fa0e130` (frontend probe), `937f116` (docs), `4be3950` (the Ollama-host leak),
plus the T-004 data cleanup, which has no commit because it is a database change.

**The reported symptom is gone.** The workspace that reported it answers `200` with
41 Gemini models where it previously answered `502`, and every other provider now
answers for the selection actually shown in the select.

Two facts worth carrying forward:

- The `NaN` provider row was **out-of-band data**, not an application bug: the
  registry API normalizes to lowercase, so `NaN` cannot be created through it. The
  application fix removed the coupling that made that row lethal; T-004 removed the
  row itself. A registry row that disappears this way can still be recreated by
  whatever inserted it.
- The Ollama-host leak (T-005) was **pre-existing and unreachable** until the probe
  started carrying the form's values. Fixing the probe without it would have moved
  the wrong-endpoint bug from "any provider answers for the saved one" to "a cloud
  provider answers at the Ollama host".

Diff against `cc9018b^`: 8 files. The review candidate wants to be the work-unit
commits, not the branch tip.
