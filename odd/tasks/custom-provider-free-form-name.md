# ODD Feature: custom-provider-free-form-name

> **Status**: done — landed on `main` by fast-forward as eight commits (`0d5de36`..
> `2e47993`, plus the evidence commit that carries this line); the feature branch was
> deleted; the work is on `origin/main` (every named commit is an ancestor of it, measured
> 2026-09-22). Receipt-driven development is **off** in this clone,
> so no native review ran; three independent verifications did, recorded below with
> their findings.
> **Created**: 2026-09-18
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/custom-provider-free-form-name`
> **Parent feature**: `odd/tasks/workspace-custom-providers.md` (reverses its D5)

## Problem

Reported by the user:

> "el nombre del custom provider puede ser cualquier cosa no necesariamente todo en
> minúscula, sin espacios y etc. Además si el máximo es 50 caracteres debería ponerse
> en el input (0/50) sabes como ya lo hemos hecho antes."

Two defects in the shipped custom-provider name field:

1. **The name rule is a slug, and it did not have to be.** D5 of
   `workspace-custom-providers` froze `^[a-z0-9][a-z0-9._-]{0,49}$` with trim +
   lowercase, on the stated grounds that "the value is a provider slug that reaches
   the adapter selector". The slug is **defensive, not load-bearing**: routing
   (`_build_llm_port`, `backend/src/storico/infrastructure/tasks/extraction_task.py:203`)
   compares exact equality against the four built-in names and sends *everything else*
   to the `OpenAIAdapter`. So `My Gateway v2` and `Ünïcode` route exactly like
   `deepseek` does. The cost of the slug is real (an org cannot register a vendor's
   name as they write it) and the benefit is zero.
2. **The `(0/50)` counter is missing.** The 50-character limit exists
   (`String(50)` column, `Field(max_length=50)`) but is invisible until the name is
   rejected. `ProjectForm.tsx` and `StoryForm.tsx` already establish the pattern:
   `maxLength={MAX}` on the control plus `{value.length}/{MAX}` in muted text.

## Decisions (user-approved 2026-09-18)

| # | Decision | Choice |
|---|----------|--------|
| D1 | Name rule | **Free-form text.** Trimmed on the way in, 1–50 characters after trimming, any other character allowed (uppercase, spaces, accents, punctuation). Stored **verbatim** as typed. |
| D2 | Identity | **Case-sensitive.** `Groq` and `groq` are two distinct providers in the same workspace; the DB `UNIQUE (workspace_id, name)` already matches, so **no migration** is involved. Chosen over case-insensitive identity precisely because that one would have required lower-casing comparisons plus a functional index. |
| D3 | Built-in guard | The four built-in names are still rejected, now **case-insensitively**: `OpenAI` is refused with the same `409` as `openai`, so a name that routes to the OpenAI-compatible branch can never masquerade as the built-in entry. |
| D4 | Select-control guard | The select's internal sentinel `__add_custom_provider__` (`frontend/src/lib/llm-providers.ts`) becomes reachable once the slug pattern is dropped, so the backend refuses that exact name with `409`. Without it, a provider registered with that name takes the select's "Add custom provider…" slot and the UI cannot select it. |
| D5 | Counter | The dialog shows `{length}/50` in muted text, right-aligned under the input, plus `maxLength={50}` on the control — the `ProjectForm` pattern. |
| D6 | Error precedence | Length → built-in → reserved sentinel, checked in that order so the specific reason survives. Unchanged from the current design; one new message is added for D4. |

## Non-goals

- No delete endpoint, no pagination (still `workspace-custom-providers` D8).
- No change to `_build_llm_port`, `PUT /llm` (still accepts any provider string,
  D9 of the parent), the `String(50)` column, or the migration.
- No case-insensitive duplicate detection, no functional index (D2).
- No change to the `<Select>`'s option list, the pencil, or the rename cascade.

## Established facts (verified in code)

- `NAME_PATTERN`/`NAME_RULE_MESSAGE` live in
  `backend/src/storico/api/schemas/custom_provider.py`; the frontend copy is
  `PROVIDER_NAME_PATTERN` in `frontend/src/lib/llm-providers.ts`, plus a zod schema
  `customProviderNameSchema` in `frontend/src/schemas/workspace.ts`.
- `_reject_known_provider_name` (`backend/src/storico/api/routes/workspace_settings.py:199`)
  compares `name in KNOWN_PROVIDERS` — exact match on the *already lower-cased*
  value, which is why dropping the lowercase step makes it case-sensitive by default.
- `Field(max_length=50)` in `CustomProviderRequest` runs on the **raw** value, so a
  padded name of 52 raw characters is refused even when the trimmed name fits. The
  rule has to move into the validator to measure what is actually stored.
- The sentinel is only escapable today because the pattern forbids a leading `_`
  (`^[a-z0-9]`). Nothing else keeps it out.
- Frontend tests to update: `frontend/src/lib/__tests__/custom-providers-api.test.ts`
  pins the lowercase normalization and the slug rejection set explicitly.
- Backend tests to update: `backend/tests/test_api/test_workspace_settings_providers.py`
  (`test_name_is_normalized`, `test_known_provider_names_are_rejected`,
  `test_invalid_names_are_rejected`).
- `frontend/src/i18n/__tests__/neutral-spanish.test.ts` enforces neutral Spanish and
  `en.json`/`es.json` key parity, so every new key lands in both files.

## Tasks

### T-001 — Backend: free-form name rule

- **Status**: done (commit `0d5de36`)
- **Files to modify**: `backend/src/storico/api/schemas/custom_provider.py`,
  `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_providers.py`
- **What**:
  - `normalize_provider_name` becomes `raw.strip()` (no lower-casing); the name rule
    becomes "1–50 characters after trimming", enforced **in the validator** on the
    trimmed value, and the raw `max_length=50` constraint goes away.
  - Reserved-name guard: keep `409`, broaden to the case-insensitive built-in check
    plus the exact select sentinel, both named constants in one place.
  - Tests: the existing normalization test now expects `Groq`; mixed-case built-ins
    (`OpenAI`, `OLLAMA`) are refused; the sentinel is refused; the reject set narrows
    to `["", "   ", "a"*51]`; new cases assert names the slug rule refused are now
    stored verbatim (`Groq`, `has space`, `Ünïcode`, `-leading`, a padded 50-char name).
- **Acceptance**: `backend/.venv/bin/pytest tests/test_api/test_workspace_settings_providers.py`
  passes, and `ruff check`/`ruff format --check` are clean on the touched files.
- **Allowed edit surfaces**: `backend/src/storico/api/schemas/custom_provider.py`,
  `backend/src/storico/api/routes/workspace_settings.py`,
  `backend/tests/test_api/test_workspace_settings_providers.py`

### T-002 — Frontend: provider vocabulary and zod schema

- **Status**: done (commit `0bf40e5`)
- **Files to modify**: `frontend/src/lib/llm-providers.ts`,
  `frontend/src/schemas/workspace.ts`,
  `frontend/src/lib/__tests__/custom-providers-api.test.ts`
- **What**:
  - `PROVIDER_NAME_MAX_LENGTH = 50` is exported (the dialog needs it for `maxLength`
    and the counter).
  - `normalizeProviderName` trims only; `isValidProviderName` means "the backend will
    accept this name" (length + not reserved); a new `isReservedProviderName` mirrors
    the backend's two guards. `isKnownProvider` stays exact-match and says why: it
    derives routing/UI state for an already-stored value, so it must not absorb the
    case-insensitive *reservation* semantics.
  - `customProviderNameSchema` keeps its trim-then-refine shape.
  - Tests: normalization preserves casing; the freed names are valid; `Groq`/`groq`
    are both valid; mixed-case built-ins and the sentinel are invalid.
- **Acceptance**: `frontend/node_modules/.bin/vitest run src/lib` passes and
  `tsc --noEmit` is clean.
- **Allowed edit surfaces**: `frontend/src/lib/llm-providers.ts`,
  `frontend/src/schemas/workspace.ts`,
  `frontend/src/lib/__tests__/custom-providers-api.test.ts`

### T-003 — Frontend: dialog counter and the two guards' messages

- **Status**: done (commit `709a9c6`)
- **Files to modify**: `frontend/src/components/react/CustomProviderDialog.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/__tests__/CustomProviderDialog.test.tsx` (new)
- **What**:
  - `maxLength={PROVIDER_NAME_MAX_LENGTH}` on the input, and the counter row
    (`{name.length}/50` in `text-muted-foreground`, `FieldError` on the left) copied
    from `ProjectForm.tsx`.
  - Error precedence D6, including the new reserved-sentinel message
    (`llmCustomProviderNameReserved`) in both locales, neutral Spanish.
  - Hint copy rewritten: any name, saved as typed, up to 50 characters.
  - A first focused test file for the dialog: counter starts at `0/50`, follows the
    typed length, `maxLength` is set, a name with an uppercase letter and a space is
    submitted verbatim, and each of the two guards shows its own message.
- **Acceptance**: `vitest run` and `tsc --noEmit` pass.
- **Allowed edit surfaces**: `frontend/src/components/react/CustomProviderDialog.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`,
  `frontend/src/components/react/__tests__/CustomProviderDialog.test.tsx`,
  `frontend/src/components/react/__tests__/LLMConfigEditor.test.tsx` (one case there
  asserted the old "not a slug" refusal, which the new rule makes obsolete)

### T-004 — Verification gate

- **Status**: done (three independent verifications: `gentle-ai-verify` on
  `0d5de36..709a9c6`, again on `a3e3288`, and again on `8e7573f`)
- **What**: run the repo gate on the candidate and record the outcome.
- **Commands**:
  - `cd backend && .venv/bin/pytest` and `.venv/bin/ruff check src tests`
  - `cd frontend && node_modules/.bin/vitest run` and `node_modules/.bin/tsc --noEmit`
- **Acceptance**: every command passes, the frontend/backend test counts are recorded
  against the baseline, and any failure is reported as a blocker — never as done.
- **Depends on**: T-001, T-002, T-003

### T-005 — Close the feature

- **Status**: done (this document's commit)
- **What**: flip the status line, write the evidence log with the real commit
  identities and the observed command output, and record any follow-up the change
  created (e.g. legacy rows whose name only differs by case).
- **Acceptance**: every row in the evidence log corresponds to a commit that exists
  on the branch and to a command that actually ran.
- **Depends on**: T-004

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Dropping the lowercase step re-opens the "`Groq` and `groq` are two rows" footgun the original D5 closed | A workspace accumulates near-duplicate provider names | Accepted by D2 as the user's choice; the picker shows the raw name, and this is recorded as a follow-up rather than silently designed around |
| A legacy row already stored under the sentinel makes the select show two items with the same value | The "Add custom provider…" option and that provider are indistinguishable | D4 closes the write path; the read path is recorded as a follow-up (a legacy row can only exist if it was written before this change, when the sentinel was unreachable) |
| Free text reaches the `String(50)` column unmetered | A DB-level truncation error instead of a clean 422 | The validator measures the trimmed length against 50; a test pins the boundary |
| `isKnownProvider` getting case-insensitive by accident | A legacy `Ollama` row is treated as the built-in and loses its base URL | It stays exact-match, with the reason in the code comment |

## Evidence log

_(each completed task records its commit identity here — no row is written before its
command has actually run)_

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `0d5de36` | `normalize_provider_name` trims and stops lower-casing; the 50-character cap moved from a raw `Field(max_length=...)` into the validator so it measures the stored name; `_reject_known_provider_name` became `_reject_reserved_provider_name`, comparing the built-ins case-insensitively and refusing `SELECT_CONTROL_VALUE`. Red run before the fix: **10 failed \| 27 passed** (the 3 mixed-case built-in cases passed already, because the old code lower-cased before the guard — they are the regression witness for D3). Green after: **37 passed**. `ruff check` clean, `ruff format --check` clean after collapsing one string. |
| T-002 | `0bf40e5` | `PROVIDER_NAME_MAX_LENGTH`, trim-only normalization, `isReservedProviderName`, and `isValidProviderName` as the whole rule. `isKnownProvider` untouched. Red run with the previous module restored from `main`: **16 failed \| 20 passed**. Green after: **36 passed** in that file; `tsc --noEmit` exit 0. |
| T-003 | `709a9c6` | `maxLength` + `(n/50)` counter, the message picked by rule, one new key in both locales, and the first focused test file for the dialog. Red run: **5 failed \| 2 passed** (the two that passed were the verbatim-save cases, which the old code satisfied only by accident of the test's own mock). Green after: dialog + i18n **10 passed**, full frontend suite **25 files / 267 passed**, `tsc --noEmit` exit 0. |
| T-004 | `a3e3288`, `8e7573f`, `2e47993` | The gate and the three verifications, below. Final candidate `2e47993`, on a clean tree: backend **540 passed, 1 skipped** (the skip is the pre-existing Docker-dependent integration test), `ruff check` and `ruff format --check` exit 0 over 207 files; frontend **26 files / 270 passed**, `tsc --noEmit` exit 0. The only pre-change baseline recorded per file is the providers suite: **27 passed** before this change (the T-001 red run), **42** in it now, the difference being the cases this change added. No before/after full-suite baseline was taken for this feature, so the suite totals are reported as observations, not as a delta. |
| T-005 | this document | Status, evidence, findings disposition and follow-ups, written after every command above ran. |

## Verification (RDD off — independent verification, not native review)

Three `gentle-ai-verify` runs, each on a named candidate, each read-only inside the
repository and doing its mutation work in a `/tmp` copy. Their reports are the evidence;
nothing below is smoothed over.

### V1 — `0d5de36..709a9c6`

Gate: backend **535 passed, 1 skipped**, `ruff` clean; frontend **25 files / 267**,
`tsc` clean. Six behavior probes through the real routers passed (cap boundary, padded
name, mixed-case built-ins, sentinel, `Groq` + `groq`, case-only rename, D9 intact on
`PUT /llm`). One candidate-caused defect, fixed in `a3e3288`:

- **F1 (fixed)** — the case-insensitive guard ran *before* the unchanged-name no-op, so
  renaming a legacy row named `Ollama` to its own name returned `409` where `main`
  returned `200`. Migration `0021` backfills exactly that row (its `notin_` is
  case-sensitive), and the pencil is the only rename affordance that row has.
- **F3 (fixed)** — `expect(PROVIDER_NAME_MAX_LENGTH).toBe(50)` asserted the constant
  against itself; nothing compared it with the backend. Replaced by the cross-language
  guard in `provider-name-mirror.test.ts`.
- **F6 (fixed)** — the dialog's cap case typed seven characters and claimed to test the
  cap. It no longer claims that, and a case types sixty and asserts the field holds
  fifty with the counter full.
- **Check that passed** — a legacy `Ollama` row is *not* broken by the case-insensitive
  guard: `isKnownProvider` stayed exact-match, so the row keeps its registry entry and
  its OpenAI-compatible routing, and only a *new* registration of that name is refused.
  The two mirrors cannot diverge on casing either (the verifier diffed every codepoint
  where Python `str.lower()` and JS `toLowerCase()` disagree — no single-ASCII-letter
  divergence).

### V2 — `a3e3288`

Gate green on the corrected candidate. The new mirror guard was mutation-tested in both
directions (frontend constant and backend constant, 50 → 48: both fail). The reorder was
re-probed with state read back after every request: own-name rename `200` and unchanged,
case-only change `409`, rename away `200`, reserved targets on a normal row all `409`,
and `_repoint_selected_provider` unreachable for a refused rename. Findings:

- **F1 (fixed in `8e7573f`)** — the guard's second case did not do what its comment
  promised: renaming the backend constant still failed with the unexplained `undefined`,
  because `toContain('NAME_MAX_LENGTH')` was satisfied by two other lines of the module.
- **F2 (fixed in `2e47993`)** — the guard covered 1 of the 3 hand-kept copies of the
  vocabulary; the settings surface's hand-typed union was the third.
- **F3 (accepted, and the deliberate direction)** — the reorder changed unknown-id +
  reserved-target from `409` to `404`. The verifier compared it against the pre-correction
  route and against the documented contract and judged `404` faithful: the reservation
  answers "what may a name be registered as", which is not a question about a row that
  does not exist. Pinned by `test_an_absent_row_outranks_a_reserved_target_name`.
- **F4 (accepted)** — the regression was reachable through the API but not through the
  dialog (`canSubmit` already excludes an unchanged name). The fix is still needed for
  non-UI callers, and the test drives the API, not the dialog.
- **F5 (accepted, not a hole)** — the sentinel is reserved by exact match, so
  `__ADD_CUSTOM_PROVIDER__` is creatable. Both languages compare exactly, so it cannot
  occupy the select's control slot.

### V3 — `8e7573f` (test-only commit; production files byte-identical to the parent)

Gate green; the mirror guard failed on every mutation tried (backend cap, backend list
member added, backend reorder, backend sentinel, renamed backend constant — with a
message naming the constant — and the frontend constant), each failing exactly one case.
The 404 pin was confirmed collected, passing three parametrized ids, and failing when the
guard is moved back before the row lookup. Findings:

- **F1 (accepted, and covered elsewhere)** — the guard mirrors *declarations*, not
  *enforcement*: setting the validator to `len(...) > 100` while leaving the constant at
  50 passes the guard. The gate still catches that change, because
  `test_invalid_names_are_rejected["a" * 51]` asserts the 422 — the guard and the API
  test cover the two halves.
- **F2 (fixed in `2e47993`)** — "every hand-kept vocabulary mirror" was an overclaim:
  `types/settings.ts` retyped the four names as a union. It is an alias of `KnownProvider`
  now, which removes the copy instead of adding a test that watches it.
- **F3 (fixed in `2e47993`)** — the list was compared as a sequence; the backend only
  tests membership and each side renders its own order, so a backend-only reorder was a
  false positive. Compared by membership now, with the reason in the comment.
- **F4 (fixed in `2e47993`)** — the new 404 pin's docstring called `403` "exists but is
  not reachable", which is not this codebase's contract.
- **F5 (accepted, cosmetic)** — the one-line vitest summary truncates a list diff to
  `…(3)`; the full diff below it names the drifted member. The custom-message assertions
  cover the constant-rename case, which was the one that read as a mystery.

## Follow-ups (not part of this change)

- **`customProviderNameSchema` is dead code.** It is imported only by its own test; the
  API layer takes the `z.infer` *type*, which is erased at runtime. Either parse through
  it in `custom-providers-api.ts` or delete it — a schema nothing runs makes its test
  green without evidence (V1 F2).
- **The 50 in `PUT /settings/llm` still measures the raw value**
  (`workspace_llm_config.py`), while the provider registry measures the trimmed one. The
  same padded name is accepted by one route and refused by the other, and the dialog's
  `maxLength` truncates the raw value on paste, so a padded paste silently loses
  characters (V1 F4).
- **`String(50)` is decorative in CI.** The suite runs on in-memory SQLite, which accepts
  a 200-character value into `VARCHAR(50)`; only the validators keep the bound. A
  Postgres-backed check (the skipped Docker test is the place) would make a validator
  regression fail somewhere (V1 F5).
- **The 409 → "already exists" message is coupled to the two guards staying in sync.** A
  reserved refusal that reached the request would be reported as a duplicate (V1 F7).
- **`llmConfigSchema.provider` retypes the same 50** (`schemas/workspace.ts`), and the
  `KNOWN_PROVIDERS` mirrors are guarded while nothing guards that one (V3 F2).
- **Near-duplicate names are now possible on purpose** (D2): `Groq` and `groq` are two
  providers. If that ever becomes a complaint, the fix is a visible warning in the dialog,
  not a silent lower-casing.

## Outcome

A workspace can register a provider under whatever name the vendor uses: `Groq`,
`My Gateway v2`, `Ünïcode`, up to 50 characters, stored exactly as typed — and the field
shows `(n/50)` while it does, so the limit is never a surprise. The two names that would
break something are still refused, one of them now in any casing, and each refusal names
its own rule.

The correction commit is the more useful part of the record: independent verification
found that the case-insensitive guard had closed a door on the one row shape migration
`0021` created — a legacy `Ollama` — and that is now answered before the reservation
without weakening it. Two guards that watched nothing were replaced by one that fails on
either side of the mirror, and a third copy of the vocabulary was deleted rather than
watched.

Nothing was pushed: the branch was landed locally at the user's explicit request and
the delivery decision beyond that is ordinary repository policy. RDD is off in this
clone, so no native review ran — the three independent verifications are the review
this candidate got.
