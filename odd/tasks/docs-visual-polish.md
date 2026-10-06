# ODD Feature: docs-visual-polish

> **Status**: in progress on `feat/docs-visual-polish`, stacked on `feat/semantic-status-tokens` @ `65a9c5d`.
> Nothing is pushed; `main` stays at `7728963`.
> **Created**: 2026-10-06
> **Workflow**: Organic Driven Development (ODD)
> **Source**: points 3, 4 and 5 of `odd/tasks/starlight-docs.md` — the callout hues, the untinted search
> modal, and the dark sidebar's weak separation. The owner chose this line and this one is its payoff:
> `semantic-status-tokens` promoted the families the callouts were missing.

## Problem

Three visual gaps, and one measured fact that reshapes two of them.

| # | Gap | Why it is still open |
| --- | --- | --- |
| 3 | `note`, `tip`, `caution` and `danger` keep Starlight's hues | Registered as *deliberate* because the app "has no OKLCH equivalents beyond `--color-success`". **No longer true**: the previous feature promoted a `warning` family and a `destructive` trio, both now proven in the emitted CSS and the browser. |
| 4 | The search modal is untinted | `--sl-color-backdrop-overlay` was never mapped. |
| 5 | In dark mode the sidebar separates weakly from the body | `--sl-color-bg-sidebar` maps to `--color-surface` (`#0f141d`), while the app's own sidebar uses `--color-sidebar` (`oklch(0.14 0.01 260)`) — lighter, and the app's actual sidebar colour. |

**The measured fact that reshapes the plan.** `frontend/src/content/docs/**` uses **no asides at all** and
no Starlight components either: 18 markdown files of plain prose (`grep` for `:::note|:::tip|:::caution|:::danger`
and for `<Card|<Badge|<Tabs|<Steps|<FileTree` both return nothing). Mapping the four callout colours would
therefore ship a mapping **that no page exercises** — invisible on the site and unverifiable in a browser.
That is why this feature also adds **one real callout** to the quickstart page: it is what makes the
mapping visible, and the fact it carries is one the docs should have been stating anyway.

## What the exploration settled

- **The hue variables are shared.** `--sl-color-{blue,purple,orange,red}` are defined in Starlight's
  `props.css` and consumed by `style/asides.css` **and** by `user-components/Card.astro`,
  `user-components/Badge.astro`, `components/Footer.astro` and `components/ContentNotice.astro`.
  Overriding the hue ramp would reach all of them. **Decision: target the aside classes**
  (`.starlight-aside--note|--tip|--caution|--danger`), which cannot leak into another component.
  The existing `starlight.css` rules are unlayered, so they beat `asides.css` inside
  `@layer starlight.components`.
- **The search modal's surface is already tinted.** `Search.astro` uses `--sl-color-black` for the
  modal background, which `starlight.css` already maps to `--color-surface`. What is untinted is the
  scrim (`--sl-color-backdrop-overlay`, line 230) and the modal shadow (`--sl-shadow-lg`, line 223).
- **Four of the aside's three variables are already the app's shape.** Starlight drives each aside
  with `--sl-color-asides-text-accent` (title and links), `--sl-color-asides-border` (the 4px bar) and
  the background. That is exactly the app's `-text` / `-border` / `-bg` trio.

## Scope

### 1. A guard, written first

`frontend/src/styles/__tests__/starlight-tokens.test.ts`, node environment, parsing both
`starlight.css` and `globals.css` from source:

- **Self-containment.** Every `--color-*` that `starlight.css` references must be declared in
  `starlight.css`. `globals.css` is never loaded on Starlight pages, so a reference to a token this
  file does not declare resolves to nothing — an invisible surface, with no build error and no test
  failure. This is the same silent-failure class the previous feature's guard was built for.
- **Drift.** Every token declared in both files must carry the **same value in the same theme scope**.
  The file's own comment already warned that "a value change in globals.css must be mirrored here by
  hand"; this turns that warning into a failing test. Copying the mirror verbatim — including
  `var(...)` references — is what keeps the comparison a plain string equality.
- **The mappings exist**: the four aside classes styled from `--color-*` and never from
  `--sl-color-{blue,purple,orange,red}`; `--sl-color-backdrop-overlay` declared in both theme scopes;
  `--sl-color-bg-sidebar: var(--color-sidebar)` in both theme blocks.
- **Non-vacuity**, and a triangulated break-and-restore.

### 2. The four callouts, on the app's families

| Aside | Background | 4px bar | Title and links |
| --- | --- | --- | --- |
| `note` | `--color-primary-50` (light) / `--color-primary-950` (dark) | `--color-primary-200` / `--color-primary-900` | `--color-primary-700` / `--color-primary-300` |
| `tip` | `--color-success-bg` | `--color-success-border` | `--color-success-text` |
| `caution` | `--color-warning-bg` | `--color-warning-border` | `--color-warning-text` |
| `danger` | `--color-destructive-bg` | `--color-destructive-border` | `--color-destructive-text` |

Three of the four need **one rule each**: the family trios are theme-flipping tokens, so the same
declaration is correct in both themes. Only `note` needs a dark rule, because the `primary` ramp is
theme-invariant by design.

**Two taste calls, both stated rather than hidden:**

- `note` maps to the brand blue, not to Starlight's blue: the app's informational colour is its
  primary ramp. The ramp's lightest step is L 0.93 where `amber-50` is L 0.987, so the note reads
  **slightly stronger** than its three siblings. Parity would mean adding a ramp step — a one-line
  remedy if the owner wants it.
- The 4px bar takes the app's `-border` token, which is its pale tinted-surface border, not a saturated
  line. That makes the callouts structurally identical to the app's banners and slightly softer than
  Starlight's default bar. Switching the bar to the saturated base token (`--color-warning`, …) is one
  declaration per type.

### 3. The search modal scrim

`--sl-color-backdrop-overlay` → `color-mix(in oklab, var(--color-inverse) 66%, transparent)`, declared in
both theme scopes because Starlight declares it in both and the light scope would otherwise win by
specificity. `--color-inverse` is dark in both themes (`#0f172a` / `#1a1f2e`), which is what a scrim
needs, and `color-mix` is the technique `globals.css` already uses for its shadows.
**`--sl-shadow-lg` is left alone**, and recorded: the app has no elevation token that corresponds to a
modal, and inventing one is a different change.

### 4. The dark sidebar

`--sl-color-bg-sidebar: var(--color-sidebar)` in both theme blocks, plus the mirror. In light this is
unchanged (`var(--color-surface)`); in dark it becomes `oklch(0.14 0.01 260)`, the app's own sidebar
colour, which is what the weak-separation complaint was asking for. The "seven Starlight grays collapsed
onto three" half of point 5 is **not** addressed: it is a broader taste call about the whole gray ramp,
and touching it would make this diff unreadable.

### 5. One real callout, so the mapping is not latent

A `:::caution` on the quickstart page, next to "Configure your LLM", in both locales. The fact it carries
is already true and already documented elsewhere: without a saved provider configuration, extraction is
blocked and the app shows the blocked-extraction banner. Written by the parent, in its own commit, so the
copy is reviewable apart from the CSS.

## Non-goals, and why

| Out of scope | Reason |
| --- | --- |
| The `--sl-color-{blue,purple,orange,red}` ramp | Shared with `Card`, `Badge`, `Footer` and `ContentNotice`. Overriding it would restyle components this feature never looked at. |
| `--sl-shadow-lg` and the rest of Starlight's elevation | No corresponding app token; inventing one is a design change, not an alignment. |
| The whole gray ramp, and light-mode sidebar separation | Broader taste call; light mode is already the surface colour. |
| The `api.astro` page, the Starlight pin, the mono debt | Recorded debt in `odd/tasks/starlight-docs.md`, each with its own decision. |
| Any change under `frontend/src/` outside `styles/` and the two quickstart pages | The docs theme is `customCss`-scoped to Starlight routes; nothing here can reach the app. |

## Tasks

- [x] 1. **The guard** — `d11dc2a`. Written first, run, and observed RED: **7 failed | 6 passed**, with
      the callout, scrim and sidebar assertions failing as expected. **One of my predictions was wrong
      and is recorded below**: I said the self-containment assertion would fail at RED; it passed.
- [x] 2. **Mirror the missing tokens** — `d11dc2a`: 26 mirrors (15 light, 11 dark), copied verbatim.
- [x] 3. **Map the four asides**, per the table — `d11dc2a`.
- [x] 4. **The scrim** and **the sidebar** — `d11dc2a`.
- [x] 5. **The quickstart callout**, both locales, own commit — `d35f194`.
- [ ] 6. **Verify.** The mechanical half is done and measured against the built bytes (below). The
      **visual half is the owner's**: a server is running on `http://127.0.0.1:4322` over
      `.vercel/output/static`, which is how the owner prefers to review.
- [x] 7. **One work-unit commit per task**, nothing pushed.

## Constraints

- **The guard compares source, not rendering.** It is a drift and self-containment check; it does not
  and cannot prove a colour looks right. That is the browser pass's job, and the two are not
  substitutes.
- **`starlight.css` is not loaded by the app.** Everything here is scoped to Starlight routes by
  `customCss`, so the app's rendering cannot change. A guard assertion should say so, not assume it.
- **Copies must be verbatim.** A mirror that "looks the same" but differs by a space or a rounding fails
  the drift guard, and that is the intent: the point is to make hand-mirroring impossible to get wrong
  silently.
- **Neutral Spanish** for the callout copy (ADR-008), same keys and structure on both locales.

## Evidence log

| Task | Commit | What ran, and what it proved |
| --- | --- | --- |
| 1–4 | `d11dc2a` | Guard RED `7 failed | 6 passed` before the file was touched, GREEN `13 passed`. Suite **798/798 in 70 files**, `tsc --noEmit` exit 0, cold build (`rm -rf .astro node_modules/.astro` — **both** caches, see `docs-content-v2`'s correction) exit 0 with 18 HTML files and Pagefind indexing 18. Diff: `starlight.css` `+76/-2`, one file. `git diff HEAD -- src/styles/globals.css` is 0 lines: the app is untouched. Drift assertion proven non-vacuous by mutation (one digit changed in `--color-warning-bg` light → the guard named the file, the token, the theme and both values; restored verbatim). |
| 5 | `d35f194` | The docs content had **no asides at all**, so the callout mapping would have shipped latent. The callout carries a fact the docs owed their readers: without a saved provider configuration, extraction is blocked — the state production and dev are in since the 0028 purge. `docs-content.test.ts` + `neutral-spanish.test.ts`: 31/31. |
| 6 (mechanical) | — | Measured against the **built bytes**, not the source. Both locales' quickstart HTML carry `class="starlight-aside starlight-aside--caution"`, so the markdown really produced an aside. The emitted `index.C19N8tSy.css` — the file the page actually loads — carries our five callout rules, two scrim declarations and two sidebar declarations. **The cascade was measured, not assumed**: ours are `(unlayered)` and Starlight's aside, scrim and sidebar declarations all sit inside `@layer starlight.base` / `starlight.components`, which is what makes ours win even though Starlight's rules are emitted **later** in the file. |

## Findings recorded, not fixed

- The docs content uses no Starlight components at all, so `Card`, `Badge` and `ContentNotice` never
  render on this site today. That is why the surgical choice (aside classes) costs nothing here — and
  why it would matter if the content later adopts cards.
- **A taste call the owner has to make with his eyes**: the `note` callout tints from the brand blue,
  and the `primary` ramp's lightest step is L 0.93 where `amber-50` is L 0.987, so the note reads
  **slightly stronger** than its three siblings. Parity means adding a ramp step. The 4px bar also takes
  the app's pale `-border` token rather than a saturated line, which keeps the callouts structurally
  identical to the app's banners but softer than Starlight's default; switching it to the base accent
  (`--color-warning`, …) is one declaration per type.
- **The guard's non-vacuity floors are calibrated to the finished file** (`SL_DECLS >= 40`,
  `REFERENCED_COLOR_TOKENS >= 20`, `SHARED_TOKENS >= 15`). That makes them "the change landed" checks:
  they fail if the mappings are deleted, and a future refactor that legitimately removes mirrors would
  trip them. Left as is — it errs toward failing loudly.
- **The file's own header comment is now stale by being too weak**: it still says a value change in
  `globals.css` "must be mirrored here by hand". The drift guard enforces it. Rewording the comment was
  outside the delegated edits, so it is recorded rather than done.

### Corrections of record — two method errors of mine, and one wrong prediction

1. **I predicted the wrong RED.** I told the worker that assertions 1, 3 and 4 should fail before the
   change. Assertions 3 and 4 did; **assertion 1 (self-containment) passed**, because the file already
   declared every token it referenced. That axis can only fail on a future regression — which is
   precisely what it is for. The worker reported the contradiction instead of engineering a failure to
   match my brief, which is the behaviour this record exists to reward.
2. **My first pass at the built CSS proved nothing, for the second time in this session.** I grepped
   only the largest emitted stylesheet and found no callout rules, which read exactly like a broken
   build. The rules are in `index.C19N8tSy.css`, the second largest. The lesson is the same one I wrote
   down after the dev-server freshness error: a narrow grep on a build artifact is not evidence of
   absence. Enumerate the artifacts, then conclude.
3. **The check I almost skipped was the one that mattered.** Our callout rules are emitted *before*
   Starlight's, so same-layer CSS order would have handed every callout back to Starlight's hues and
   the guard would still have been green. Only the `@layer` membership settles it, and only the built
   stylesheet can be asked. Measured: ours are unlayered, Starlight's are not.
