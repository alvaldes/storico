# ODD Feature: app-debt-closure

> **Status**: in progress, same stack, nothing pushed.
> **Created**: 2026-10-06
> **Workflow**: Organic Driven Development (ODD)
> **Source**: the two app-side debts that surfaced while working on the docs, both with the owner's
> decision already taken.

## Problem

Two defects in the app, found by looking rather than by testing.

1. **The mono font is declared but never loaded.** `frontend/src/styles/globals.css:141` says
   `--font-mono: 'JetBrains Mono', 'SF Mono', ui-monospace, monospace`, and JetBrains Mono appears
   nowhere in the font link. What the app **does** download on every page is **Geist Mono**
   (`frontend/src/lib/fonts.ts:27`, `family=Geist+Mono:wght@400;500;600;700`, and `FONT_FAMILIES`
   lists it). So every code block, identifier and API snippet renders in the system mono while a font
   paid for on every page is thrown away. On top of that, `@fontsource-variable/geist ^5.2.9` sits in
   `dependencies` and in `node_modules`, and nothing imports it.
2. **`StatusPanel` renders lists without keys.** `frontend/src/components/react/StatusPanel.tsx:324` and
   `:332` do `{coreRows.map(renderRow)}` and `{optionalRows.map(renderRow)}`, and `renderRow` (`:266`)
   returns a `<div>` with no `key`. React logs `Each child in a list should have a unique "key" prop`
   on every status page load. Confirmed in a real browser console during the previous feature's
   verification, on both themes.

## The owner's decisions

- **Mono: declare Geist Mono.** The font already travels on every page, so this adds no download and
  makes the declaration true. It changes how code looks across the product, which is the point.
- The `@fontsource-variable/geist` dependency goes with it: it is unused and, once the token names
  Geist Mono, the Google Fonts link is the single source of the face.

## Scope

1. **`--font-mono` → `'Geist Mono'`** in `globals.css`, and the mirror in `starlight.css` in the same
   change. The drift guard added in `docs-visual-polish` compares every token declared in both files,
   **including `--font-mono`**, so the change has an order that proves the guard works: edit
   `globals.css`, see the guard fail on the drifted mirror, then fix the mirror.
2. **Drop `@fontsource-variable/geist`** from `dependencies`.
3. **Key the `StatusPanel` rows** — one line, `key={row.title}`, since the rows carry unique titles.
   Test-first: a test that renders the panel and fails if React logs a key warning.
4. **Verify**: focused tests, the full suite, `tsc`, build, and a browser check that a code block now
   renders in Geist Mono in both themes.

## Non-goals

| Out of scope | Reason |
| --- | --- |
| The `Inter` / `Space Grotesk` halves of the font link | They are loaded and used. Only the mono was lying. |
| Changing the docs theme | The mirror is a copy of the token; the docs follow it and the drift guard enforces that. |
| Any other debt in the repository | Recorded elsewhere; this feature closes exactly the two the docs work surfaced. |

## Tasks

- [x] 1. **The mono token**, mirror included — `84ab88e`. The guard's RED was observed **before** the
      mirror moved, which is the first real drift it has caught.
- [x] 2. **Drop the unused font package** — `84ab88e`: `@fontsource-variable/geist` is out of
      `dependencies`, out of `pnpm-lock.yaml` and out of `node_modules`.
- [x] 3. **Key the `StatusPanel` rows**, test-first — `e37d66d`. RED with React's exact message,
      GREEN after one line.
- [x] 4. **Verify** and one work unit per task. Suite **799/799 in 71 files**, `tsc --noEmit` exit 0.

## Constraints

- **Behaviour-first, not appearance-first.** The font change is appearance; its testable part is that
  the declaration matches what is loaded, which the drift and mirror guards already cover.
- **The key fix must be proven by its warning.** A test that spies on `console.error` and asserts the
  absence of the React key message is the RED; without it the fix would be faith.

## Evidence log

| Task | Commit | What ran, and what it proved |
| --- | --- | --- |
| 1–2 | `84ab88e` | `--font-mono` moved to `'Geist Mono'` in `globals.css`, the mirror moved with it, and the package is gone. The order was deliberate: `globals.css` first, guard run, and it failed with `--font-mono (light) drifted from globals.css: starlight.css says "'JetBrains Mono', …", globals.css says "'Geist Mono', …"` — token, theme and both values, before the docs could render a font the app had stopped declaring. Fixing the mirror gave 13/13 again. |
| 3 | `e37d66d` | One line: `key={row.title}` on the element `renderRow` returns. **The test-first attempt failed in an instructive way**: the assertion added to `StatusPanel.test.tsx` **passed against the unfixed component**, because React logs a list-key warning once per message per module instance and an earlier render in that file had already emitted it — a passing test that proves nothing. Moved into its own file, where the render is the first anywhere, the spy is a real witness: RED with `Each child in a list should have a unique "key" prop.%s%s See https://react.dev/link/warning-keys`, GREEN after the fix. The file documents why it must stay alone. |
| 4 | — | `pnpm test` **799/799 in 71 files** (the new file is the +1), `tsc --noEmit` exit 0, `pnpm exec vitest run` on the drift guard 13/13. |

### Not verified

| Item | Why |
| --- | --- |
| That a code block now **renders** in Geist Mono in a browser | The token and the font link agree, and the guard enforces the mirror; but no browser measured the computed `font-family` of a code block. The owner's review of the running app covers it, or a follow-up browser pass does. |
