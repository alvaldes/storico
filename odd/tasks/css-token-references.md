# ODD Feature: css-token-references

> **Status**: closed, branch `fix/web-css-token-references`, nothing pushed.
> **Created**: 2026-10-06
> **Workflow**: Organic Driven Development (ODD)
> **Source**: the owner reported undeclared CSS variables in the frontend. The report named
> `font-size: var(--sl-text-h4);` as the example; that example turned out to be a false positive, and
> the real broken references were a different, verified set.

## Problem

Six CSS custom-property names are referenced from `frontend/src` and **resolve to nothing**. The
references carry no fallback, so each one is invalid at computed-value time and the property collapses
to `unset` — silently, with no console error and no failing test.

| Token name | References | Files |
| --- | --- | --- |
| `--color-surface-tertiary` | 4 | `src/components/react/StoriesList.tsx:378,415,473`, `src/components/react/KanbanColumn.tsx:24` |
| `--radix-dropdown-menu-trigger-width` | 2 | `src/components/team-switcher.tsx:173`, `src/components/nav-user.tsx:87` |
| `--secondary` | 1 | `src/components/ui/button.tsx:15` |
| `--foreground` | 1 | `src/components/ui/button.tsx:15` |
| `--sidebar-border` | 1 | `src/components/ui/sidebar.tsx:464` |
| `--sidebar-accent` | 1 | `src/components/ui/sidebar.tsx:464` |

What each one does today, measured against the emitted CSS (`frontend/dist/client/_astro/*.css`), not
inferred:

1. **`--color-surface-tertiary` never existed.** `git log -S "--color-surface-tertiary:"` over the
   whole repository returns nothing: no commit ever declared it. It was written in `08e68e9` and
   `79d63ea` as if it were a sibling of `--color-text-tertiary`. Being a Tailwind v4 arbitrary value
   (`bg-(--color-surface-tertiary)` → `background-color: var(--color-surface-tertiary)`), it compiles
   verbatim and dies at runtime. `KanbanColumn`'s count badge renders as muted text with no chip, and
   the three help icons in `StoriesList` have no hover background.
2. **`--radix-dropdown-menu-trigger-width` is a stale Radix name.** `src/components/ui/dropdown-menu.tsx`
   imports `Menu` from **`@base-ui/react/menu`**, and Base UI's positioning primitive publishes
   `--anchor-width` (that is the name `dropdown-menu.tsx:42` uses in its own class list). The Radix
   name survived the layout refactor `a73578b`. With `width: var(…)` invalid, `unset` means `auto`, so
   both workspace/user menus fall back to `min-w-56` instead of matching their trigger's width.
3. **`--secondary` and `--foreground` are Tailwind-v3-era bare names.** `globals.css` declares them as
   `--color-secondary` and `--color-foreground` inside `@theme inline`. The `background-color:
   color-mix(in oklch, var(--secondary), var(--foreground) 5%)` in `button.tsx` is therefore invalid
   and the `secondary` button's fill **disappears** on hover instead of gaining a 5% tint.
4. **`--sidebar-border` and `--sidebar-accent` are the same mistake on the sidebar rail.** The declared
   names are `--color-sidebar-border` / `--color-sidebar-accent`. Both `box-shadow` declarations become
   `none`, so the rail button's ring never appears, neither at rest nor on hover.

### Why `--sl-text-h4` is *not* one of them

The reported example resolves correctly. Starlight declares it in its own shipped stylesheet — not in
this repository:

- `node_modules/@astrojs/starlight/style/props.css:81` → `--sl-text-h4: var(--sl-text-xl);`
- `node_modules/@astrojs/starlight/style/props.css:178` (inside `@media (min-width: 50em)`) →
  `--sl-text-h4: var(--sl-text-2xl);`

Those live in `@layer starlight.base` on `:root`. CSS layers do not affect custom-property resolution
— they only arbitrate *conflicting declarations* — so the value inherits into `SiteTitle.astro`, a
Starlight component that renders inside Starlight's own layout, with Starlight's stylesheet loaded.
Confirmed in the emitted output: `frontend/dist/client/_astro/index.DLh9Tnd8.css` both declares
`--sl-text-h4` and uses it, in the same chunk. An editor that flags it is not indexing `node_modules`.

Every other `--sl-*` reference in the tree is either declared by that same shipped stylesheet
(`--sl-nav-gap`, `--sl-nav-height`, `--sl-nav-pad-x`, `--sl-nav-pad-y`, `--sl-sidebar-width`,
`--sl-content-width`, `--sl-text-sm`, `--sl-color-*`) or carries a fallback
(`var(--sl-content-inline-start, 0rem)`).

## The owner's decisions

- **Scope: fix all six names and add the guard.** Working code with a red suite is not an option, and
  fixing without a guard leaves the door open for a seventh.
- **`--color-surface-tertiary` maps onto `--color-surface-secondary`.** No new token. The naming is
  already consistent: `--color-surface-secondary` is the support surface in this design system — it is
  also what `--color-muted`, `--color-accent` and `--color-sidebar-accent` resolve to.

## The `@theme inline` trap (measured)

The obvious fix — rename `--secondary` to `--color-secondary` — would have produced a **second**
silent failure, and this is the reason the substitutions below target the plain tokens instead.

`--color-secondary`, `--color-foreground` and `--color-sidebar-border` are declared inside
`@theme inline`. Tailwind does **not** emit an `inline` theme variable into `:root` unless the name is
referenced somewhere in the scanned source. Verified on the emitted CSS:

```
declared in @theme inline, NOT referenced  → NOT emitted
  --color-secondary            emitted=false
  --color-foreground           emitted=false
declared in @theme inline, referenced      → emitted
  --color-popover              emitted=true   (var(--color-popover) in src/components/ui/sonner.tsx:73)
  --color-destructive          emitted=true   (var(--color-destructive) in ui/sonner.tsx:78)
  --radius                     emitted=true   (var(--radius) in ui/input-group.tsx:24, ui/sonner.tsx:76)
```

`--color-sidebar-border` is worse than absent: the dark block declares it as a literal, so
`var(--color-sidebar-border)` would resolve in dark theme and fail in light — a bug that only shows up
in one theme.

So the substitutions target the app's plain `@theme` tokens, which the app's own utilities already
reference by name and which are therefore emitted unconditionally, in both scopes. Every replacement is
**value-identical in light and dark**, checked declaration by declaration:

| Reference today | Replacement | Why it is the same value |
| --- | --- | --- |
| `--secondary` | `--color-surface-secondary` | `--color-secondary: var(--color-surface-secondary)` (globals.css) |
| `--foreground` | `--color-text` | `--color-foreground: var(--color-text)` (globals.css) |
| `--sidebar-border` | `--color-border` | light: `--color-sidebar-border: var(--color-border)`; dark: both literals are `oklch(0.25 0.01 260)` |
| `--sidebar-accent` | `--color-surface-secondary` | light: `--color-sidebar-accent: var(--color-surface-secondary)`; dark: both are `oklch(0.18 0.01 260)` |
| `--color-surface-tertiary` | `--color-surface-secondary` | the token never existed; this is the support surface (owner's decision) |
| `--radix-dropdown-menu-trigger-width` | `--anchor-width` | the name Base UI actually injects for a positioned popup |

## Scope

1. **The guard test** — `frontend/src/styles/__tests__/css-vars.test.ts`. Walks `frontend/src`, extracts
   every custom-property *reference* and every custom-property *declaration*, and fails on a reference
   that resolves to nothing. Test-first: written first, RED observed on exactly the six names above,
   GREEN after the substitutions.
2. **The substitutions** — the ten references across six files, per the table above.
3. **Verify** — the emit, the focused test, the full suite, `tsc`, and a browser check of the four
   visible symptoms in both themes.

## Non-goals

| Out of scope | Reason |
| --- | --- |
| `--sl-text-h6` | Starlight's own stylesheet uses it (`style/markdown.css:97`, `style/anchor-links.css:72`) and Starlight never declares it. Upstream bug, not ours; recorded here so the next person recognises it. |
| Replacing `sonner.tsx`'s `@theme inline` references | They resolve today (measured above). Turning that into a rule would add an allowlist for working code. Documented in the guard's header instead of enforced. |
| Declaring a real `--color-surface-tertiary` ramp step | The owner chose the existing token. A third surface step would need a value, a dark override and a `design-tokens.test.ts` entry for no visible gain. |
| Any other CSS debt | Only what the guard reports after the fix is closed here. |

## Tasks

- [x] 1. **Guard test + the six substitutions**, one work unit. RED observed on the six names before any
      source edit, GREEN after — `0b8306b`.
- [x] 2. **Exclude tests from Tailwind's content scan.** Not in the original scope: verifying task 1
      found that the guard test's own text is scanned as content and compiled into dead rules. One
      line in `globals.css`, measured — `d622970`.
- [x] 3. **Verify and close** — this commit.

## The guard test leaked nine dead rules into the bundle (found by verification)

The first verification pass was asked to diff the set of emitted custom-property declarations before
and after the change. It returned three new names nothing in the change declares: `--c`, `--name`,
`--x`.

The cause is that Tailwind v4's automatic content detection scans `src/**` — **comments included** —
and the guard test lives in `src/styles/__tests__/`. Its illustrative examples of Tailwind syntax are
indistinguishable from real class names to a scanner, so they compiled into rules no markup can match.
The declaration diff understated it: a `bg-(--probe)` example declares no new custom property, so only
the bracketed declarations showed up.

Measured by diffing the raw emitted CSS of two clean builds (250,128 vs 249,785 bytes), the exclusion
removes **exactly nine dead rules, 343 bytes, and nothing else**:

| Dead rule | Origin |
| --- | --- |
| `.\[--c\:--spacing\(4\)\]{--c:calc(var(--spacing) * 4)}` | a synthetic fixture in the test |
| `.\[--name\:…\]{--name:…}`, `.\[--x\:…\]{--x:…}` | the test's own header and JSDoc |
| `.bg-\(--color-x\)`, `.bg-\(--name\)`, `.w-\(--name\)` | the test's prose examples |
| `.bg-\(--first-probe\)` | a synthetic fixture in the test |
| `.contents`, `.lowercase` | ordinary words in test prose, zero uses in app source |

Nothing else left the bundle — every remaining difference between the two builds was an Astro scoped-style
hash on `.brand-link`, identical in both once compared by selector — and nothing was added.

First measurement was wrong, and the way it was wrong is worth keeping. It read 358 bytes because it
concatenated `dist/client/_astro/*.css` without clearing `dist` first: Astro leaves a stale chunk behind
when a hash changes, and a naive glob picks it up. The tell was a rule that appeared to vanish,
`.h-0\.5` — exactly 41 bytes — which no source file in the frontend mentions and which no dynamic class
construction produces. Both numbers were re-measured from `rm -rf dist .astro` before each build, and
the committed state's build is now confirmed byte-identical from clean and incremental runs.

The fix is a build-level exclusion rather than sanitised fixtures: **every** fixture written to exercise
a Tailwind-shaped pattern is a candidate for the scanner, so chasing them one by one is a losing game —
and this file's own prose illustrates the syntax it is about. `@source not` with a quoted path is
supported by the installed Tailwind 4.3.3, confirmed in its directive parser
(`E.startsWith("not ")` followed by a mandatory quoted path).

## Constraints

- **The guard must not be vacuous.** The existing guards in this repository assert their own
  non-vacuousness (`design-tokens.test.ts` → "the token parse is not vacuous";
  `starlight-tokens.test.ts` → "walks a substantial part of the source tree"). This one asserts a
  minimum source-file count, a non-empty reference parse, non-empty derivations for both external
  sources, and unit-tests the detector against a synthetic undeclared name that the real tree does not
  contain.
- **Both reference syntaxes count.** Tailwind v4's `bg-(--x)` / `w-(--x)` shorthand is a raw reference
  just like `var(--x)`, and it is the syntax four of the six names use. A guard that only greps
  `var(` would have missed `--color-surface-tertiary` and `--radix-dropdown-menu-trigger-width`
  entirely.
- **Declarations come from CSS positions only** — `.css` files, `<style>` blocks in `.astro`, quoted
  inline-style keys (`'--x':`) and arbitrary-property brackets (`[--x:…]`). Scanning `.tsx` prose for
  `--x:` would let a comment declare a token and silently mask a broken reference.
- **A fallback is an exemption, not a failure.** `var(--x, 0rem)` is the explicit statement that the
  token is optional; `--public-nav-h` and `--sl-content-inline-start` rely on that and are correct.
- **pnpm symlinks.** `node_modules/@base-ui/react` and `node_modules/@astrojs/starlight` are symlinks
  into `.pnpm`. A recursive walk must resolve them (`fs.realpathSync`) or follow directory symlinks;
  `readdirSync(dir, { recursive: true })` does **not** follow symlinked directories and would derive an
  empty external set, quietly turning every reference into a failure.

## Evidence log

### Reconnaissance

- Source-wide scan of `frontend/src` (`.css`, `.astro`, `.tsx`, `.ts`) against declarations in the same
  tree: 123 declared names, 6 unresolved with no fallback.
- Cross-checked against the emitted CSS (`frontend/dist/client/_astro/globals.CSl4RjTF.css`,
  `index.DLh9Tnd8.css`, `styles.D2xgHy33.css`): all six are emitted verbatim as
  `var(--name)` / `width:var(--name)` / `background-color:var(--name)` with no declaration anywhere in
  any chunk.
- External derivation sources, both non-empty and both symlinked: Starlight's shipped stylesheet
  (`style/*.css`, 97 `--sl-*` declarations) and Base UI's runtime variable modules
  (`**/*CssVars*`, 43 names including `--anchor-width`, `--available-height`, `--transform-origin`,
  `--accordion-panel-height`).

### The worker's first guard was accepted only after four corrections

The drafted guard's own comments described behaviour the code did not have. Each was confirmed with a
probe before being touched:

1. Its declaration-boundary comment claimed the character class included `[`; it did not — `[--d:1px]`
   produced no match on that path and only matched through a second pattern.
2. A declaration at the first character of a file, or opening straight onto a `<style>` span, was
   dropped.
3. It advertised references "in source order" while returning every `var()` before every shorthand.
4. **A real false negative:** `var(--outer, var(--inner))` reported only `--outer`. A `var()` nested as
   another's fallback — with no fallback of its own — was invisible, which is precisely the silent hole
   this guard exists to close.

The fix replaced the nesting regex with a balanced-parenthesis walk that recurses into the fallback
position, corrected the offset arithmetic (`[...source]` splits by code point while a regex `index`
counts UTF-16 code units — the two disagree after the first emoji), and replaced the boundary class with
CSS-comment stripping, so no character has to be guessed and a commented-out declaration can never
declare a token. Eight tests were added that exercise the declaration scanner and the resolution rule on
synthetic input.

### Test-first evidence

- **RED**, observed by checking out the six component files and running the final guard: exactly 6 names
  / 10 references, with the exact `file:line` list and no `--card-spacing` false positive —
  `1 failed | 16 passed`.
- **GREEN** after restoring: `17 passed (17)`.
- Full suite **72 files / 818 tests**, `tsc --noEmit` exit 0.

Baseline correction worth recording: an earlier brief claimed "72 files / 810 tests before the guard".
That was wrong. The suite was **71 files / 801 tests** before the guard existed and is 72 / 818 now
(801 + the guard's 17).

### Independent verification

- Pre-change snapshot: **511 declared custom-property names**, with all six broken forms present in the
  emitted CSS. After the change: **none of the six remains** (checked for prefix collisions, not just
  exact strings), and **no declared name disappeared**.
- **The claim the substitution rests on — PASSED.** `--color-surface-secondary`, `--color-text` and
  `--color-border` are each declared in the light block (`:root,:host`) *and* in
  (`:root[data-theme=dark],[data-theme=dark],[data-theme=dark] *`), read out of the fresh chunk.
- `--anchor-width` is not ours to declare: `@base-ui/react@1.8.0`
  `utils/CommonPositionerCssVars.mjs:15` declares `anchorWidth = '--anchor-width'`, and
  `internals/useAnchorPositioning.mjs:234` publishes it to the element's style. The fresh CSS compiles
  `w-(--anchor-width)` into `width:var(--anchor-width)`.
- Guard integrity: breaking one reference to `--color-surface-deliberately-broken` makes the guard fail
  naming that token and `KanbanColumn.tsx:24`; the file was then restored byte-identically (md5 compared).

### Functional check in a real browser

The four symptoms live in components that need a session, a workspace and data, and this environment has
none of that (`docs/deployment.md`, `odd/tasks/dev-reset-0028.md`). So the check targeted the question
that is actually at stake — does the property still collapse to `unset`? — with a scratch page loading
the freshly built chunk and reading `getComputedStyle`:

| Probe | Light | Dark |
| --- | --- | --- |
| `bg-(--color-surface-secondary)` | `oklch(0.96 0.01 260)` | `oklch(0.18 0.01 260)` |
| `hover:bg-[color-mix(in oklch, var(--color-surface-secondary), var(--color-text) 5%)]` | `oklch(0.9195 0.01 260)` on hover | `oklch(0.2175 0.01 260)` |
| `shadow-[0_0_0_1px_var(--color-border)]` | `oklch(0.88 0.01 260) 0 0 0 1px` | `oklch(0.25 0.01 260) 0 0 0 1px` |
| `hover:shadow-[0_0_0_1px_var(--color-surface-secondary)]` | derived, see below | `oklch(0.18 0.01 260) 0 0 0 1px` |
| `w-(--anchor-width)` with `--anchor-width:275px` | `275px` | `275px` |
| **negative control**: `background-color: var(--undeclared)` + `box-shadow: 0 0 0 1px var(--undeclared)` | `rgba(0, 0, 0, 0)` and `box-shadow: none` | same |

The negative control is what makes the table mean something: it reproduces the pre-fix failure mode in
the same page, so the instrument is proven to detect it rather than merely never complaining. No probe
collapsed.

Stated as a derivative rather than an observation: the light-theme hover of the rail ring was not
captured directly, because the pointer was on another element when the theme was read. It follows from
two things observed in that same page — the rule is
`box-shadow: 0 0 0 1px var(--color-surface-secondary)`, and light `--color-surface-secondary` computed as
`oklch(0.96 0.01 260)` on the element beside it.

Still not runnable here, and not claimed: a browser pass over the real Kanban board, story list, workspace
switcher and sidebar, with a session and data. That is what would confirm the four symptoms are gone *in
place*, as opposed to confirming that the properties resolve.

## Limitations carried forward

- **References to `@theme inline` names are fragile, and the guard does not forbid them.** Tailwind emits
  an `inline` theme variable only when its scanner sees a reference to that name, so such a reference
  resolves by side effect. `ui/sonner.tsx` relies on this today (`var(--color-popover)`,
  `var(--color-destructive)`, `var(--radius)`) and it works; making it a rule would need an allowlist for
  working code. Documented in the guard's header instead of enforced.
- **A Tailwind-shaped string anywhere in `src/**` is a content candidate.** The `@source not` line handles
  `__tests__`; the same trap applies to a future fixture, doc comment or prose file that lives in a
  scanned path.
- **`--sl-text-h6`** is used by Starlight's own CSS (`style/markdown.css:97`,
  `style/anchor-links.css:72`) and declared by no one. Upstream, not ours.
