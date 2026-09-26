# ODD Feature: landing-hero-redesign

> **Status**: done — `a59a7d4`, `ad27f03`, `bf233fa` and `8753a65`, on `feat/landing-live-demo`,
> stacked after `5afb7fb fix(landing): zoom the embedded demo so its story fits small screens`.
> Nothing pushed.
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
| D4 | Type scale | **Superseded by D8.** Originally title `text-4xl`/`md:text-5xl`/`lg:text-6xl` (36/48/60px), subtitle `text-lg`/`md:text-2xl`/`lg:text-3xl` (18/24/30px) — a uniform 0.5 subtitle-to-title ratio on the project's own Tailwind scale. Inkdrop's ratio is 0.45–0.51 across its breakpoints (`calc(var(--h3) * .9)` against `var(--h1)`, 1.8em/4em at ≥1200px). Written down as what `ad27f03` shipped, not as what stands. |
| D5 | Heading face | Space Grotesk stays. Inkdrop sets its `h1`/`h2` in `p22-mackinac-pro`, a licensed Adobe Typekit serif that is not in this repository and is not free to add; Space Grotesk is already the project's heading face (about, terms, features). The *arrangement* is what was asked for. Whether to introduce a display serif is recorded as an open decision below, not answered silently. |
| D6 | Copy | **Superseded by D9.** Unchanged in both locales through `ad27f03`: the `en.json`/`es.json` hero strings were inputs to the problem, not part of the fix. |
| D7 | Measure | The readability defect is fixed by `text-wrap: balance` on the title and a `60ch` cap plus `text-wrap: pretty` on the subtitle — a constraint on the text, never on the container. The container stays full width, which is what the owner asked for. |
| D8 | Delivered scale | The owner downscaled one step after reading `ad27f03` in the browser, and that is the scale that stands: title `text-3xl`/`md:text-4xl`/`lg:text-5xl` (30/36/48px), subtitle `text-lg`/`md:text-xl`/`lg:text-2xl` (18/20/24px). The ratios become 0.60 / 0.56 / 0.50, so the pair is no longer uniform: only `lg` lands in inkdrop's 0.45–0.51 band and mobile drifts to 0.60. Kept exactly as the owner set it, with the drift written down instead of silently re-normalized. |
| D9 | Copy | Adopt **set A** of the four measured options, in both locales: `Your backlog, already broken down.` and `Paste a user story. Get structured Kanban tasks, ready to edit and export.` / `Tu backlog, ya desglosado en tareas.` and `Pega una historia de usuario. Obtén tareas Kanban listas para editar y exportar.` Chosen by the owner from candidates measured against this tree. It is the only set that reproduces inkdrop's *structure* — possessive, comma, state, period — and not merely its brevity. |
| D10 | `md` subtitle step | The `md:text-1xl` the owner wrote when downscaling the scale **is not a Tailwind class**. It matches no scale step, emits no CSS, and left the subtitle at 18px through `md` — measured, not inferred. Corrected to `md:text-xl` (20px), which is what the owner meant. |
| D11 | Hero copy is an accessible name | `hero.subtitle` is not only a paragraph: it is interpolated into the demo iframe's `title` as `` `${t.app.name}: ${t.landing.hero.subtitle}` ``, so the string must stand on its own and must not open with the product name, or a screen reader announces "Storico: Storico…". Every candidate respected this, and the rendered result was checked. |
| D12 | Sealed order | The owner moved the badge and the CTA row out of the hero copy column and, shown the diff, chose to keep that order: the section reads copy → `#demo` → CTAs → badge, and the badge is centered with `self-center` rather than by adding `items-center` to the section, which would have re-shrunk the CTA row as a side effect. The badge therefore reads as a closing label for the hero rather than as an eyebrow above the title — a compositional consequence the owner accepted when choosing this option. |

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
- [x] T7 — Fix the dead `md:text-1xl` step introduced by the owner's downscale (D10), in the same
      commit as that downscale, which had never been committed.
- [x] T8 — Apply copy set A to `frontend/src/i18n/en.json` and `frontend/src/i18n/es.json` (D9).
- [x] T9 — Re-verify after the copy change: suite, build, both locales at three widths, and the
      interpolated iframe title.
- [x] T10 — Center the moved badge with `self-center` (D12), leaving the CTA row's stretching alone
      because fixing it was not what was asked.
- [x] T11 — Commit the settled scale, order and badge alignment as one work unit, and say why it is
      one and not three.

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
| `bf233fa` | `feat(landing): rewrite the hero title and subtitle as a sentence pair` — T8 |
| `8753a65` | `feat(landing): settle the hero scale, order and badge alignment` — T7, T10 |

The rendered anonymous landing (`astro dev`, served on port 4322 because another dev server already
held 4321) returns 200 at 58,260 bytes in `/en/`, with **0** occurrences of `mockup`, **1**
`id="demo"` and **1** `<iframe>` — the mockup is gone and the demo embed is intact in the same
response.

`8753a65` is deliberately one commit for three changes (the scale, the order, the badge alignment).
They share lines and hunks: committing the scale alone would have required materializing a tree the
owner never had on disk, which is fabrication rather than history.

Computed values read from the rendered page with `getComputedStyle`, **as of `ad27f03`**. The table
is kept because it is what that commit shipped, but the scale it measures was replaced by D8; see
the second table for what stands.

| Locale | Element | Font | Lines | `text-wrap` |
|--------|---------|------|-------|-------------|
| `/en/` at 1440px | `h1` | 60px | 2 | `balance` |
| `/es/` at 1440px | `h1` | 60px | 2 | `balance` |
| `/es/` at 1440px | subtitle | 30px | 2 | `pretty` |

At 60px the Spanish subtitle ran ~69 characters per line, down from the ~130 the uncapped wide
paragraph produced. Visually checked at 390px, 820px and 1440px in English and at 1440px in Spanish:
one centered column at all three widths, two-line title above two-line subtitle at `lg`, three-line
title at 390px, no line running off the container and no overlapping watermark.

### After D8, D9 and D10 — current

Measured the same way, on the tree that carries T7 and T8, in **both** locales at three widths. Line
counts come from `Range.getClientRects()` on the live element, not from `height / line-height`:

| Locale | Width | Title | Title lines | Subtitle | Subtitle lines |
|--------|-------|-------|------------|----------|----------------|
| `en` | 1440px (`lg`) | 48px | 1 | 24px | 1 |
| `en` | 820px (`md`) | 36px | 1 | 20px | 1 |
| `en` | 390px | 30px | 2 | 18px | 2 |
| `es` | 1440px (`lg`) | 48px | 1 | 24px | 1 |
| `es` | 820px (`md`) | 36px | 1 | 20px | 1 |
| `es` | 390px | 30px | 2 | 18px | 3 |

The `md` row is the observation that proves D10: the subtitle reads **20px**, where the dead
`md:text-1xl` left it at 18px. The candidate line counts used to choose the copy were measured on
this same tree and are what the three expected sets were read against.

The interpolated accessible name was read off the live DOM after the copy change:

- `/en/` → `Storico: Paste a user story. Get structured Kanban tasks, ready to edit and export.`
- `/es/` → `Storico: Pega una historia de usuario. Obtén tareas Kanban listas para editar y exportar.`

No product-name repetition in either, and both stand as sentences.

The neutral-Spanish claim is not an eyeball. The 55 words of `VOSEO_FORMS` were extracted from
`frontend/src/i18n/__tests__/neutral-spanish.test.ts` and the detector was run against the six
Spanish candidates before the owner chose; all six returned `OK`. The suite then re-checked the two
that were applied, and `Test Files 50 passed` / `Tests 567 passed` stands on the final tree, which
includes the key-parity and neutral-Spanish assertions.

One correction to this record's own earlier reasoning: the `60ch` cap is **not** 60 characters. `ch`
is the advance of the digit `0`, which is ~0.63em in Inter, while the average lowercase letter is
~0.55em; the cap resolves to 908px at 24px and the measured Spanish line ran 69 characters. A true
60-character measure at that size would be ~`52ch`. Recorded, not changed — the delivered measure
sits inside the 45–75 band either way.

### After D12 — the sealed order

Badge geometry read off the rendered section, both locales, three widths. `left`/`right` are the
distances from the badge to the section's own edges:

| Locale | Width | Badge | `left` | `right` | Centered |
|--------|-------|-------|--------|---------|----------|
| `en` | 1440 / 820 / 390px | 254px | 433 / 251 / 52 | 433 / 251 / 52 | yes |
| `es` | 1440 / 820 / 390px | 240px | 440 / 258 / 59 | 440 / 258 / 59 | yes |

Section children read as `div -> demo -> div -> span` at every width in both locales, which is D12's
order.

One consequence of the move is measured rather than argued: at **390px** the two CTA buttons render
**358px** wide — full section width — because the CTA row is now a direct child of a
stretch-aligned `flex flex-col` section instead of a child of the `items-center` copy column. At
820px and 1440px they stay content width (144px and 146px in `en`, 134px and 132px in `es`) and
centered. Left as measured: making the row shrink-to-fit again is `items-center` on the section,
which was not what was asked for, and full-width stacked CTAs are a legitimate mobile pattern.

## Open decisions

| # | Question | State |
|---|----------|-------|
| O1 | Introduce a display serif for the hero `h1` to match inkdrop's actual face? | Open. Options put to the owner: keep Space Grotesk (current), or add a free display serif (Fraunces, Instrument Serif, Playfair Display) as a landing-only face. Not decided, not applied. |
| O2 | Should the hero title copy become a sentence with a period, the way inkdrop's is? | **Resolved** by D9: set A, applied in both locales. |
