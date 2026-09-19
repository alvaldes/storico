# ODD Feature: taskeditor-sibling-selector

> **Status**: planning — no commit, no evidence yet.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/taskeditor-sibling-selector` (to be created off `main` @ `6174f5a`).
> **Receipt-driven development**: off in this clone.

## Problem

`frontend/src/components/react/TaskEditor.tsx:49`:

```ts
const siblings = useTaskStore((s) => s.tasks[task.storyId] ?? []);
```

The selector returns `s.tasks[task.storyId]` when the story has an entry, but a **fresh
`[]` literal on every call** when it does not. Zustand v5 subscribes through
`useSyncExternalStore`, which compares snapshots with `Object.is`; an unstable snapshot makes
React re-render in a loop and warns *"The result of getSnapshot should be cached to avoid an
infinite loop"*.

The failure is therefore conditional on data, not on the component: it needs the editor to be
mounted for a story whose id is absent from `state.tasks` — exactly what a task opened from a
surface that never populated that story's slice produces. Every other selector in the file
(`:37`) returns a stable reference, which is why this one was easy to miss.

This is the most severe item the independent verifications surfaced, and it was left unbundled
on purpose so it would get its own review.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | The fix | Hoist one module-level frozen empty array and return it from the selector, so the fallback reference is stable for the lifetime of the module. |
| D2 | Alternative rejected | `useShallow` / a `useMemo` wrapper: treats the symptom at each call site and leaves the next selector free to repeat the mistake. |
| D3 | Test shape | Pin the *stability* of the snapshot (select twice, compare identity) **and** pin the observable behaviour that no loop occurs when the slice is missing. A test that only renders the editor would not have caught this. |
| D4 | Scope | This one selector. No sweep of other selectors in this slice; if the sweep finds siblings, record them rather than bundling. |

## Non-goals

- No change to `taskStore`'s shape or to the dependency-selection logic.

## Tasks

- [ ] Reproduce: confirm the warning and the loop with the story slice absent.
- [ ] Fix with the stable empty-array constant.
- [ ] Add the identity-stability test plus the no-loop regression test.
- [ ] Run `pnpm exec tsc --noEmit` and `pnpm vitest run`.
- [ ] Work-unit commit on the feature branch.
- [ ] Independent verification.
- [ ] Fast-forward into `main`, delete the branch, re-gate.

## Evidence

_None yet — this document carries pending statuses only. Evidence rows are written after a
command actually runs._
