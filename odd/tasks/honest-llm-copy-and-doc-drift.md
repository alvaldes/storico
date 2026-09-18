# ODD Feature: honest-llm-copy-and-doc-drift

> **Status**: done — six commits on `feat/honest-llm-copy-and-doc-drift` (`7617b08`..
> `da673e8`), plus the evidence commit that carries this line (seven against the parent
> branch); nothing was pushed. Receipt-driven development is **off** in this clone, so no
> native review ran; one independent verification did, recorded below with its findings and
> their disposition.
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

- **Status**: done (one independent `gentle-ai-verify` run over `c1a60a0..afe763a`; its
  findings are fixed in `da673e8`, and the gate was re-run green on the corrected
  candidate — see the verification section below)
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

- **Status**: done (this document's commit)
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
| T-001 | `7617b08` | `llmApiKeyDesc` rewritten in both locales and in the editor's hardcoded fallback. A repo-wide grep for the encryption claim, in English and Spanish, returns nothing outside the change record that quotes it. `tsc` exit 0; the i18n suites pass. |
| T-002 | `5251cc1`, extended in `afe763a` | `onboarding.step3_note` no longer claims a working setup. The gate re-run at T-005 found the **same false promise in a second surface** — `pages.docs.step_2`, the public docs page — which `afe763a` fixes too, along with the provider list in that same sentence (it omitted Gemini). Repo-wide grep for the promise now returns nothing. |
| T-003 | `144f0df` | The later copy of `stories.create_error` and of `kanban.invalid_drop` removed from both files — behaviour-neutral, and proven so: the pairs were byte-identical before the edit and the effective values are unchanged after it. New `no-duplicate-keys.test.ts` with a raw-text scanner and 12 cases. Red run with a planted duplicate: **1 failed** naming `llmSaved`, green when restored. Full frontend suite **30 files / 351 passed**, `tsc` exit 0. |
| T-004 | `5737085` | Five false statements corrected plus the two workspace-scoped extraction routes, the canonical trailing slash on nine collection rows, and both health routes. Acceptance is mechanical and was re-run after every later edit: **zero documented-but-absent operations** against `create_app().openapi()`, and both JSON examples match `ExtractResponse`/`ExtractionResponse` field for field. |
| T-005 | `da673e8` | Gate and independent verification, below. Six findings addressed: one medium falsehood in `docs/security.md` that the slice had missed, four imprecisions in what this slice had just written, and an overclaiming code comment. |
| T-006 | this document | Status, evidence, the verification record and the dispositions, written after every command above ran. |

## Verification (RDD off — independent verification, not native review)

One `gentle-ai-verify` run over `c1a60a0..afe763a`, read-only, with its mutations in a
`/tmp` copy. Gate it observed: frontend **30 files / 351 passed**, `tsc --noEmit` exit 0;
backend **585 passed, 1 skipped**, `ruff check` and `ruff format --check` clean over 210
files. Gate re-run by me on the corrected candidate (`da673e8`): same numbers.

What it confirmed independently, by driving real code rather than reading the tests:

- **Every clause of the replacement copy is true.** The key is written to
  `workspace_llm_configs.api_key`; the only schema carrying it is `LLMConfigResponse`,
  returned by `GET`/`PUT /settings/llm`, both `require_admin`; and no storage API in the
  client touches it (`partialize` persists only `settings.export`).
- **The old claim was indeed false**: `grep -rniE "cryptography|fernet|nacl|AES|kms|encrypt"
  backend/src` → 0 matches.
- **The range changed exactly three keys per locale and nothing else.** It compared the
  *effective parsed values* (not the diff): `base keys=663 head keys=663` on both files,
  three changed keys, and the removed duplicates left the effective value untouched —
  which is the independent proof of this slice's "no behaviour change" property.
- **`docs/api.md`: zero documented-but-absent**, every documented path's trailing slash
  matching the live route, both examples field-for-field, every enum value a real member,
  and the error envelope real.
- **The guard has teeth and no false positives** across 12 crafted shapes, including the
  array-of-objects shape that a path-keyed check would wrongly flag, and it reports the
  original duplicates at the parent commit (`['create_error', 'invalid_drop']`).
- **The documented custom-provider rule matches the route clause by clause** (trim, 1–50
  after trim, stored verbatim, `Groq ≠ groq`, case-insensitive built-in refusal, sentinel
  refusal, 409 duplicate, 404 foreign id), and `PATCH` really is the onboarding method
  (`POST` → 405).

### Findings and disposition

- **F1 (fixed in `da673e8`) — pre-existing, medium, and the one that mattered.**
  `docs/security.md:88` claimed the LLM API keys are *"nunca expuestas al frontend"*.
  They are: `GET /settings/llm` returns `api_key` in `LLMConfigResponse` and the editor
  loads it into the form (`LLMConfigEditor.tsx:123,271`). A security document asserting
  non-exposure of a credential is the same defect class this slice exists to fix, and the
  replacement copy this slice wrote ("readable only by its admins") contradicted it. The
  bullet now states the real posture — plaintext at rest, returned to the workspace admin,
  never returned by the member-readable status route — and the pending-work list gains the
  at-rest encryption item.
- **F2 (fixed in `da673e8`) — candidate-caused, low.** The `410 Gone` sentence I wrote for
  the legacy extract route contradicted the trailing-slash rule I had written two
  paragraphs above: the exact no-slash path answers `307` to the slashed form, which is
  what answers `410`. The sentence now says that.
- **F3 (accepted, not a defect) — pre-existing, low.** The landing FAQ `a6` still says
  *"Storico supports Ollama out of the box"*. It is a **capability** claim (Ollama support
  is built in) and not a readiness claim, which is the distinction that makes the removed
  `step3_note` a defect. Left as is, recorded with the reasoning and with the stale
  provider list it sits beside.
- **F4 (accepted as a follow-up) — pre-existing, low.** `frontend/dist/` and
  `frontend/.vercel/output/` still contain pre-change bundles with the old encryption
  claim. Gitignored and regenerated by a build; a deploy reusing those artifacts would
  still serve it, so it is recorded as a shipping note rather than a source fix.
- **F5 (fixed in `da673e8`) — candidate-caused, low.** The extraction example showed
  `completed_at` with a timestamp, but the status route passes `completed_at=None`. The
  example now shows `null` with a sentence saying so, and the app-side gap is a follow-up.
- **F6 (fixed in `da673e8`) — candidate-caused incompleteness, low.** The custom-provider
  rules I rewrote stated the `409`s unconditionally, omitting the deliberate no-op: a row
  renamed to its own name answers `200` before the reserved-name and duplicate checks, so
  a migration-`0021` row named `Ollama` can resubmit its own name. That carve-out is now
  documented.
- **F7 (fixed in `da673e8`) — informational.** My guard's comment claimed the
  escape-spelling limit "cannot hide a real duplicate here". It can: `{"a": 1,
  "\u0061": 2}` is a duplicate the guard reports as clean. Not reachable in these two
  ASCII-key files, but the comment now states the hole instead of dismissing it.
- **F8 (recorded) — informational.** More live operations are undocumented than the three
  the slice listed: the legacy projects pair `GET|POST /api/v1/projects` also answers
  `307` → `410` and is not documented, while the analogous extract route now is. Recorded
  as a follow-up rather than swept in — the boundary is "false statements", not "complete
  coverage".
- **F9 (fixed in this document) — informational.** My own D4 note said "eight collection
  paths"; it is nine rows across five distinct base paths. Corrected.
- **F10 (recorded) — informational, and the one hole in the new sentence.** The store's
  comment says the pre-refactor `storico-settings` key still holds API keys, and nothing
  ever calls `removeItem`. So "never saved in your browser" is exactly true of current code
  and not unconditionally true of a browser upgraded from the older build. A one-line
  `removeItem` would close it; being a behaviour change, it is a follow-up, not part of a
  copy-only slice.

Not verified: the authenticated custom-provider create/rename calls live (source and
routing probes only, no session), `docs/api/spec-api-endpoints.md` (out of scope), and the
E2E suite (already recorded in this repo as not runnable).

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
