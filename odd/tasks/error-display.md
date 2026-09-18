# ODD Feature: error-display

> **Status**: done — two commits on `feat/error-display` (`34e23aa`, `15711ec`), plus the
> evidence commit that carries this line (three against the parent branch); nothing was
> pushed. Receipt-driven development is **off** in this clone, so no native review ran; one
> independent verification did, recorded below with its findings and their disposition.
> **Created**: 2026-06-30
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/error-display`, stacked on `feat/normalize-blank-llm-fields`.
> **Receipt-driven development**: off in this clone.

## Problem

Slice 3 of the review follow-ups. `ErrorDisplay` renders `null` and has since `353224f`
("simplify ErrorDisplay to placeholder for future use"), so every error surface that uses
it shows **nothing**:

| Call site | What the user sees today |
|-----------|--------------------------|
| `KanbanBoard.tsx` | A failed load shows the **empty board with no explanation**: its error branch was `if (loadError)` on local state set from a `.catch()` on a promise the store never rejects |
| `StoryForm.tsx:520` | A failed save shows nothing (no toast on this path either). Reachable: `storyStore` rethrows |
| `TaskEditor.tsx:330` | A failed save shows nothing. Reachable: `taskStore.updateTask` rethrows |
| `ExportPanel.tsx:161` | A failed task fetch shows nothing (the download path has its own toast) |
| `ExportPanel.tsx:172` | A failed download shows nothing beyond the toast |
| `StoryDetail.tsx:504` | The failed-extraction panel shows nothing (the toast covers this one) |

### Correction to this plan, found while implementing it

The row for `KanbanBoard` was wrong when this document was written, and the mistake was in
the direction of overstating the symptom. The claim was "a failed load replaces the whole
page with a blank screen". What is actually true: the branch could not be reached at all.
`fetchTasksForWorkspace` **never rejects** (`taskStore.ts` catches and records
`{ error }`), and the board listened on a local `loadError` set from a `.catch()` on that
promise, while never reading the store's `error`. So the worst surface had *two* defects —
the component rendered nothing **and** the state it was waiting for was unreachable — and
the user's actual experience was a silently empty board.

The implementation fixes both: the board reads the store's `error` (the channel that is
actually signalled), the dead state and its unmatchable `.catch()` are gone, and the retry
refetches (which clears the recorded error before it starts). The test drives the
reachable path, so it would have failed against either half of the old arrangement.

The other five call sites were re-checked against their stores and are reachable as the
table says: `storyStore.createStory` and `taskStore.updateTask` both rethrow.

The component is not broken by accident: it was parked deliberately, and the file still
holds the `BackendError` interface plus `formatRawDetail`, `copyToClipboard` and
`extractErrorInfo` — written and used by nobody. Every call site already passes
`friendlyMessage`, `rawDetail`, `status`, `errorCode`, `onRetry`/`retryLabel`,
`onDismiss` and `locale`, so the contract is complete and unused.

The prior implementation lives in `dad9039` (211 lines): destructive card, status +
errorCode, dismiss, and a collapsible raw response with a copy button. It does **not**
render `retryLabel`/`onRetry`, so reviving it verbatim would silently drop the retry
affordance all six call sites already pass.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Revive or rewrite | **Revive `dad9039`** and add what the current interface already promises: the retry action. The prior design was reviewed once in this repo's own history; deviating further would be a rewrite for no gain. |
| D2 | Kanban's full-page case | **No navigation escape.** The revived component gives the page a message and a retry, which is what the user needs (approved by the user). |
| D3 | The collapsible | Use the repo's `Collapsible` primitive (a thin `@base-ui/react` wrapper, already used in `nav-main.tsx`) instead of the prior hand-rolled toggle, so the open state and its `aria-expanded` come from the primitive. |
| D4 | Accessibility | `role="alert"` on the container: this banner appears in response to a failure and must be announced. The raw-detail region keeps `role="region"` and takes its name from the already-localized `errorDisplay.raw_response` instead of the prior hardcoded English `aria-label`. The dismiss button — which had **no** accessible name — gets one. |
| D5 | `friendlyMessage` ownership | Unchanged: callers pass a message they own (translated or from the API). The component never invents copy for the message itself, only for its own chrome. |

## Non-goals

- No change to any call site's logic, props or error handling: this is the component.
- No new error-handling behaviour anywhere (e.g. no toast added to `StoryForm`).
- No redesign: same destructive card, same layout as `dad9039`.
- No navigation escape for the Kanban case (D2).
- No change to `extractErrorInfo`'s shape (it is exported and unused; it stays for parity).

## Established facts (verified)

- The placeholder is `frontend/src/components/react/ErrorDisplay.tsx` (125 lines), whose
  body is `return null;` with a comment saying it was parked for future implementation.
- The prior implementation is `dad9039:frontend/src/components/react/ErrorDisplay.tsx`.
- Every i18n key it needs already exists in both locales:
  `errorDisplay.show_details|hide_details|raw_response|copy|copied`, and `common.retry`.
  The only missing string is an accessible name for the dismiss button.
- `Collapsible`/`CollapsibleTrigger`/`CollapsibleContent` wrap `@base-ui/react/collapsible`;
  `nav-main.tsx` uses them with `className="group/collapsible"` on the root and
  `group-data-open/collapsible:rotate-90` on the chevron.
- `KanbanBoard.tsx:214` is a top-level `return`, so its error state replaces the board.
- There is no test file for `ErrorDisplay` today.

## Tasks

### T-001 — Revive the component with the retry it already promises

- **Status**: done (commit `34e23aa`)
- **Files to modify**: `frontend/src/components/react/ErrorDisplay.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`
- **What**: bring back the `dad9039` render (D1), add a retry button driven by
  `onRetry`/`retryLabel` (falling back to `common.retry`), swap the hand-rolled toggle for
  the `Collapsible` primitive (D3), and fix the two accessibility gaps (D4). One new key,
  `errorDisplay.dismiss`, in both locales, neutral Spanish.
- **Acceptance**: `node_modules/.bin/tsc --noEmit` clean and `vitest run` green.
- **Allowed edit surfaces**: `frontend/src/components/react/ErrorDisplay.tsx`,
  `frontend/src/i18n/en.json`, `frontend/src/i18n/es.json`

### T-002 — Test the component in both directions

- **Status**: done (commit `34e23aa`)
- **Files to modify**: `frontend/src/components/react/__tests__/ErrorDisplay.test.tsx` (new)
- **What**: pin what must render and what must not: message, `HTTP n` and the error code
  when present; the retry button only when `onRetry` is given, calling it once; dismiss
  only when given; the details toggle is closed initially, opens to the formatted raw
  detail, and the copy button reports the copy; no toggle at all when there is no raw
  detail; an object detail is pretty-printed and an array detail is joined.
- **Acceptance**: `vitest run` passes; the suite fails if the component returns `null`
  again (the red run).
- **Depends on**: T-001
- **Allowed edit surfaces**: `frontend/src/components/react/__tests__/ErrorDisplay.test.tsx`

### T-003 — Pin the blank page that started this

- **Status**: done (commit `34e23aa`, and it grew: see the correction above — the case now
drives the reachable channel, and the call site had to be fixed for it to pass)
- **Files to modify**: `frontend/src/components/react/__tests__/KanbanBoard.test.tsx`
- **What**: a case that fails a board load and asserts the user gets an announced error and
  a retry that refetches — the defect's user-visible form, at the call site where it is
  worst.
- **Acceptance**: `vitest run` passes; the case fails against the placeholder.
- **Depends on**: T-001
- **Allowed edit surfaces**: `frontend/src/components/react/__tests__/KanbanBoard.test.tsx`

### T-004 — Verification gate

- **Status**: done (one independent `gentle-ai-verify` run over `edfdf95..34e23aa`; its
  findings are fixed in the commit below, see the verification section)
- **What**: run the full repo gate and record it; delegate an independent verification that
  enumerates every `ErrorDisplay` call site and checks each one now renders something
  reachable, and that the accessibility claims hold.
- **Commands**: `cd frontend && node_modules/.bin/vitest run` and
  `node_modules/.bin/tsc --noEmit`; `cd backend && .venv/bin/pytest -q`,
  `.venv/bin/ruff check src tests`, `.venv/bin/ruff format --check src tests`.
- **Acceptance**: every command passes and the counts are recorded.
- **Depends on**: T-001, T-002, T-003

### T-005 — Close the feature

- **Status**: done (this document's commit)
- **Depends on**: T-004

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| A call site passes a prop the revived component ignores | That surface stays silently degraded | Six call sites; T-003 pins the worst one, and the verification enumerates all six against the component's interface |
| `role="alert"` on a container that also holds a button | Some screen readers announce the whole subtree | The container is short; the alternative (no announcement) is the defect being fixed. The details region stays collapsed by default, so the announcement is bounded |
| The `Collapsible` primitive renders a button inside a paragraph or vice versa | Invalid nesting warnings in the console | The trigger is `render={<Button/>}`, the same composition `nav-main.tsx` uses |
| Reviving `dad9039` brings its dead `"(no detail provided)"` string | Confusion | It is unreachable: `hasDetail` gates the whole details block. Kept for parity, noted here |

## Evidence log

| Task | Commit | Outcome |
|------|--------|---------|
| T-001 | `34e23aa` | The `dad9039` render is back, with the retry the interface promised (`retryLabel` ?? `common.retry`), the `Collapsible` primitive instead of the hand-rolled toggle, `role="alert"` scoped to the message block, a localized name for the raw-detail region, an accessible name for the dismiss button (it had none) and an announced copied state. One new key, `errorDisplay.dismiss`, in both locales. The raw-detail block was extracted into its own `RawDetail` component (its copy state belongs to it), and the trivial `copyToClipboard` wrapper was inlined. |
| T-002 | `34e23aa` | `ErrorDisplay.test.tsx`, **17 cases**: message, status/code combinations, retry only when given (and with the caller's label), dismiss only when given, no toggle without a detail, collapsed-then-disclosed with `aria-expanded`, label swap, object pretty-printing, array joining, and a copy verified by reading the clipboard back the way a paste would. Red run against the placeholder: **13 of 21 failed**, the 8 that passed being the "must not render" assertions that pass trivially against `null`. |
| T-003 | `34e23aa` | The Kanban state was fixed at the call site (see the correction above) and the case now drives the store's `error` channel, asserts the columns are gone while the failure is shown, and asserts the retry brings the board back. Whole frontend suite **31 files / 369 passed**, `tsc` exit 0; backend untouched, **631 passed, 1 skipped**. |
| T-004 | `15711ec` | Gate and independent verification, below. Three of its findings were worth fixing; the rest are recorded. |
| T-005 | this document | Status, evidence, the verification record and the dispositions. Final gate on the closed candidate: frontend **31 files / 372 passed**, `tsc` exit 0; backend **631 passed, 1 skipped**, `ruff` clean. |

## Verification (RDD off — independent verification, not native review)

One `gentle-ai-verify` run over `edfdf95..34e23aa`, read-only, probes in `/tmp` copies. Gate
it observed: frontend **31 files / 369 passed**, `tsc` exit 0; backend **631 passed, 1
skipped**, `ruff check` and `ruff format --check` clean over 211 files.

What it confirmed:

- **All six call sites are reachable**, each with the channel that sets its state and a probe
  that fired it. It also proved the premise of the correction above independently: awaiting
  `fetchTasksForWorkspace` with a rejecting API mock returns `"RESOLVED"` while
  `store.error !== null`, so the old `.catch()` could never run.
- **No prop is silently dropped**: all eight declared props were exercised and each produced
  observable output.
- **The Kanban defect reproduces**: with only `KanbanBoard.tsx` reverted, both the new test
  and three of its four probes fail, and the failing DOM is the empty-board copy with no alert.
- **The label swap works in real CSS**, not just in jsdom: it compiled the project's own
  Tailwind and read the emitted rules (`.group-data-open\/collapsible\:hidden` → `display:none`,
  `\:inline` → `display:inline`) and confirmed Base UI sets `data-open` on the root, so the
  specificities and source order resolve the way the markup assumes.
- **Nothing else relied on the removed local state** (`grep` for `loadError` finds only the new
  alias and an unrelated i18n key), and no affordance was lost by dropping `onDismiss` there:
  the error branch never rendered, so there was nothing to dismiss.
- **i18n parity** 664/664 with `errorDisplay.dismiss` in both locales, and the previously
  unreferenced `errorDisplay.copied` now has a consumer.

### Findings and disposition

- **F1 (fixed in the corrections commit) — candidate-caused, trivial.** `hasDetail` compared the
  formatted text against `'(no detail provided)'`, so a caller whose detail *is* that literal
  text had it silently dropped. The gate now tests `rawDetail` for absence and the formatted
  text for emptiness, which is the honest pair.
- **F2 (fixed in the corrections commit) — candidate-caused, trivial.** `rawDetail=""` opened a
  disclosure onto an empty panel; the same change closes it. Both edge cases now have tests,
  taken from the verifier's own probes.
- **F3 (fixed in the corrections commit) — candidate-caused consequence, low.** The revived
  retry showed the **empty-board copy** while the refetch was in flight: the spinner guard is
  `initialLoad && loading`, and a retry starts with `initialLoad` already false. The retry now
  puts `initialLoad` back, mirroring what `ExportPanel` does per attempt. My first test for it
  passed for the wrong reason — the mock did not clear the stored error, so the retry fell back
  onto the error branch and the assertion was vacuous. Corrected, the test fails without the fix.
- **F5 (fixed in the corrections commit) — candidate-caused, low, unverifiable here.**
  `role="alert"` carries implicit `aria-atomic="true"`, and it wrapped the disclosure, so
  expanding the detail could re-announce the whole card including the raw JSON blob. The alert
  now wraps only the message block.
- **F4 (recorded) — candidate-caused information gap, low.** `KanbanBoard` and
  `ExportPanel:161` render the store's `error`, which is a message: no status, code or raw body
  there, unlike the other four sites. Pre-existing store design; recorded as a follow-up.
- **F7 (recorded, and the most severe thing the review found anywhere) — pre-existing, low in
  practice but a real hazard.** `TaskEditor.tsx:49` selects `s.tasks[task.storyId] ?? []`, a new
  array per snapshot, which makes `useSyncExternalStore` warn `The result of getSnapshot should
  be cached` and can loop. Masked today because other pages populate `tasks[storyId]` first.
  Unrelated to this slice, so it is recorded rather than bundled.
- **F6, F8 (accepted, informational).** Five tests are negative-only and pass vacuously; that is
  the conditional-rendering contract, and twelve others have teeth. `extractErrorInfo` and the
  new `data-slot` remain unused.
- **Not verified:** a real browser / assistive-technology pass (no Playwright or Puppeteer driver
  installed), and Astro's SSR output for the alert (a build cannot run in a `/tmp` copy; the
  no-alert-on-initial-load conclusion rests on `client:load` plus the stores' null initial
  state).

## Follow-ups (not part of this change)

- **`TaskEditor.tsx:49` has a latent infinite loop** (found by the verification, pre-existing and
  unrelated to this change): `useTaskStore((s) => s.tasks[task.storyId] ?? [])` returns a new
  `[]` on every snapshot, so `useSyncExternalStore` reports `The result of getSnapshot should
  be cached` and React can loop (`Maximum update depth exceeded`). It is masked today because
  `StoryDetail`/`KanbanBoard` populate `tasks[storyId]` first. The fix is a module-level frozen
  empty array instead of a fresh literal, plus a test that mounts the editor with an unseeded
  story.
- **The store flattens the failure.** `TaskState.error` is `string | null`, so the two call
  sites that render the store's error (`KanbanBoard`, `ExportPanel:161`) cannot show the
  `status`, `errorCode` or raw body the other four sites show. Keeping the structured error in
  the store would let them; that is a store-contract change, not a component one.
- `StoryForm` and `TaskEditor` have no toast channel for a failed save, so `ErrorDisplay` is
  their only feedback (it now renders). Adding a toast is a separate decision.
- `extractErrorInfo` is exported and used by nobody (it predates `dad9039`), and the new
  `data-slot="error-display"` hook has no consumer.
- Five of the component's tests are negative-only and pass vacuously against a component that
  renders nothing; they pin the conditional-rendering contract rather than proving the card
  draws. The other twelve fail without it.
- A real-browser / assistive-technology check (accessible names, live-region announcement, the
  Tailwind-driven label swap) was not possible here: no Playwright or Puppeteer driver is
  installed. What was verified instead: `dom-accessibility-api` for the names, the project's
  own compiled Tailwind CSS for the swap, and Base UI's source for `data-open`.
- `frontend/.vercel/output` and `dist` hold the pre-revive bundle until a rebuild.
