# ODD Feature: rich-store-errors

> **Status**: done and landed on `main` @ `1532552` — three commits from `137f804`: `c9878b3`
> (the change and its tests), `faa60d7` (the record) and `1532552` (the answer to the verification,
> including the coverage it proved was missing). Branch deleted, `main` re-gated, **not pushed**.
> Receipt-driven development is **off** in this clone, so no native review ran; an independent
> verification did, and it found a real hole in this change rather than only in its prose.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/rich-store-errors`.

## Process correction: the review switch was on

**This record said receipt-driven development was "off in this clone", and for the second half of
this session that was false.** The switch read `off (decided by default)` when the session began, and
was turned on globally mid-session — `~/.gentle-ai/state.json` records `rdd_mode = 'on'` with
`rdd_mode_recorded_at = 2026-09-19T18:49:02Z`. This record's line was copied forward from the earlier
features without re-checking it, which is **the same defect this batch spent the day removing**: a
claim about state, written once and never re-read.

So native review was the expected path for this candidate and it did not run. Two independent
verifications did, and their findings are recorded below — every one of them found something material.
Whether that is an adequate substitute is the maintainer's call, not this record's.

It could not have run from the parent session regardless: the `gentle_review` facade answers
`native-status-package-binary-missing` here, while a subagent's context reached the lifecycle and
returned an unresolved provider consent envelope for the last candidate. The recovery is
`node scripts/install-gentle-ai.mjs` from the installed package directory, which is a maintenance
action rather than something this session takes on its own.

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
| D5 | `workspaceStore.error` | **Removed** — the declaration, its initial value, the four writes that cleared it (`set({ …: true, error: null })`) and the four catch writes: ten mentions, zero readers. |
| D6 | Coverage | The two flattening expressions and `ExportPanel`'s error branch — the latter entirely untested — get assertions. |
| D7 | `rawDetail` semantics | The old `ErrorDisplay.extractErrorInfo` put `detail` in `rawDetail`; the unified normaliser puts the whole `rawError.rawBody` there. Deliberate: the raw body is a superset of `detail` (in `api.ts`, `detail` is a projection of the body), it is what the disclosure panel is for, and it is what the extraction path already used. **One consequence, measured rather than assumed**: `ExportPanel` deliberately supplies its own translated headline and passes `rawDetail ?? friendlyMessage`, so for a failure that *did* carry a body the store's own sentence is rendered nowhere on that page — the body is shown instead. Nothing is lost (the body contains what the message summarised, and the badge carries the status and code), but the sentence is not preserved, and saying otherwise would be the kind of unverified claim this batch exists to remove. |

## What the change actually touched, including what I underestimated

The blast radius of D5 was larger than the exploration predicted, and it is worth writing down
rather than discovering again:

- **18 test state resets** across 10 files set `error: null` inside a `useWorkspaceStore.setState`
  block and had to drop the key: `projectStore.unit.test.ts` (4), `storyStore.unit.test.ts` (3),
  `taskStore.unit.test.ts` (3), `workspaceStore.unit.test.ts` (2), `team-switcher.test.tsx`,
  `ExportPanel.test.tsx`, `KanbanBoard.test.tsx`, `StoriesList.test.tsx`, `StoryDetail.test.tsx`,
  `WorkspaceSettings.test.tsx`. The type checker is what makes this safe: every one was found by
  `tsc` (18 × `TS2353`, plus 3 × `TS2322` for the seeds that carried a string), and none of them
  silently changed behaviour.
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
| Broken state (before the test updates) | `pnpm exec tsc --noEmit` | **21 errors** naming every site that still set the removed key (18 × `TS2353`, 3 × `TS2322`) |
| Failing tests (before the test updates) | `pnpm vitest run` | **2 files failed, 7 tests failed** of 394 — the 6 project-store scope-guard assertions plus KanbanBoard's |
| Full suite | `pnpm vitest run` | **35 files, 403 passed** (394 before, +9 new, plus 3 more after the verification) |
| Types | `pnpm exec tsc --noEmit` | exit 0 |
| New coverage | — | `error-info.test.ts` (6), `ExportPanel` error branch (1), `projectStore` rich failure (2) |
| Audit of the bulk edit | re-derived from `main` with a corrected parser | exactly the 18 intended sites, none other |

Two of the new assertions are the ones that make the change observable rather than merely typed:

- `KanbanBoard.test.tsx` now seeds `status: 503` and `errorCode: 'BOARD_UNAVAILABLE'` and asserts
  the alert shows `HTTP 503` **and** the code — impossible before, which is exactly what the
  deleted comment said.
- `error-info.test.ts` pins that a look-alike object (`{ detail, status, message }`) is **not**
  treated as an `ApiRequestError`, guarding the loose classification the old copy allowed.

## Independent verification

Ran over `137f804..faa60d7`, read-only. Four of seven claims confirmed outright; the rest came
back with corrections, one of which was a real hole in this change rather than in its prose.

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| V1 | **medium** | **Half the change was unguarded.** Mutating *both* `taskStore` catch sites to a message-only `ErrorInfo` left the whole suite green (35 files / 403 passed) and `tsc` clean — no test anywhere asserted `useTaskStore.getState().error`. D6 claimed the two flattening expressions had assertions; they did not. | **Fixed** — three tests in `taskStore.unit.test.ts` now drive both paths with an `ApiRequestError` and assert the status, the code and the raw body. Re-ran the verifier's own mutation: **3 tests fail** on it now. The doc's claim matches the code again. |
| V2 | medium | The recorded numbers were wrong: **18** sites across **10** files, not 16 across 8 (`ExportPanel.test.tsx` and `KanbanBoard.test.tsx` were omitted), and **21** `tsc` errors, not 20 — the same omission caused both. | **Fixed** — corrected here. The conclusion the audit existed for does hold: nothing removed outside a `useWorkspaceStore.setState` block, and no block still sets `error`. |
| V3 | low | `ExportPanel` renders the store's `friendlyMessage` nowhere when the failure carried a body: `rawDetail ?? friendlyMessage` only falls back on `null`/`undefined`. | **Fixed in the record**, no code change: D7 now states the consequence and why it is acceptable. The verifier confirmed the disclosure panel still renders and that the check this replaced would have been worse. |
| V4 | low | D5 said "its four writes"; the removal also took the four `error: null` clears from the operation starts — ten mentions in total. | **Fixed** — D5 states all of them. |
| V5 | low, out of range | `workspaceStore.ts:85` sets `loading: true` on the **success** path, so the flag never clears. | **Recorded as a follow-up** — see below. Not introduced here, and not this feature's subject. |
| V6 | low, out of range | `team-switcher.tsx:75-78` swallows a create-workspace failure with `catch { // error handled by store }`, and the store no longer records anything either. | **Recorded** — the silent-failure class is wider than the follow-up below claimed. |
| V7 | info | `odd/tasks/error-display.md:243` said `extractErrorInfo` "predates `dad9039`"; that commit created both the file and the function. | **Fixed** — the line now says it was born dead there, and that the function is gone. |
| V8 | info | Mis-indentation in the object literal this change added to `KanbanBoard.test.tsx`. | **Fixed**. |

Two mutation results are worth keeping because they say what the tests are for: the `error-info`
suite catches a return to shape-based classification (2 of 6 tests fail), and the `KanbanBoard` and
`ExportPanel` assertions each fail when the consumer stops passing `status`/`errorCode` — the
latter all three, because `role="alert"` is not atomic over the disclosure panel. The four
remaining `error-info` tests are characterisation of `Error`/string/fallback inputs rather than
guards of this change, which is honest rather than a defect.

Also confirmed by reconstruction: every non-`error` statement in every `catch` of all three stores
is byte-identical before and after (catch counts, `saving: false` counts, `loading: false` counts
and `throw` counts all unchanged; the scope guards, the request-sequence tokens and the `saving`
writes left deliberately *outside* the scope guards are all intact). That was the worst plausible
outcome of this refactor and it did not happen.

## Follow-ups this surfaced, recorded rather than bundled

1. **A user with no workspaces cannot create one.** `workspaceStore.ts:85` sets `loading: true` on
the success path — almost certainly a typo for `false` — and `team-switcher.tsx:106` renders a
`LoaderCircle` skeleton from that flag. The reachable consequence: with `teams.length === 0` and
no persisted `currentWorkspace`, the component renders the "loading" branch **instead of** the
"New Workspace" button at `:126-142`. That is exactly the state of a freshly registered user who
has not been added to a team yet, which ADR-003 makes a normal state. Byte-identical before and
after this change, so it is pre-existing. It is a one-line fix with a test, and it deserves its
own slice rather than riding along here.
2. **Silent failure is a class, not an instance.** `fetchWorkspaces` failing is silent (recorded
above), and `team-switcher`'s create-workspace failure is silent too, by a comment that says the
store handles it — while the store no longer records anything. Fixing the first without the second
would leave half the class behind, and the second needs a decision about where the failure should
appear, which is a product question.

## Tasks — all closed

- [x] Explore the exact reader set of each store's `error` before changing any type.
- [x] Define one `ErrorInfo` shape and one normaliser in `lib/`.
- [x] Route every catch through it; delete the duplicated normaliser.
- [x] Remove `workspaceStore.error` and its writes.
- [x] Update `KanbanBoard`, `ExportPanel` and `ProjectsList`; delete the comment recording the loss.
- [x] Update the tests that the type change invalidated, and add the missing coverage.
- [x] Run `pnpm exec tsc --noEmit` and `pnpm vitest run`.
- [x] Work-unit commit on the feature branch (`c9878b3`, plus the record at `faa60d7`).
- [x] Independent verification — 4/7 confirmed outright; V1 (a real hole) fixed and re-mutated to
      prove it, V2/V4 corrected here, V3 recorded, V5–V7 fixed or recorded, V8 fixed.
- [x] Fast-forward into `main`, delete the branch, re-gate — `main` @ `1532552`, 35 files /
      406 tests passed and `tsc --noEmit` exit 0 re-run **after** the merge.
