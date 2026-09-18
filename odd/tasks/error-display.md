# ODD Feature: error-display

> **Status**: in progress
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
| `KanbanBoard.tsx:214` | `if (loadError) return <ErrorDisplay …/>` — the **whole page**, replaced by a component that renders nothing: a blank screen, no message, no retry, no way back |
| `StoryForm.tsx:520` | A failed save shows nothing (no toast on this path either) |
| `TaskEditor.tsx:330` | A failed save shows nothing |
| `ExportPanel.tsx:161` | A failed task fetch shows nothing (the download path has its own toast) |
| `ExportPanel.tsx:172` | A failed download shows nothing beyond the toast |
| `StoryDetail.tsx:504` | The failed-extraction panel shows nothing (the toast covers this one) |

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

- **Status**: pending
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

- **Status**: pending
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

- **Status**: pending
- **Files to modify**: `frontend/src/components/react/__tests__/KanbanBoard.test.tsx`
- **What**: a case that fails a board load and asserts the user gets an announced error and
  a retry that refetches — the defect's user-visible form, at the call site where it is
  worst.
- **Acceptance**: `vitest run` passes; the case fails against the placeholder.
- **Depends on**: T-001
- **Allowed edit surfaces**: `frontend/src/components/react/__tests__/KanbanBoard.test.tsx`

### T-004 — Verification gate

- **Status**: pending
- **What**: run the full repo gate and record it; delegate an independent verification that
  enumerates every `ErrorDisplay` call site and checks each one now renders something
  reachable, and that the accessibility claims hold.
- **Commands**: `cd frontend && node_modules/.bin/vitest run` and
  `node_modules/.bin/tsc --noEmit`; `cd backend && .venv/bin/pytest -q`,
  `.venv/bin/ruff check src tests`, `.venv/bin/ruff format --check src tests`.
- **Acceptance**: every command passes and the counts are recorded.
- **Depends on**: T-001, T-002, T-003

### T-005 — Close the feature

- **Status**: pending
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
| T-001 | | |
| T-002 | | |
| T-003 | | |
| T-004 | | |
| T-005 | | |

## Follow-ups (not part of this change)

- `StoryForm` and `TaskEditor` have no toast channel for a failed save, so `ErrorDisplay`
  is their only feedback (it now renders). Adding a toast is a separate decision.
- `extractErrorInfo` is exported and used by nobody.
- `frontend/.vercel/output` and `dist` hold the pre-revive bundle until a rebuild.
