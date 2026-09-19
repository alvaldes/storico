# ODD Feature: rich-store-errors

> **Status**: done — commit (the fix, its tests and the record) on `fix/rich-store-errors`, off
> `main` @ `137f804`, not pushed. Receipt-driven development is **off** in this clone, so no
> native review ran; the independent verification is recorded below.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/rich-store-errors`.

## Problem

Three stores flattened a thrown error to a `string` at the catch boundary, discarding everything
the richer type carried:

| Site | Type declaration | Flattening |
|------|------------------|------------|
| `frontend/src/stores/taskStore.ts` | `:50` `error: string \| null;` | `:173`, `:401` |
| `frontend/src/stores/projectStore.ts` | `:28` `error: string \| null;` | `:71`, `:96`, `:118`, `:140` |
| `frontend/src/stores/workspaceStore.ts` | `:23` `error: string \| null;` | `:97`, `:123`, `:140`, `:158` |

All of them did `const message = err instanceof Error ? err.message : '<fallback>'`. The API layer
throws `ApiRequestError` (`frontend/src/lib/api.ts:17-98`), which holds `status`, `statusText`,
`errorCode`, `currentState`, `attemptedState`, `allowedTransitions`, `detail` and
`rawError.rawBody`. Flattening dropped all of it.

The loss was already admitted in the code. `KanbanBoard.tsx`:

```tsx
// The store records a message rather than the `ApiRequestError`, so there is no
// status, code or raw body to disclose on this page.
```

Consequences: `ErrorDisplay` could not render its `HTTP n` badge or the raw-response panel
(`ErrorDisplay.tsx:167-173`, `:190`), and no consumer could branch on a machine code the way the
extraction slice already did (`categorizeExtractionError`).

The asymmetry was internal to one file: the **same** `taskStore` kept a rich
`ExtractionErrorInfo` for the extraction slice while flattening the workspace slice.

## Two normalisers, one of them loose

The audit that preceded this change found the duplication that caused the drift:

- `extractExtractionErrorInfo` (`taskStore.ts:123`) used `err instanceof ApiRequestError` and
  delegated to `toErrorInfo()`.
- `extractErrorInfo` (`ErrorDisplay.tsx:222`) — **dead since it was written** in `dad9039`, with
  no caller in any commit — classified by shape instead: `'detail' in err && 'status' in err`.
  Any object with those two keys satisfied it, and everything else about the object was ignored.

Unifying them was therefore not just tidying: it is what removes the loose classification.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Where the shared shape and the normaliser live | A new `frontend/src/lib/error-info.ts`. A store normalising errors must not import a React component to do it, and the helper was in `ErrorDisplay.tsx` only because that is where it happened to be written. |
| D2 | The normaliser | One function. `ApiRequestError` matched **by class, first**, delegating to `toErrorInfo()`; then `Error`; then `string`; then a fallback. A `fallbackMessage` parameter lets a caller with its own user-facing name keep it without re-implementing the rest. |
| D3 | `TaskState.error` and `ProjectState.error` | Both become `ErrorInfo \| null`, matching what the extraction slice already stored. |
| D4 | `ExtractionErrorInfo` | Deleted as a name; `ExtractionState.error` uses `ErrorInfo`. Two names for one shape is the drift this feature is about. |
| D5 | `workspaceStore.error` | **Removed**, with its four writes and its initial value: four writes, zero readers. |
| D6 | Coverage | The two flattening expressions and `ExportPanel`'s error branch — the latter entirely untested — get assertions. |
| D7 | `rawDetail` semantics | The old `ErrorDisplay.extractErrorInfo` put `detail` in `rawDetail`; the unified normaliser puts the whole `rawError.rawBody` there. Deliberate: the raw body is what the disclosure panel is for, and it is what the extraction path already used. |

## What the change actually touched, including what I underestimated

The blast radius of D5 was larger than the exploration predicted, and it is worth writing down
rather than discovering again:

- **16 test state resets** across 8 files set `error: null` inside a `useWorkspaceStore.setState`
  block and had to drop the key: `workspaceStore.unit.test.ts` (2), `storyStore.unit.test.ts` (3),
  `taskStore.unit.test.ts` (3), `projectStore.unit.test.ts` (4), `team-switcher.test.tsx`,
  `StoryDetail.test.tsx`, `WorkspaceSettings.test.tsx`, `StoriesList.test.tsx`. The type checker
  is what makes this safe: every one was found by `tsc`, and none of them silently changed
  behaviour.
- **Three dead imports surfaced**, all pre-existing: `ExtractionErrorInfo` in `StoryDetail.tsx`
  (imported and never used — so the fix was to delete the import, not to repoint it),
  `api` in `KanbanBoard.test.tsx`, and — created by this change — `ApiRequestError` and
  `RawBackendError` in `taskStore.ts` once the old normaliser was gone.
- **A mistake I made and repaired**: the mechanical deletion of those 16 lines was done with a
  line-based script that tracked "inside a `useWorkspaceStore.setState` block" with a flag. A
  *single-line* `setState({ … })` never closed the flag, so it stayed set for the rest of the
  file and the script deleted an `error: null` from an `ExtractionState` literal 12 lines later.
  `tsc` caught it (the field is required there). Lesson: a line-based state machine is the wrong
  tool for brace-structured code, and a scripted bulk edit needs an audit that re-derives the
  change from the original revision rather than trusting the script's own bookkeeping. The repair
  and a full re-derived audit of all 16 sites are both recorded here.

## The follow-up this leaves behind

`fetchWorkspaces` failing is **silent**, and it was equally silent before: the catch recorded the
failure in `workspaceStore.error`, which no component ever read, and now it records nothing while
still clearing `loading`. Removing the dead field did not create that gap, it exposed it. It is
the same class of defect as the previous batch's unreachable Kanban error branch, and it needs its
own slice — surfacing the failure is new behaviour, not a rename.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| The duplication | `grep -rn "extractErrorInfo\|extractExtractionErrorInfo"` at `main` | two near-identical normalisers; the `ErrorDisplay` one with **zero** callers in any commit |
| Broken state (before the test updates) | `pnpm exec tsc --noEmit` | **20 errors** naming every site that still set the removed key |
| Failing tests (before the test updates) | `pnpm vitest run` | **2 files failed, 7 tests failed** of 394 — the 6 project-store scope-guard assertions plus KanbanBoard's |
| Full suite | `pnpm vitest run` | **35 files, 403 passed** (394 before, +9 new) |
| Types | `pnpm exec tsc --noEmit` | exit 0 |
| New coverage | — | `error-info.test.ts` (6), `ExportPanel` error branch (1), `projectStore` rich failure (2) |
| Audit of the bulk edit | re-derived from `main` with a corrected parser | exactly the 16 intended sites, none other |

Two of the new assertions are the ones that make the change observable rather than merely typed:

- `KanbanBoard.test.tsx` now seeds `status: 503` and `errorCode: 'BOARD_UNAVAILABLE'` and asserts
  the alert shows `HTTP 503` **and** the code — impossible before, which is exactly what the
  deleted comment said.
- `error-info.test.ts` pins that a look-alike object (`{ detail, status, message }`) is **not**
  treated as an `ApiRequestError`, guarding the loose classification the old copy allowed.

## Tasks — all closed

- [x] Explore the exact reader set of each store's `error` before changing any type.
- [x] Define one `ErrorInfo` shape and one normaliser in `lib/`.
- [x] Route every catch through it; delete the duplicated normaliser.
- [x] Remove `workspaceStore.error` and its writes.
- [x] Update `KanbanBoard`, `ExportPanel` and `ProjectsList`; delete the comment recording the loss.
- [x] Update the tests that the type change invalidated, and add the missing coverage.
- [x] Run `pnpm exec tsc --noEmit` and `pnpm vitest run`.
- [x] Work-unit commit on the feature branch.
- [ ] Independent verification — **pending**.
- [ ] Fast-forward into `main`, delete the branch, re-gate — **pending**.
