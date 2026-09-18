# ODD Feature: custom-model-list-visibility

> **Status**: done — merged into `main` by fast-forward as five commits
> (`6938dd9`, `15ac9ab`, `f1b0531`, `65ddc4a`, + the evidence commit that carries
> this line); the feature branch was deleted. Not pushed.
> **Created**: 2026-09-17
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/custom-model-list-visibility`

## Problem

Reported symptom, for provider `nan` (a workspace-registered custom provider):

> "sí cargan los modelos pero no se ven en el select"

The probe works. Reproduced by the reporter against the running app:

```
POST http://localhost:4321/api/v1/workspaces/019f9114-…/settings/llm/models
body {"provider":"nan","base_url":"https://api.nan.builders/v1/","api_key":"sk-…"}
→ 200 [{"id":"deepseek-v4-flash","name":"deepseek-v4-flash"}, … 12 models]
```

The response reaches `availableModels`. What is invisible is the **suggestion
surface**: in custom mode the model field is a free-text `<Input>` backed by a
native `<datalist>` (`LLMConfigEditor.tsx:601-611`), and Firefox does not render
that list the way a user expects.

### Root cause (sourced, not inferred)

Native `<datalist>` is a degraded affordance in Firefox, independently of this
codebase:

- [Bug 1575444](https://bugzilla.mozilla.org/show_bug.cgi?id=1575444) — Firefox
  draws **no dropmarker** for `<input list="…">`, unlike Chrome.
- [Bug 1882075](https://bugzilla.mozilla.org/show_bug.cgi?id=1882075) — the list
  needs **two clicks** to open (the first only focuses), and typed text filters
  options by prefix.

So with a loaded list, an empty field, and no typing, the user sees a plain text
box. The models loaded; nothing told them so.

## Decisions (user-approved 2026-09-17)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Fix mechanism | Render the discovered models as an **always-visible list under the field** in custom mode, not a richer popup. Chosen over a creatable Combobox because `@base-ui/react` 1.8 has no free-text commit (typed text reverts on blur) — the risk already recorded in `custom-provider-model-discovery.md`. |
| D2 | Field contract | The field stays free text, so D3 of `custom-provider-model-discovery` holds: never selection-only. An id absent from the list must remain typeable. |
| D3 | What a click means | Clicking an entry writes the model **id** into the field; the entry's visible text is the human-readable **name**. A differing id is surfaced on the entry. |
| D4 | Suggestion layers | The native `<datalist>` stays: it is the type-time filter, while the visible list is the always-on surface. Two roles, one list. |
| D5 | The provider's catalogue | The list stays **raw**. Asked at review time whether to filter or group the non-chat entries, the user chose to show all 12. The provider owns its catalogue, and any id heuristic is a guess about what can chat that can also hide a model the workspace wants. A visible filter can be added later, once the noise is a real complaint. |

## Non-goals

- No change to the probe, the endpoint, or the backend.
- No change to the known-provider `Combobox` path.
- No provider-specific filtering of the returned list (it is whatever the
  provider serves, `rerank`/`whisper`/`flux-2-klein` included — see D5).
- No persisted-list cache, no new state.

## Established facts (verified in code)

- `isCustomProvider` is derived, not stored: `LLMConfigEditor.tsx:74` uses
  `!isKnownProvider(llmConfig.provider)` against `KNOWN_PROVIDERS` in
  `frontend/src/lib/llm-providers.ts:9`.
- The custom branch renders `Input` + `<datalist>`; the known branch renders the
  base-ui `Combobox` (`LLMConfigEditor.tsx:585-680`).
- The label, hint chain and refresh button already exist for custom mode;
  `llmCustomModelsEmpty` and `llmCustomModelHint` carry the empty/typing states.
- Two existing tests pin the `<datalist>` link
  (`__tests__/LLMConfigEditor.test.tsx:816-829`), and `CUSTOM_MODELS` in that
  suite deliberately has **distinct** ids and names
  (`deepseek-chat` / `DeepSeek Chat`), which is what makes the id-vs-name
  decision testable.
- `frontend/src/i18n/__tests__/neutral-spanish.test.ts` enforces neutral Spanish
  (tú register, no voseo) and key parity between `en.json` and `es.json`.

## Tasks

### T-001 — Frontend: always-visible discovered-model list in custom mode

- **Status**: done (commit `15ac9ab`)
- **Files to modify**: `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`
- **What**:
  - In the custom branch, under the field row and above the `FieldDescription`,
    render the discovered models as a wrapping list of `<button type="button">`
    entries when `availableModels.length > 0`.
  - Entry text is `model.name`; clicking writes `model.id` into the field
    (D3). Mark the entry matching the current `llmConfig.model` with
    `aria-pressed="true"`.
  - Keep the `<Input>` editable and keep the `<datalist>` (D2, D4).
  - New i18n key `llmCustomModelsDiscovered` in **both** `en.json` and `es.json`,
    neutral Spanish (tú register, no voseo). The count is rendered beside the
    label in JSX, not interpolated into the string.
  - Tests: the list is visible after a settled probe without touching the field;
    choosing an entry fills the field with the id and persists on save; no list
    renders before a probe settles or when the list is empty.
- **Acceptance**: `pnpm exec tsc --noEmit` and `pnpm vitest run` pass; the
  models are visible with zero interaction beyond loading the page.
- **Allowed edit surfaces**: `frontend/src/components/react/LLMConfigEditor.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx`

### T-002 — Verification gate

- **Status**: done
- **What**: run the repo gate and record the outcome.
- **Commands**:
  - `cd frontend && pnpm exec tsc --noEmit`
  - `cd frontend && pnpm vitest run`
  - `cd frontend && pnpm run build`
- **Acceptance**: every command passes; any failure is reported as a blocker,
  never as a done task.
- **Depends on**: T-001

### T-003 — Formatter cleanup of the pre-existing `title` prop

- **Status**: done (commit `65ddc4a`)
- **Files to modify**: `frontend/src/components/react/LLMConfigEditor.tsx`
- **What**: collapse the refresh button's multi-line `title` prop, which was
  already not `prettier`-clean at `HEAD`, so the touched file is formatter-clean.
  Requested by the user as part of "fix everything" before the merge.
- **Acceptance**: `npx prettier@3.9.8 --check` exits 0 on the file, and the only
  change is the parenthesization and line breaks of that one prop.
- **Allowed edit surfaces**: `frontend/src/components/react/LLMConfigEditor.tsx`

### T-004 — Final pre-merge gate

- **Status**: done
- **What**: re-run the gate on the candidate that is about to fast-forward into
  `main`, because a source commit landed after T-002.
- **Commands**: T-002's list plus
  `npx prettier@3.9.8 --check src/components/react/LLMConfigEditor.tsx src/i18n/en.json src/i18n/es.json`.
- **Acceptance**: every command passes and the test count is unchanged from
  T-002, since the added commit is formatting-only.
- **Depends on**: T-003

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| The visible list makes the field read as selection-only | The user stops typing a model id the provider does not list | D2; the input keeps its label, placeholder and typing hint, and a test asserts it is not `readonly` |
| Entry text shows the name while the id is what saves | A user picks "DeepSeek Chat" and cannot tell what will be sent | The id is surfaced on the entry when it differs from the name (D3) |
| A long provider list (12+ models here) crowds the card | Layout noise | Wrapping flex row under the field, with its own label and count |
| Duplicate suggestion layers confuse | Two overlapping affordances | Documented as two roles in the code comment beside the list (D4) |

## Evidence log

_(each completed task records its commit identity here — no row is written before
its command has actually run)_

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `15ac9ab` | Custom mode now renders the discovered models as an always-visible list of `type="button"` entries below the field row; the entry text is the model `name`, the click writes the `id`, and the entry matching the saved model carries `aria-pressed="true"`. The `<Input>` and its `<datalist>` remain. New key `llmCustomModelsDiscovered` in both locales. 3 new tests; `git diff main...HEAD -- LLMConfigEditor.tsx` is a pure insertion (31 added, 0 removed). |
| T-002 | — | Independent verification of the candidate on a clean tree. `tsc --noEmit` exit 0, no diagnostics. `vitest run` exit 0, **24 files / 253 tests passed** — matching the recorded pre-change baseline of 24/250 plus exactly the 3 added cases, with no previously-passing test regressed. `pnpm run build` exit 0, `[build] Complete!`. No backend file is in the diff. |
| T-003 | `65ddc4a` | The refresh button's `title` prop is now one line. `prettier --check` exits 0 on the file where it previously exited 1. One hunk, 1 insertion and 4 deletions. |
| T-004 | — | Re-verification of the 4-commit candidate on a clean tree. `prettier --check` exit 0 on all three touched frontend files. `tsc --noEmit` exit 0. `vitest run` exit 0, **24 files / 253 tests** — count unchanged, as a formatting-only commit requires. `pnpm run build` exit 0 with no new warning. Removal of the parentheses was proven value-equivalent, not assumed: `??` is associative, and the verifier tabulated all 8 nullish/non-nullish combinations of the three operands with identical results. |

## Verification findings

The gate is green, with two things recorded rather than smoothed over:

1. **2 of the 3 new tests are load-bearing, the third is a guard.** The
   verifier judged from the source and the diff that the visible-list cases
   cannot pass on `main` (no such button exists in the custom branch there),
   while `renders no discovered-models list when the probe returns nothing`
   asserts an *absence* and would pass unchanged on `main`. It is kept as a
   regression guard against a future "Discovered models (0)" label, and it is
   not counted as evidence of the fix. Neither the verifier nor the writer ran
   the tests against pre-change code — the red run for that file was observed by
   the writer before the implementation existed (`2 failed | 46 passed`), which
   is the TDD witness.
2. **Three build warnings and no new one.** They come from `ErrorDisplay.tsx`
   (untouched, byte-identical to `main`) and from `zod@4.6.4` in
   `node_modules`.

## Outcome

Fix verified end to end: the models the probe returns are on screen with no
interaction, and the field still accepts a typed id. RDD is off in this clone,
so no native review ran; the candidate is the `15ac9ab` work unit plus the
`65ddc4a` formatter cleanup. Fast-forwarded into `main` at the user's explicit
request, and the feature branch deleted.

## Follow-ups (not part of this fix)

- D5 leaves the list raw on purpose. If the noise is ever reported as a problem,
  the fix is a visible, explicit filter — never a silent id heuristic.
- The verifier's stated coverage limit: the list is only exercised in `jsdom`.
  No one has watched the real page in Firefox, so the browser-level claim rests
  on the Mozilla bug reports cited above, not on an observed render.
