# ODD Feature: landing-features-section

> **Status**: done — `9a17ddf feat(landing)`, on `feat/landing-live-demo`, stacked after
> `525abf8 docs(odd): close the landing hero redesign`. Nothing pushed.
> **Created**: 2026-09-26
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.

## Problem

The second landing section, "Everything you need to manage your backlog", is three floating shadcn
`Card`s in a `flex-wrap` row under a centred header, hydrated from a React island. The owner asked
for it to look like inkdrop.app's "Less friction between you and your agents" section, and that
section is a different composition entirely: one raised box holding a headline band and a band of
joined columns, with no floating cards and no gaps.

The reference was measured in the browser rather than read off its stylesheet, so the numbers below
are computed values from the live page at a 1352px viewport:

| Element | Measured |
|---------|----------|
| `.ui.raised.segments` (the container) | 1138px wide, radius 15px, no visible border, two-layer shadow `0 2px 4px rgba(34,36,38,.12)`, `0 2px 10px rgba(34,36,38,.15)` |
| `.ui.headline.segment` | padding `28px 300px 28px 28px`, left-aligned text (the 300px right padding reserves the illustration) |
| headline `h2` | 35px, weight 500, `p22-mackinac-pro` serif, `margin-bottom: 17.5px` |
| `.landing-section-lead` | 20px, weight 300, `opacity: .85`, sans, 810px wide |
| `.ui.horizontal.segments` | `display: flex`, `overflow-x: auto`, `scroll-snap-type: x proximity` |
| each feature column | `flex: 1 0 280px`, `padding: 14px`, `border-left: 1px` (removed on the first), `flex-direction: column` |
| icon box | `flex: 0 0 100px`, `justify-content: center`, `align-items: center`; the SVGs inside measure 46px and 92px |
| feature `h3` | 20px, weight 300, `margin-bottom: 10px` |
| feature `p` | 14px / 20px line-height, `color: rgba(0,0,0,.6)`, `margin-bottom: 14px` |
| ghost button | 14px, `padding: 11px 14px`, radius 15px, transparent, `align-self: start`, `margin-top: auto` |

The island is the second half of the problem. `FeatureCards.tsx` has no state, no props that change,
and no handlers, yet it ships as a hydrated React island: the rendered landing carries **4**
`astro-island` elements, one of them is this section, and the three feature titles exist only inside
the island's serialized `props` attribute — not as text in the document.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Composition | One raised container with a headline band on top and a band of joined columns below, divided by 1px lines. Not floating cards with gaps, and not a two-band layout with separate boxes. Owner's instruction, by reference URL. |
| D2 | Mobile | Horizontal snap carousel, exactly like the reference: the columns keep a 280px basis and the row scrolls, instead of stacking. Chosen by the owner over stacking and over stacking-with-dividers. It hides two of the three features behind a swipe, which is the cost the owner accepted for matching the reference. |
| D3 | Ghost buttons | **Omitted.** The reference puts a "Learn more" ghost button in each column, pinned to the bottom with `margin-top: auto`. We have no destination for any of the three features, and inventing links is exactly the dead-end class that `odd/tasks/public-footer-auth-links.md` removed elsewhere. Owner's choice: omit. The bottom-alignment idiom goes with it, since there is nothing left to align. |
| D4 | Icons | Chromeless, centred in a 100px box, like the reference — no coloured tile behind them. Owner's choice over keeping the tiles and over keeping the tiles' accent colour on the stroke alone. |
| D5 | Icon implementation | The three icons are inlined as raw `<svg>` in an `.astro` component, carrying lucide's own path data, rather than adding `lucide-astro` or keeping React components. `lucide-react` is a React package and cannot be used from an `.astro` file; inlining two `path` elements and two `circle`/`line` sets beats a new dependency, and matches `GitHubIcon.astro`. |
| D6 | Island | `FeatureCards.tsx` is replaced by an `.astro` component and deleted. It has no interactivity, and ADR-001 limits React to islands that need it. This is the only decision here that also deletes JavaScript. |
| D7 | Tokens | The six `--color-accent-{blue,green,orange}-{bg,icon}` tokens in both themes lose their only consumer with D4 and are deleted. Same rule as the mockup token purge in this feature's sibling record: prove no consumer remains, then take the tokens with the markup. |
| D8 | Typography | Keep the project's voice where it would otherwise be a rebrand: `h2` stays Space Grotesk extrabold (the reference's 35px/500 serif is its own brand face), `h3` stays semibold, and body colours use `--color-text-secondary`. The reference's *geometry, alignment, grouping and dividers* are what is being adopted. Column padding is scaled up from the reference's 14px to `20px`/`24px` at `lg` because our columns are ~373px wide against its 285px, and 14px reads cramped at that width. |

## Non-goals

- **The headline illustration.** The reference reserves 300px on the right of the headline band for a
  hand-drawn illustration (`section-ainative.png`, 280px). We have no such asset, and generating one
  or commissioning it is not a call this record can make. Recorded as O1. Without it the headline
  band drops the 300px right padding and keeps the 28px the reference uses everywhere else.
- **The eyebrow pill.** The reference puts an "AI native" pill above the `h2`. No such key exists in
  `en.json`/`es.json`, and adding copy in two locales for a decorative pill is its own decision.
  Recorded as O2.
- No copy change: `landing.features.title`, `landing.features.subtitle` and the three
  `card_N_title`/`card_N_desc` pairs are used as they are, in both locales.
- No change to the hero, the demo embed, or the FAQ section, and none to `PublicLayout`.
- No change to the three features themselves, to their icons, or to how many there are.
- No unit test. There is no harness for `.astro` templates in this repository (see
  `odd/tasks/public-footer-auth-links.md`, F2); the claims are checked against the rendered page.

## Tasks

- [x] T1 — Add `frontend/src/components/astro/FeatureSegments.astro`: raised container, headline band,
      joined column band, snap carousel below the container width (D1, D2, D4, D5, D8).
- [x] T2 — `frontend/src/pages/[locale]/index.astro`: render it, drop the `client:idle` island and the
      now-unused `color` field.
- [x] T3 — Delete `frontend/src/components/react/FeatureCards.tsx` (D6).
- [x] T4 — Delete the six dead accent tokens from `frontend/src/styles/globals.css`, both themes (D7).
- [x] T5 — Verify: suite, build, rendered geometry at three widths, the carousel's scrollability, and
      the island count going from 4 to 3.
- [x] T6 — Commit the work units and record the identities and the numbers here.

## Verification

- `cd frontend && npx vitest run`
- `cd frontend && npx astro build`
- Rendered page: the container's radius and shadow, the headline band's padding, the 1px dividers
  between columns, the 100px icon box, and the column count.
- Carousel: `scrollWidth > clientWidth` at 390px with `overflow-x: auto` and a computed
  `scroll-snap-type` on the row; `scrollWidth === clientWidth` at 1440px.
- Island count in the rendered landing HTML, before and after: `grep -c '<astro-island'`.
- The three feature titles must appear as element text, not only inside an island's `props` attribute.

## Evidence

**Before**, captured from the running dev server on the current tree (`/en/`, 58,175 bytes): the
landing carries **4** `astro-island` elements — `ThemeToggle`, `MobileNav`, `FeatureCards`,
`FaqAccordion` — and the feature copy is visible in the response only as escaped JSON inside
`props="{&quot;cards&quot;:[[0,{&quot;title&quot;:[0,&quot;Automatic Extraction&quot;]…`.

**After the same capture** (`/en/`, 57,976 bytes): **3** islands — `ThemeToggle`, `MobileNav`,
`FaqAccordion` — with `FeatureCards.tsx` gone from the list, and `Automatic Extraction` present as
element text: `…ata-astro-source-loc="106:65">Automatic Extraction</h3> <p class="text-sm leading-5
text-(`. No `props=` payload carrying the card copy exists anywhere in the response.

Rendered geometry, read with `getComputedStyle` and `getBoundingClientRect` on `/en/`:

| | 1440px (`lg`) | 820px (`md`) | 390px |
|---|---|---|---|
| container | 1120x392, radius 16px, `oklch(0.99 0 0)` | 740x472 | 358x477 |
| headline band padding | 28px | 28px | 28px |
| `h2` | 36px, left | 36px, left | 24px, left |
| lead | 20px, `opacity .85`, 656px wide | 20px, 656px | 18px, 302px |
| column band | `scrollWidth 1120 == clientWidth 1120`, not scrollable | `840 > 740`, scrollable | `840 > 358`, scrollable |
| computed on the band | `overflow-x: auto`, `scroll-snap-type: x` | same | same |
| columns | 3 x 373px | 3 x 280px | 3 x 280px |
| dividers | first column `border-left: 0`, the rest `1px` | same | same |
| column padding | 24px | 20px | 20px |
| icon box / icon | 100px / 48x48 | same | same |
| `h3` / `p` | 20px 600 / 14px-20px | same | same |

`npx astro build` completes; `npx vitest run` reports `Test Files 50 passed` / `Tests 567 passed`.

Dark theme checked separately, by setting `localStorage['theme']` and reloading: the container reads
`rgb(15, 20, 29)` against the page's `#0b0f17` body and the divider resolves to
`oklch(0.25 0.01 260)`, so the raised grouping survives the theme swap instead of flattening into the
background.

One deviation found by measuring rather than by taste, and corrected: the reference's lead is exactly
20px, and the first draft had `text-base md:text-lg` (16/18). It is now `text-lg md:text-xl`.

## Open decisions

| # | Question | State |
|---|----------|-------|
| O1 | Illustrate the headline band the way the reference does? | Open. Needs an asset we do not have. |
| O2 | Add an eyebrow pill above the section `h2`, as the reference has? | Open. Needs new copy in `en.json` and `es.json`. |
