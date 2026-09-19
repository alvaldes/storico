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
| D3 | Test shape | **As actually implemented**: two *behaviour* tests — the dialog renders for a story absent from the slice, and with no siblings loaded the dependency select offers no candidate. The original intent was an identity assertion (`select twice, compare with Object.is`); it was dropped while implementing because it pins the mechanism rather than the outcome, and the outcome is the crash. Both shipped tests are proven to fail on the unmodified code. |
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
| Pattern is unique | `git grep -nE "Store\(\(s\) =>.*\?\? \[\]" 6174f5a -- frontend/src` | **1 hit** at the parent commit (`TaskEditor.tsx:49`); **0 hits** on the fixed tree |
| No unstable sibling | sweep of all 42 store-hook call sites in `frontend/src` | no selector returns a newly allocated object/array/`.map`/`.filter` snapshot |

`StoryDetail.tsx:83` also writes `tasks[storyId] ?? []`, but as a plain local after the store was
read, **not** as a selector: it never reaches `getSnapshot`, so it cannot loop. Recorded, not
changed (D4).

## Independent verification

Ran over `6174f5a..fc7b069`, read-only. **All six claims confirmed**: the crash reproduction
(including replaying the shipped tests against the pre-fix bytes → `2 failed | 9 passed`), that
the fix is minimal and correct, that both new tests genuinely fail when the fix is reverted
(also under `--sequence.shuffle` with three seeds), the completeness of the sweep, the three gate
numbers, and no collateral damage (the 9 pre-existing tests are byte-identical).

Three findings, all about this document and none about the code:

| # | Severity | Finding | Disposition |
|---|----------|---------|-------------|
| F1 | LOW | D3 described a snapshot-identity assertion that was never shipped (the tests assert behaviour). | **Fixed** — D3 now records what was implemented and why the identity assertion was dropped. |
| F2 | LOW | The evidence row claimed the uniqueness grep returns "1 hit — the fixed line"; on the fixed tree it returns **0**. The hit exists only at the parent commit. | **Fixed** — the row now names the revision for each count. |
| F3 | INFO | `siblings` infers as plain `Task[]`, not a union with `readonly`: the `readonly` guards the shared constant, not the call site, so a future `siblings.push(...)` would still type-check and only `Object.freeze` would stop it — loudly, not silently. | **Recorded**, no change: no such mutation exists. |

Also verified by the sweep, and worth keeping: no other selector in `frontend/src` returns a
newly allocated object or array, so this was the only unstable snapshot in the tree.

## Tasks — all closed

- [x] Reproduce: confirmed the crash and the warning with the story slice absent.
- [x] Fix with the stable frozen empty-array constant.
- [x] Add the render test plus the no-candidates behaviour test.
- [x] Run `pnpm exec tsc --noEmit` and `pnpm vitest run`.
- [x] Work-unit commit on the feature branch (`6c42998`).
- [x] Independent verification — 6/6 confirmed, F1/F2 fixed in this document, F3 recorded.
- [ ] Fast-forward into `main`, delete the branch, re-gate — **pending**.
