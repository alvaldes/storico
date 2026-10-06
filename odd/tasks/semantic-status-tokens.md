# ODD Feature: semantic-status-tokens

> **Status**: in progress on `feat/semantic-status-tokens`, stacked on `feat/docs-content-v2` @ `8a73d6a`.
> Nothing is pushed; `main` stays at `7728963`.
> **Created**: 2026-10-06
> **Workflow**: Organic Driven Development (ODD)
> **Source**: point 3 of `odd/tasks/starlight-docs.md` (the callout hues). The owner was offered three
> scopes and chose the widest: promote the missing semantic families **and** migrate the components
> that hardcode them. The docs polish that will consume this is a separate stacked feature
> (`docs-visual-polish`), started after this one closes.

## Problem

The app has three semantic status families and tokenized exactly one of them.

| Family | Tokens | Ad-hoc Tailwind literals |
| --- | :---: | --- |
| `success` (emerald) | full trio, light + dark | **0** (3 usages, all tokenized) |
| `warning` (amber) | **none** | **38** occurrences, 5 components |
| `danger` (red) | `--color-destructive` only — one colour, no trio, no dark variant | **~119** occurrences, 7 components |
| `info` (blue) | `primary-*` ramp | 1 |

Consequences visible in the code, none of them a design decision:

- the same banner recipe is spelled `dark:bg-amber-950/30` in `TaskEditor.tsx:513` and
  `dark:bg-amber-950/40` in `StatusPanel.tsx:43`;
- the same title is `dark:text-amber-200` in `MemberManagement.tsx:558` and `dark:text-amber-300` in
  `StatusPanel.tsx:57`;
- the same danger body is `text-red-700` in five files and `text-red-600` in `AccountPage.tsx:324`;
- `AccountPage.tsx:315` declares a red heading **with no dark counterpart at all**.

And the red is already in the token system by the back door: `--color-destructive` is
`oklch(0.577 0.245 27.325)`, which is **exactly Tailwind's `red-600`** (`node_modules/tailwindcss/theme.css:16`).

## The rule that governs the token values

**No literal is invented.** Every value is copied from the palette the app already renders —
`node_modules/tailwindcss/theme.css` — and each token records in a comment which ramp step it mirrors.
Each trio copies the shape of `--color-success`, the one family the app already got right.

The accent slot keeps **today's exact rendering**: `--color-warning` is amber-500, which is what every
bare `text-amber-500` / `bg-amber-500` site renders right now. Only the *text* roles collapse, because
they are the ones that disagree with each other.

## Scope

**1. Promote the families** into `frontend/src/styles/globals.css`:

| Token | Light | Dark | Mirrors today's |
| --- | --- | --- | --- |
| `--color-warning` | `oklch(0.769 0.188 70.08)` | *(none — theme-invariant, like `--color-success`)* | `text/bg-amber-500` |
| `--color-warning-bg` | `oklch(0.987 0.022 95.277)` | `oklch(0.279 0.077 45.635 / 0.3)` | `bg-amber-50`, `dark:bg-amber-950/30` |
| `--color-warning-border` | `oklch(0.924 0.12 95.746)` | `oklch(0.414 0.112 45.904)` | `border-amber-200`, `dark:border-amber-900` |
| `--color-warning-text` | `oklch(0.473 0.137 46.201)` | `oklch(0.879 0.169 91.605)` | `text-amber-800`, `dark:text-amber-300` |
| `--color-destructive-bg` | `oklch(0.971 0.013 17.38)` | `oklch(0.258 0.092 26.042 / 0.3)` | `bg-red-50`, `dark:bg-red-950/30` |
| `--color-destructive-border` | `oklch(0.885 0.062 18.334)` | `oklch(0.396 0.141 25.723)` | `border-red-200`, `dark:border-red-900` |
| `--color-destructive-text` | `oklch(0.444 0.177 26.899)` | `oklch(0.808 0.114 19.571)` | `text-red-800`, `dark:text-red-300` |

`--color-destructive` itself is **not touched** and gets no dark override: it stays red-600 in both
themes, as it is today for the `button`/`badge` variants. On the dark body that is a 5.6:1 contrast
ratio, which passes AA.

**2. Migrate every ad-hoc occurrence** in `frontend/src` onto these tokens (11 files), by role:

| Role | Slot |
| --- | --- |
| tinted surface background | `-bg` |
| tinted surface border | `-border` |
| text inside a tinted surface (title, body) | `-text` |
| solid accent — icon, status dot, card heading, retry/inline link, and hover states | the base token (`--color-destructive`, `--color-warning`) |
| `emerald-*` | the existing `success` family |
| the one `blue-500` | `text-primary` |

**3. Guard it**: a test that (a) asserts every new token exists *with its value* in the right scope,
and (b) forbids the ramp literals outright, so the debt cannot grow back.

### Deliberate visual deltas

Consolidation means the minority spellings converge on the majority. Every site that moves is listed
here; anything else that changes appearance is a bug in the migration, not a delta.

| Delta | Sites | Why |
| --- | --- | --- |
| dark banner bg `/40` → `/30` | `StatusPanel.tsx:43,45,310` | `/30` is the danger majority (8 sites) and the warning half; choosing one shared value keeps the two sibling families coherent. |
| dark warning title `amber-200` → `amber-300` | `MemberManagement.tsx:558`, `TaskEditor.tsx:515` | `amber-300` is the warning majority (3 sites). Title/body hierarchy survives on `font-medium`, which those titles already carry. |
| warning hint `amber-600`/`amber-400` → `-text` (`amber-800`/`amber-300`) | `LLMConfigEditor.tsx:873,878,891,902,908` | Collapsed into the single readable warning tone. Darker in light, and still light in dark: contrast improves in both. |
| danger body `text-red-700` → `-text` (`red-800` light) | 5 sites | One ramp step; removes the `AccountPage.tsx:324` outlier instead of blessing it. |
| danger `text-red-500` → `text-destructive` (red-600) | 8 icon sites, plus `WorkspaceSettings.tsx:408` where the same literal is inline error **text**, not an icon (my first census said 6; the scout's inventory was right) | One ramp step. The accent is theme-invariant by design, so these sites stay red-600 in both themes and have no dark value to lose. |
| danger border `border-red-300` / `dark:border-red-700` → `-border` (red-200 / red-900) | `WorkspaceSettings.tsx:322`, and the two danger outline buttons | One step lighter in light; in dark, red-700 → red-900 consolidates the danger-zone Card onto the value the banners already used. |
| warning ring `ring-amber-300` → `-border` (amber-200 / amber-900) | `MemberManagement.tsx:496` | The ring carried **no** dark counterpart at all — the light value was showing in both themes. It gains one. |
| `bg-red-50/80 dark:bg-red-950/20` → `-bg` solid wash | `WorkspaceSettings.tsx:335` (CardFooter) | The footer's deliberate translucency is dropped for the shared wash; the `border-t-` direction is kept. |
| `dark:text-red-400` on links/headings → `text-destructive` | `LLMConfigEditor.tsx:521`, `MemberManagement.tsx:251`, `WorkspaceSettings.tsx:292,326`, `AccountPage.tsx:315` | Keeps the light value exact (red-600) and makes dark red-600 instead of red-400: still 5.6:1, AA. Avoids inventing a dark override for a token that has none. |
| `emerald-*` → `success` | `ErrorDisplay.tsx:101`, `StoryForm.tsx:491,558`, `sonner.tsx:63` | Hue shifts from emerald (163) to the app's green (145) — which is the point: one green, not two. |
| `blue-500` → `primary` | `sonner.tsx:64` | One brand blue. |

## Non-goals, and why

| Out of scope | Reason |
| --- | --- |
| The docs (`starlight.css`, callouts, search modal, sidebar contrast) | Separate stacked feature `docs-visual-polish`, which consumes what this promotes. |
| A reusable `Alert` / `Banner` component | The inventory confirms none exists. Introducing one on top of a colour migration doubles the review surface; migration is literal → token, nothing else moves. |
| Touching `--color-success`, `--color-destructive`, `--color-method-*` values | They are the migration's targets. A value change here would be a redesign wearing a refactor's clothes. |
| Unifying the two token-consumption conventions (`text-success-text` vs `text-(--color-success-text)`) | The migration uses **one** convention for what it touches — the arbitrary-value form of `StatusPanel.tsx:35` — and leaves pre-existing usages alone. Unifying them is its own change. |
| Any backend change | This is CSS tokens and className strings. |

## Tasks

- [x] 1. **Promote the trios** into `globals.css` + the token-existence guard — `4ece390`. Additive:
      nothing consumes them yet, so the app's rendering is unchanged by construction. The guard was
      written first and observed failing before the tokens existed (3 failed | 3 passed on the new
      file), so this task is test-first — **a correction of my own earlier claim** that adding unused
      variables leaves no meaningful RED. It does: the guard's assertions are the RED.
- [x] 2. **Migrate the 11 files** onto the tokens, in the same commit as the guard's second half (the
      literal ban) — `eb8177c`. That half had a real RED: the ban failed with all **73** offenders
      printed as `path:line`, and passes now that the literals are gone.
- [ ] 3. **Verify.** The mechanical half is done and passed — see the log below. The **visual half is
      the owner's**: the owner took over the browser space mid-run and chose to review the surfaces
      himself, so the agent's browser evidence covers `/en/status` in both themes and nothing behind
      the login.
- [ ] 4. **Evidence log** with the deltas as they actually landed, plus the owner's verdict on the
      visual pass.

### Commit plan, and why it is not one commit per family

The owner asked for the widest scope, so the review surface is the thing to protect. But splitting the
migration per family would not work: `StatusPanel`, `MemberManagement`, `LLMConfigEditor` and `sonner`
carry **both** families on adjacent or identical lines, so the hunk boundaries do not follow the family
boundary and the resulting commits would not stand alone.

| Commit | Contents |
| --- | --- |
| `feat(web)` | the seven tokens + the token-existence guard |
| `refactor(web)` | the 11-file migration + the literal ban, with the observed RED in the message body |
| `docs(odd)` | this document's evidence log |

### Hover states are not the accent

Where hover modulates a colour that is already destructive (the retry links, the two danger outline buttons), the hover lands on `-text`/`-bg` rather than on the accent: accent-on-accent erases the hover feedback entirely. Where hover *introduces* the destructive colour from a neutral
(`MemberManagement.tsx:426`), it lands on the accent. That distinction is the migration's only
semantic judgement call, and it is the part of the diff most worth a second look.

## Constraints

- **English technical artifacts.** No user-facing copy changes, so no Spanish rules apply here.
- **Test coupling is zero** — the scout verified: no test asserts these literals, `toHaveClass` appears
  only for unrelated classes, and there are no `__snapshots__` files in `frontend/`. Nothing needs a
  test update.
- **Dark mode is not optional.** A site whose `dark:` counterpart is dropped is a defect, not a
  leftover.
- **The literal ban must be non-vacuous**: it has to fail if the scan finds no files, so a broken glob
  cannot pass silently.
- **Nothing changes appearance except at the table above.** Any other visual change is a bug.

## Evidence log

| Task | Commit | What ran, and what it proved |
| --- | --- | --- |
| 1 | `4ece390` | Guard written first and observed RED against a tree with no tokens (`Tests 3 failed | 3 passed`), then GREEN (`6 passed`). Diff is 23 insertions in `globals.css` and 131 in the guard; no existing line moved or reformatted. `tsc --noEmit` exit 0. |
| 2 | `eb8177c` | The guard's literal ban was added **before** any component changed and observed RED with all 73 offenders listed as `path:line: text`. After the migration: focused guard `8 passed`, suite **785/785 in 69 files**, `tsc --noEmit` exit 0, `git diff --stat` = 12 files `+131/-74`. |
| 3 (mechanical) | — | **The decisive check, run against the emitted CSS rather than the diff**, because an arbitrary-value class that fails to compile fails no build and no test. `pnpm build` exit 0; all **12** classes present in `.vercel/output/static/_astro/globals.DU6WaV3f.css` with their rule text. The composed opacities compile to `color-mix(in oklab, var(--color-warning) 10%\|15%, transparent)` **with a `#f99c001a` hex fallback that proves Tailwind resolved the variable all the way to amber-500**. Precedent confirmed: `bg-(--color-surface-secondary)/30` already existed at HEAD. Badge cascade measured — the variant's `bg-primary` rule sits at offset 32,575 and the arbitrary class at 30,822, so CSS order alone would render the owner badge blue; `tailwind-merge` inside `cn()` drops `bg-primary`, which is the same mechanism the pre-migration `bg-amber-500/15` relied on. All 23 `--color-*` names referenced by the 11 files are declared (no dangling `var()`), all 31 arbitrary utilities compile, 18 prerendered routes and Pagefind 9/locale unchanged. Ban proven non-vacuous read-only: **73 matches at HEAD, 0 in the tree**. |
| 3 (visual) | — | `/en/status` in both themes, measured in a real browser: every warning and destructive token resolved to its **exact** declared `oklch`, including the theme-invariant `--color-warning` (`oklch(0.769 0.188 70.08)` in both themes) and the dark `--color-destructive-bg` (`oklch(0.258 0.092 26.042 / 0.3)`). The catastrophic-failure detector passed: no element that asks for a colour resolved to `rgba(0,0,0,0)` or to an empty `var()`. Screenshots: `/tmp/status-light.png`, `/tmp/status-dark.png`. The dark load happened to render the degraded branch (`schema: Unknown`, see findings), so both the green/ok and the amber/degraded states were observed. |

### Not verified, and why

| Item | Why |
| --- | --- |
| Every authenticated surface (`AccountPage`, `DeleteAccountDialog`, `StoryForm`, `StoryDetail`, `TaskEditor`, `StatusPanel`'s authenticated siblings) | `/en/account` and `/en/stories` answer `302` to `/en/login`. The browser session was absent by design and the owner chose to review the running app himself. |
| `WorkspaceSettings`, `MemberManagement`, `LLMConfigEditor` | The dev database has been empty since the 0028 purge, so there is no workspace to open. |
| The destructive branch of `StatusPanel`, and the two `danger` banners that need a failure or a destructive action | Reaching them means breaking a required service or executing the action. Recorded, not fabricated. |
| `/es/status` in a real browser | The owner took control of the browser task space mid-run and the verifier stopped rather than retaking it. Static evidence only: both locales load the same `globals.css` and the tokens are defined on `:root` / `[data-theme='dark']` with no locale selector, so a locale cannot change them. |
| Visibility of the `divide-(--color-border)` dividers | The verifier saw computed `border-top-width: 0px` on the row children and did not conclude either way. |

## Findings recorded, not fixed

- The two token-consumption conventions coexist (`text-success-text` in
  `ImportStoriesDialog.tsx:291`, `text-(--color-success-text)` in `StatusPanel.tsx:35`).
- `--color-success` and the new `--color-warning` are theme-invariant while their trios are not; that
  asymmetry is inherited from the existing family, not introduced here.
- **A real pre-existing React defect, surfaced by the verification**: `StatusPanel.tsx:324,332` render
  `{coreRows.map(renderRow)}` and `{optionalRows.map(renderRow)}` while `renderRow` (`:266`) returns a
  `<div>` with no `key`, so the console logs `Each child in a list should have a unique "key" prop` on
  every status page load. A className-only diff cannot cause it and the migration did not touch it.
  **Cost of the fix: one line** — the rows carry a unique `title`, so `key={row.title}` on the
  returned element is enough. Not fixed: it is outside this feature's authorization, so it is offered
  to the owner as its own change rather than smuggled into a colour migration.
- The backend reported `schema: Unknown` on one of two browser loads, flipping the status page to the
  degraded branch, while three direct `GET /api/health/services` calls and the other load returned
  `schema: ok`. It is upstream of the visual layer — `frontend/src/pages/api/health/services.ts`
  forwards the body verbatim — and it is not a token problem. Left uncharacterised: it deserves its
  own look, not a guess inside this feature.

### Correction of record — a value I annotated without measuring it

The verification brief I handed the verifier carried a `→ #hex` column next to each expected
`oklch()`. **Nine of those eleven hexes were wrong**: they were Tailwind **v3** hexes attached to
Tailwind **v4** oklch values, which are different palettes (`amber-800` is `#92400e` in v3 and
`#973c00` in v4; `red-200` is `#fecaca` vs `#ffc9c9`). The verifier converted the real oklch values
and caught the mismatch, and the tokens themselves were never wrong — the guard asserts oklch strings
and the browser resolved them exactly.

The mistake matters because it is the same shape as the two falsehoods this feature exists to fix: I
asserted a derived value I had never measured. **Where it did not reach: this repository.** The
feature document and `globals.css` carry only oklch values and ramp names, verified by grep — the
wrong hexes lived in a brief, not in an artifact. Rule kept: never annotate a measured oklch with an
unmeasured hex; convert it or leave it out.

### Operational, for whoever resumes

- A stale `astro dev` from an earlier session was listening on **4321** and serving pre-migration
  behaviour (`200` on `/en/dashboard` where the current middleware answers `302`). It was left
  untouched; a fresh server owned by this session ran on **4322**.
- The first freshness test I ran was worthless and I said it backwards at the time: grepping the dev
  HTML for the new tokens proves nothing, because the dev server does not inline the stylesheet. The
  `302` versus `200` divergence was the real evidence.
