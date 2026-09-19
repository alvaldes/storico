# ODD Feature: rich-store-errors

> **Status**: planning — no commit, no evidence yet.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/rich-store-errors` (to be created off `main` @ `6174f5a`).
> **Receipt-driven development**: off in this clone.

## Problem

Three stores flatten a thrown error to a `string` at the catch boundary, discarding everything
the richer type carries:

| Site | Type declaration | Flattening |
|------|------------------|------------|
| `frontend/src/stores/taskStore.ts` | `:50` `error: string \| null;` | `:173`, `:401` |
| `frontend/src/stores/projectStore.ts` | `:28` `error: string \| null;` | `:71`, `:96`, `:118`, `:140` |
| `frontend/src/stores/workspaceStore.ts` | `:23` `error: string \| null;` | `:97`, `:123`, `:140`, `:158` |

All of them do `const message = err instanceof Error ? err.message : '<fallback>'`. The API
layer throws `ApiRequestError` (`frontend/src/lib/api.ts:17-98`), which holds `status`,
`statusText`, `errorCode`, `currentState`, `attemptedState`, `allowedTransitions`, `detail`
and `rawError.rawBody`. Flattening drops all of it.

The loss is already visible in the product and already admitted in the code. `KanbanBoard.tsx:222-223`:

```tsx
// The store records a message rather than the `ApiRequestError`, so there is no
// status, code or raw body to disclose on this page.
```

Consequences: `ErrorDisplay` cannot render its `HTTP n` badge or the collapsible raw-response
panel (`ErrorDisplay.tsx:138-141`, `:167-173`, `:190`), and no consumer can branch on a machine
code the way the extraction slice already does via `categorizeExtractionError`
(`taskStore.ts:112`, `:114`).

The asymmetry is internal to one file: the **same** `taskStore` keeps a rich
`ExtractionErrorInfo` for the extraction slice (`:29-43`, `:123-143`) while flattening the
workspace slice.

Two pieces of dead weight are entangled with this and are decided here rather than left:

- `extractErrorInfo` (`frontend/src/components/react/ErrorDisplay.tsx:222-265`) is exported and
  referenced by **nothing** — including no test — and git shows it was added in `dad9039` with
  no caller ever, so it is dead **from birth**, not orphaned by a removal.
- `workspaceStore.error` is written by four catch blocks and read by **zero** components.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The store field | `error` becomes the rich shape (`ExtractionErrorInfo`-compatible) in `taskStore` and `projectStore`, matching what the extraction slice already stores. |
| D2 | The normaliser | `extractErrorInfo` stops being dead code: it becomes the boundary normaliser used by the catch blocks. Its current structural check (`'detail' in err && 'status' in err`) must be reviewed — it is looser than an `instanceof ApiRequestError` test and must not misclassify an arbitrary object that happens to have those keys. |
| D3 | `workspaceStore.error` | **Removed.** Zero readers: keeping a field nothing consumes is the same liability as dead code, and its four catch blocks lose nothing that no consumer was reading. |
| D4 | Consumers | Update the two real readers — `KanbanBoard.tsx:37→:219-229` and `ExportPanel.tsx:19→:159-168` — to pass the structured fields through, deleting the comment that documents the loss. |
| D5 | Tests that must change | `KanbanBoard.test.tsx:118` and `:146` seed `useTaskStore.setState({ error: 'the board is unavailable' })` as a plain string; they must be rewritten against the new shape. They are the first thing that will fail and are the proof the change is observable. |
| D6 | Coverage to add | The two flattening expressions and `ExportPanel`'s error branch (currently untested — `ExportPanel.test.tsx` has one unrelated test) get assertions, since they are the behaviour this feature changes. |

## Non-goals

- No change to `ApiRequestError`'s shape.
- No change to the extraction error path, which already stores the rich shape.
- No new UI for `currentState` / `allowedTransitions`: the data becomes available, surfacing it
  beyond the existing `ErrorDisplay` fields is separate work.

## Tasks

- [ ] Explore the exact reader set of each store's `error` before changing any type.
- [ ] Decide and implement the rich state type shared by `taskStore` and `projectStore`.
- [ ] Route the catch blocks through `extractErrorInfo`; tighten its classification.
- [ ] Remove `workspaceStore.error` and its four writes.
- [ ] Update `KanbanBoard`, `ExportPanel` and their tests.
- [ ] Add the missing coverage (`ExportPanel` error branch, store flattening).
- [ ] Run `pnpm exec tsc --noEmit` and `pnpm vitest run`.
- [ ] Work-unit commit on the feature branch.
- [ ] Independent verification.
- [ ] Fast-forward into `main`, delete the branch, re-gate.

## Evidence

_None yet._
