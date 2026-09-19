# ODD Feature: taskeditor-sibling-selector

> **Status**: done — commits `e460b8f` (the plan of record) and `6c42998` (the fix) on
> `fix/taskeditor-sibling-selector`, not pushed. Receipt-driven development is **off** in this
> clone, so no native review ran; independent verification is recorded below.
> **Created**: 2026-09-19
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `fix/taskeditor-sibling-selector`, off `main` @ `6174f5a`.

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

## Reproduced, and it was worse than a warning

Measured before any change, with the story slice absent (`state.tasks = {}`), React DOM 19.3.0:

```text
THREW: Error: Maximum update depth exceeded. This can happen when a component repeatedly
       calls setState inside componentWillUpdate or componentDidUpdate. React limits the
       number of nested updates to prevent infinite loops.
WARNING_COUNT: 1
FIRST_WARNING: The result of getSnapshot should be cached to avoid an infinite loop
RENDERED_TITLE: no
```

The stack proves the path is `useSyncExternalStore`, not a local state loop:
`forceStoreRerender` → `updateStoreInstance` → `commitHookEffectListMount`.

So the dialog **throws and renders nothing**. The problem statement above said "re-renders in a
loop" and warned about the console; the honest severity is a hard crash of the editor.

The two permanent tests were written first and failed on the unmodified code with the same
`Error: Maximum update depth exceeded`, then passed after the fix.

## Evidence

| Check | Command | Result |
|-------|---------|--------|
| Repro (before) | `pnpm vitest run …/TaskEditor.test.tsx` | **2 failed**, 9 passed — `Error: Maximum update depth exceeded` |
| Fixed file | `pnpm vitest run …/TaskEditor.test.tsx` | **11 passed** |
| Full frontend suite | `pnpm vitest run` | **33 files, 384 passed** (baseline 382, +2 new) |
| Types | `pnpm exec tsc --noEmit` | exit 0 |
| Pattern is unique | `grep -rn "use*Store((s) =>… ?? []" frontend/src` | 1 hit — the fixed line |

`StoryDetail.tsx:83` also writes `tasks[storyId] ?? []`, but as a plain local after the store was
read, **not** as a selector: it never reaches `getSnapshot`, so it cannot loop. Recorded, not
changed (D4).

## Tasks — all closed

- [x] Reproduce: confirmed the crash and the warning with the story slice absent.
- [x] Fix with the stable frozen empty-array constant.
- [x] Add the render test plus the no-candidates behaviour test.
- [x] Run `pnpm exec tsc --noEmit` and `pnpm vitest run`.
- [x] Work-unit commit on the feature branch (`6c42998`).
- [ ] Independent verification — **pending**.
- [ ] Fast-forward into `main`, delete the branch, re-gate — **pending**.
