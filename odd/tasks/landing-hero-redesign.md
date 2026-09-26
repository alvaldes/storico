# ODD Feature: landing-hero-redesign

> **Status**: done — `a59a7d4 feat(landing)` plus `ad27f03 feat(landing)`, on
> `feat/landing-live-demo`, stacked after `5afb7fb fix(landing): zoom the embedded demo so its story
> fits small screens`. Nothing pushed.
> **Created**: 2026-09-26
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.

## Problem

The landing hero was laid out as two flex partners: a copy column capped at `max-w-[565px]` and,
beside it, a decorative phone mockup that rendered only at `lg` and above (`hidden lg:flex`). Below
`lg` the mockup did not exist at all, so the cap made the hero copy a narrow ribbon on every
viewport that could not show the mockup anyway — including the whole `lg`-and-up range, where the
copy was capped at 565px inside an ~1120px content box while the mockup carried the remaining width.

Once the mockup was removed, the cap had no partner to justify it: the copy stayed a 565px ribbon
centered in a full-width row by `justify-around`, which is the *opposite* defect — a wide container
with a narrow, oddly centered column and no visual reason for the leftover space.

The second, independent defect surfaced by the same change: with the cap gone, a full-width hero
paragraph runs ~1120px at `md:text-lg`. That is ~130 characters per line. Comfortable prose measures
sit between 45 and 75 characters; past that the eye loses the line return and re-reads lines. The
container could stay full width, but the *text* could not.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Mockup | Deleted outright, not hidden. It was decorative, it duplicated the live demo embed that now sits in the same hero, and keeping it behind a flag would leave dead markup plus nine dead tokens. Owner's call, given directly. |
| D2 | Tokens | The token set that only the mockup consumed — `--color-mockup-bg/-header/-border/-task-bg/-task-border/-text/-muted/-label` in both themes, plus `--shadow-phone` — is deleted with the markup. Verified used nowhere else before deleting. |
| D3 | Hero arrangement | Adopt the recipe inkdrop.app's masthead headline uses, chosen by the owner by URL: one centered column, `text-align: center`, title and subtitle as a single vertical pair, badge and CTAs centered with them. Not a two-column hero with a centered caption, and not a left-aligned hero. |
| D4 | Type scale | Title `text-4xl`/`md:text-5xl`/`lg:text-6xl` (36/48/60px), subtitle `text-lg`/`md:text-2xl`/`lg:text-3xl` (18/24/30px). A uniform 0.5 subtitle-to-title ratio, on the project's existing Tailwind scale. Inkdrop's own ratio is 0.45–0.51 across its breakpoints (`calc(var(--h3) * .9)` against `var(--h1)`, 1.8em/4em at ≥1200px). |
| D5 | Heading face | Space Grotesk stays. Inkdrop sets its `h1`/`h2` in `p22-mackinac-pro`, a licensed Adobe Typekit serif that is not in this repository and is not free to add; Space Grotesk is already the project's heading face (about, terms, features). The *arrangement* is what was asked for. Whether to introduce a display serif is recorded as an open decision below, not answered silently. |
| D6 | Copy | Unchanged, in both locales. The `en.json`/`es.json` hero strings are inputs to the problem, not part of the fix, and the `/i18n` tests assert key parity between them. |
| D7 | Measure | The readability defect is fixed by `text-wrap: balance` on the title and a `60ch` cap plus `text-wrap: pretty` on the subtitle — a constraint on the text, never on the container. The container stays full width, which is what the owner asked for. |

## Non-goals

- No change to the live demo embed, to its `#demo` anchor, or to the `demo-frame` zoom that applies
  below `lg`. That mechanism was settled in `odd/tasks/landing-live-demo.md` and is untouched.
- No change to the badge or CTA copy, and no new CTA.
- No new font dependency, no `@font-face`, no Adobe Typekit link.
- No change to the Features, FAQ or closing CTA sections, and none to the shared `PublicLayout`.
- No unit test. There is no test harness for `.astro` templates in this repository (see
  `odd/tasks/public-footer-auth-links.md`, F2); the claims here are checked against the rendered
  anonymous HTML and the production build.

## Tasks

- [x] T1 — Delete the phone mockup block from `frontend/src/pages/[locale]/index.astro`.
- [x] T2 — Delete the nine dead tokens and `--shadow-phone` from `frontend/src/styles/globals.css`,
      after proving no consumer remained.
- [x] T3 — Restructure the hero title and subtitle to the inkdrop arrangement (D3, D4, D7).
- [x] T4 — Record the reversal in `odd/tasks/landing-live-demo.md`, whose "out of scope" section
      still claimed the mockup stayed as it was.
- [x] T5 — Verify: frontend suite, production build, and the rendered anonymous landing.
- [x] T6 — Commit the work units on `feat/landing-live-demo` and record the identities here.

T1 and T2 were executed inline earlier in the same session, before this feature was classified as
substantial and this record existed. They are listed as tasks rather than quietly folded into
"problem" because that is the order things actually happened.

## Verification

- `cd frontend && npx vitest run`
- `cd frontend && npx astro build`
- `curl -sS http://127.0.0.1:4321/en/` and `/es/`: the response must contain **zero** occurrences of
  `mockup`, and must still carry the hero copy, the `#demo` anchor and the demo iframe.
- Rendered check of the hero at mobile, `md` and `lg` widths.

## Evidence

`grep -rn "mockup" frontend/src` → 0 matches, and `grep -rlo "color-mockup" frontend/dist
frontend/.vercel` → 0 files, so no other rule re-emitted the tokens. `--shadow-card`,
`--shadow-primary-sm` and `--shadow-primary-lg` in the same group keep real consumers and were left
alone.

`npx astro build` completes; `npx vitest run` reports `Test Files 50 passed` / `Tests 567 passed`
on the tree carrying T1, T2 and T4, and again on the tree carrying T3.

Each work unit was committed from a tree that builds:

| Commit | Work unit |
|--------|-----------|
| `a59a7d4` | `feat(landing): retire the phone mockup so the hero copy fills the width` — T1, T2 |
| `ad27f03` | `feat(landing): arrange the hero title and subtitle as a centered pair` — T3 |

The rendered anonymous landing (`astro dev`, served on port 4322 because another dev server already
held 4321) returns 200 at 58,260 bytes in `/en/`, with **0** occurrences of `mockup`, **1**
`id="demo"` and **1** `<iframe>` — the mockup is gone and the demo embed is intact in the same
response.

Computed values read from the rendered page with `getComputedStyle`:

| Locale | Element | Font | Lines | `text-wrap` |
|--------|---------|------|-------|-------------|
| `/en/` at 1440px | `h1` | 60px | 2 | `balance` |
| `/es/` at 1440px | `h1` | 60px | 2 | `balance` |
| `/es/` at 1440px | subtitle | 30px | 2 | `pretty` |

The Spanish subtitle is the longest hero string in either locale at 138 characters, and it now lands
at ~69 characters per line — inside the 45–75 range the problem statement asks for, down from the
~130 the uncapped wide paragraph produced. Visually checked at 390px, 820px and 1440px in English
and at 1440px in Spanish: one centered column at all three widths, two-line title above two-line
subtitle at `lg`, three-line title at 390px, no line running off the container and no overlapping
watermark.

## Open decisions

| # | Question | State |
|---|----------|-------|
| O1 | Introduce a display serif for the hero `h1` to match inkdrop's actual face? | Open. Options put to the owner: keep Space Grotesk (current), or add a free display serif (Fraunces, Instrument Serif, Playfair Display) as a landing-only face. Not decided, not applied. |
| O2 | Should the hero title copy become a sentence with a period, the way inkdrop's is ("Your context, beautifully organized.")? | Open. Current titles are fragments in both locales; the arrangement works for either. Not decided, no copy touched. |
