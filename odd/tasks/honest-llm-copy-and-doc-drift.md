# ODD Feature: honest-llm-copy-and-doc-drift

> **Status**: in progress
> **Created**: 2026-06-30
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/honest-llm-copy-and-doc-drift`, stacked on
> `feat/llm-config-validation-gate` (nothing pushed yet, so this branch's diff against
> its parent is exactly this slice).
> **Receipt-driven development**: off in this clone.

## Problem

Slice 1 of the review of `llm-config-validation-gate`'s follow-ups. Four items, all the
same class of defect: **the product and its documentation state things that are not
true**, and three of them are stated to the user at the exact moment they are deciding
whether to trust the tool with a credential.

1. **The API-key field claims encryption that does not exist.** `llmApiKeyDesc` says
   *"Your API key for this provider. Stored encrypted at rest."* / *"Tu API Key para este
   proveedor. Se almacena encriptada."* There is **no encryption anywhere in the
   backend**: `grep -rniE "cryptography|fernet|nacl|aes|kms" backend/src | wc -l` is `0`,
   `workspace_llm_configs.api_key` is a plain `String(500)`, and
   `user_preferences.preferences` is a plain `JSON` column. The claim appears in three
   places, including the editor's hardcoded fallback.
2. **Onboarding step 3 promises a working setup it does not create.**
   `onboarding.step3_note` says *"Ollama works out of the box with no API key."* /
   *"Ollama funciona sin configuración adicional, sin API key."* Ollama indeed needs no
   key, but **every** provider family requires a `model`, and step 3 never asks for one —
   so the "out of the box" half is false and the user's first extraction is refused.
3. **`docs/api.md` lies about five things.** Audited mechanically against the running
   app's OpenAPI schema (`create_app().openapi()`), not by eye: three documented routes
   do not exist as written (`GET /health`, `POST /api/v1/extract`, and onboarding as
   `POST` instead of `PATCH`), the custom-provider name rule is the slug rule that
   `custom-provider-free-form-name` reversed, and the extraction example documents a
   synchronous `201` with a `tasks` array for an endpoint that answers `202` and returns
   an `extraction_id` to poll.
4. **Both locale files declare two keys twice.** `stories.create_error` and
   `kanban.invalid_drop` each appear twice with identical values, so nothing is broken
   today — but JSON keeps the last one, both keys are **read by the UI**
   (`StoriesList.tsx:205,224`, `KanbanBoard.tsx:148`), and CI runs no JSON linter, so the
   next edit to one copy silently changes user-visible copy.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Scope | Exactly these four. The blank-endpoint normalization (C), `ErrorDisplay` (B) and the dead per-user LLM slice (G) are their own slices and are **not** touched here. |
| D2 | The encryption claim | **Tell the truth in the copy now; treat real encryption as its own decision.** The replacement states only verifiable facts: the key lives with the workspace on the server, is readable by its admins, and is never saved in the browser. No security promise is made in either direction. |
| D3 | The onboarding note | Fix the **copy** (keep step 3 collecting only the provider). It stops claiming the workspace is ready and names the missing step. Collecting the model in onboarding is a product change, not this slice. |
| D4 | `docs/api.md` boundary | Fix the **false** statements the audit found and add the workspace-scoped extraction routes the corrected example depends on. Two adjacent corrections rode along, because leaving them would have left the same file still wrong: the nine collection rows (five distinct base paths) got the trailing slash FastAPI actually exposes (without it the documented path answers a redirect), and the two health routes are now documented because the `/health` correction landed on that row. The three **omissions** left over are gaps, not lies, and stay as follow-ups. |
| D5 | Duplicate keys | Remove the **later** occurrence of each pair — the ones that read as strays from a later append — keeping the copy where it belongs. Behaviour-neutral: the values are byte-identical, and today the *first* copy is the shadowed one. |
| D6 | A permanent guard | Add a duplicate-key guard to the frontend suite. Without one this is tidying that regresses, and CI has no JSON linter. It has to read the raw text: `JSON.parse` collapses duplicates before a reviver can see them. |

## Non-goals

- No encryption, no key management, no migration (D2).
- No change to what onboarding collects (D3).
- No new endpoints, no backend behaviour change of any kind. This slice changes copy and
  documentation only.
- No JSON/markdown linter wired into CI (the guard is a test, not a new tool).
- No rewrite of `docs/api.md` into an OpenAPI-generated document.

## Established facts (verified)

- Encryption: `grep -rniE "cryptography|fernet|nacl|aes|kms" backend/src` → 0 matches.
  `api_key: Mapped[str | None] = mapped_column(String(500))`
  (`infrastructure/database/models/workspace_llm_config.py:29`);
  `preferences: Mapped[dict] = mapped_column(JSON)` (`.../models/user_preferences.py`).
- The API key is deliberately returned to workspace admins by `GET /settings/llm` so the
  form can display it and probe the provider — so "readable by its admins" is true, and
  testing it is what keeps D2 honest.
- The key is **not** in browser storage: `settingsStore`'s `partialize` persists only
  `settings.export` (`stores/settingsStore.ts`).
- The claim's three occurrences: `i18n/en.json:425`, `i18n/es.json:425`, and the
  fallback at `components/react/LLMConfigEditor.tsx:1032`.
- Onboarding: `OnboardingModal.tsx:115` calls `upsertLLMConfig(wsId, { provider })`; the
  step-3 copy keys are `onboarding.step3_description` (accurate) and
  `onboarding.step3_note` (the false claim).
- OpenAPI audit: 48 real operations vs 43 documented, and the three documented-but-absent
  ones above. `POST /api/v1/extract` returns **410 Gone**
  (`api/routes/extraction.py:57-74`); onboarding is `@router.patch("/me/onboarding")`
  (`api/routes/users.py:96`) and the frontend already calls it with `api.patch`
  (`lib/user-api.ts:50`).
- The real extraction contract: `ExtractResponse` = `{extraction_id, status,
  user_story_id, message}` with `202`, then
  `GET /api/v1/workspaces/{workspace_id}/extract/status/{extraction_id}`
  (`api/schemas/extraction.py`, `api/routes/extraction.py`).
- The error envelope `{detail, type}` in `docs/api.md` is **correct** — `api/errors.py`
  emits exactly `type: entity_not_found | duplicate_entity | repository_error |
  internal_error`.
- The custom-provider name rule today: trimmed, 1–50 characters after trimming, any
  characters, stored verbatim; built-ins refused case-insensitively; the select sentinel
  refused; `409` for a duplicate (`api/routes/workspace_settings.py`,
  `api/schemas/custom_provider.py`).
- Duplicates: `stories.create_error` at `en.json:137` and `:207` (identical values), and
  `kanban.invalid_drop` at `:240` and `:242` (identical values). Same in `es.json`. Both
  keys are read by the UI, so the shadowing is real.
- i18n rules to respect: `i18n/__tests__/neutral-spanish.test.ts` enforces neutral
  Spanish (no voseo) and `en`/`es` key parity.
- CI runs `tsc --noEmit` and `vitest run` for the frontend, `ruff` and `pytest` for the
  backend — no JSON or markdown linter.

## Tasks

### T-001 — The API-key field stops claiming encryption

- **Status**: pending
- **Files to modify**: `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/LLMConfigEditor.tsx`
- **What**: replace `llmApiKeyDesc` in both locales and the editor's hardcoded fallback
  (D2) with copy stating only what can be verified: stored with this workspace on the
  server, readable by its admins, never saved in the browser. Neutral Spanish.
- **Acceptance**: no occurrence of the encryption claim remains (a grep for
  `encrypted at rest|encriptada|cifrad` over the frontend returns nothing for this field);
  `tsc --noEmit` and `vitest run` pass.
- **Allowed edit surfaces**: `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/LLMConfigEditor.tsx`

### T-002 — Onboarding step 3 stops promising a ready workspace

- **Status**: done (commit `5251cc1`, extended in `afe763a`)
- **Files to modify**: `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`
- **What**: rewrite `onboarding.step3_note` (D3) so the Ollama fact is paired with the
  step it does not cover: every provider still needs a model, chosen later in Settings
  before the first extraction.
- **Acceptance**: the note no longer claims the setup works without further action and
  names where the remaining step happens; both locales updated, key parity and neutral
  Spanish tests pass.
- **Allowed edit surfaces**: `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`

### T-003 — Remove the duplicate keys, and stop the next one

- **Status**: done (commit `144f0df`)
- **Files to modify**: `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/i18n/__tests__/no-duplicate-keys.test.ts` (new)
- **What**: drop the later occurrence of `stories.create_error` and of
  `kanban.invalid_drop` in both files (D5), then add a guard (D6) that reads each locale
  file as **text** and fails when an object declares the same key twice — `JSON.parse`
  cannot see a duplicate, so the check has to scan the raw document. The scanner is
  minimal and covered by its own cases: a nested duplicate fails, an array of objects
  that legitimately repeat the same key across elements does **not** fail, and a string
  value containing `":` does not produce a false positive.
- **Acceptance**: `vitest run` passes on both real files; a red run with a planted
  duplicate fails the guard; `tsc --noEmit` exit 0. The removal is proven
  behaviour-neutral by asserting the effective value of each de-duplicated key before and
  after (identical pairs).
- **Allowed edit surfaces**: `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/i18n/__tests__/no-duplicate-keys.test.ts`

### T-004 — `docs/api.md` true against the running app

- **Status**: done (commit `5737085`)
- **Files to modify**: `docs/api.md`
- **What**: five corrections (D4): the health path, the extraction routes (replacing the
  410 legacy entry and adding the workspace-scoped POST plus its status route), the
  onboarding method, the custom-provider name rule, and the extraction example rewritten
  for the asynchronous `202` + poll contract with the real `ExtractResponse` shape.
- **Acceptance**: re-running the OpenAPI comparison against the corrected file reports
  **zero** documented-but-absent operations; the example matches `ExtractResponse` field
  for field.
- **Allowed edit surfaces**: `docs/api.md`

### T-005 — Verification gate

- **Status**: pending
- **What**: run the repo gate on the candidate and record the outcome; delegate an
  independent verification of the two claims a test cannot fully assert (that no
  encryption claim survives anywhere in the repo, and that `docs/api.md` has no remaining
  documented-but-absent operation).
- **Commands**:
  - `cd frontend && node_modules/.bin/vitest run` and `node_modules/.bin/tsc --noEmit`
  - `cd backend && .venv/bin/pytest -q`, `.venv/bin/ruff check src tests`,
    `.venv/bin/ruff format --check src tests`
- **Acceptance**: every command passes and the counts are recorded; the OpenAPI
  comparison is re-run and reported.
- **Depends on**: T-001, T-002, T-003, T-004

### T-006 — Close the feature

- **Status**: pending
- **What**: flip the status line, write the evidence log with real commit identities and
  observed output, and record the follow-ups this slice creates.
- **Depends on**: T-005

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Replacing the encryption claim with facts reads as a downgrade a user notices ("so it is *not* encrypted?") | The honest copy draws attention to a real gap | D2 is the point: the alternative is a false promise. The real fix (encryption) is recorded as its own decision, not silently skipped |
| The duplicate-key scanner is hand-rolled | A subtle bug makes it pass on a real duplicate, or fail on valid JSON | It is tested in both directions against synthetic documents (nested duplicate, array of objects repeating a key, string containing `":`) plus both real locale files |
| Removing the later duplicate changes which value wins | User-visible copy changes silently | The two values in each pair are asserted byte-identical before removal, so the effective value cannot move |
| Rewriting the extraction example drifts again | Docs become stale a second time | The acceptance criterion is mechanical (re-run the OpenAPI comparison), not editorial |
| Touching `LLMConfigEditor.tsx` for one string re-opens a file the previous slice just validated | Unintended behaviour change | One string constant, no logic; the file's 59 tests are the regression check |

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

## Follow-ups (not part of this change)

- **Real encryption for workspace API keys** (D2's other half): key management, at-rest
  encryption, migration of existing plaintext rows, and a decision about whether the
  credential may keep being returned to admins in cleartext. A feature of its own.
- The stale provider enumerations this slice found but deliberately did **not** sweep:
  `pages.docs.llm_runner_desc` ("Ollama / OpenAI / Anthropic"), `landing` FAQ `a6`
  ("Cloud models (OpenAI, Anthropic)"), and the two privacy-policy sentences
  `collection_llm` and `transfers_body` (both "a cloud LLM provider (OpenAI,
  Anthropic)"). Each omits Gemini. `pages.docs.step_2` was the one of these that sat in
  the sentence being corrected, so it was fixed there; the rest are a copy sweep of
  their own, and the privacy-policy pair deserves its own review rather than riding on
  this slice.
- `pages.docs.llm_backend_openai` still advertises "GPT-3.5, GPT-4" while the app's
  default OpenAI model is `gpt-4o-mini`; a support list that is a subset is not false,
  but it is stale.
- The omitted-but-real operations `GET /api/v1/workspaces/{id}/export/tasks`,
  `POST /api/v1/auth/sync` and `DELETE /api/v1/users/me` are still undocumented (D4).
- The omitted-but-real operations `GET /api/v1/workspaces/{id}/export/tasks`,
  `POST /api/v1/auth/sync` and `DELETE /api/v1/users/me` are still undocumented, and so is
  the legacy projects pair `GET|POST /api/v1/projects` (which answers `307` → `410`), even
  though the analogous legacy extract route is now documented (D4).
- **The legacy localStorage key is never removed.** `settingsStore` persists under
  `storico-settings-v2` and its comment says the old `storico-settings` still has API keys
  in it, but nothing calls `removeItem`. So "never saved in your browser" is exactly true
  of the current code and *not* unconditionally true of a browser upgraded from a build
  that still had the per-user LLM editor. A one-line `removeItem` on load would close it;
  it is a behaviour change, so it does not belong in a copy-only slice.
- **`completed_at` is never set.** The status route passes `completed_at=None`
  (`api/routes/extraction.py`), so a finished extraction reports `null`. The doc now says
  so; fixing the route is app work.
- **Stale build artifacts still carry the old false claim.** `frontend/dist/` and
  `frontend/.vercel/output/` hold pre-change bundles with *"Stored encrypted at rest"*.
  They are gitignored and regenerated by a build, but a deploy that reuses them would
  still serve it — regenerate before shipping.
- The landing FAQ `a6` still says *"Storico supports Ollama out of the box"*. Judged a
  **capability** claim rather than a readiness one (support is built in), so it was left;
  it is nevertheless the same phrase this slice removed elsewhere, and it sits next to the
  stale provider list below.
- Slice 2 (blank `base_url`/`api_key` reaching the adapter), slice 3 (`ErrorDisplay`
  renders `null` — six call sites, one of them a blank page), slice 4 (the dead per-user
  LLM slice and the plaintext keys it may still hold) remain open.
