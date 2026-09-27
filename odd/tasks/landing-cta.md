# ODD Feature: landing-cta

> **Status**: done — `feat(landing)` on `feat/landing-live-demo`, stacked after
> `5c17bc2 feat(landing): move the badge into the features section as its eyebrow`. Nothing pushed.
> **Created**: 2026-09-26
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.

## Problem

The hero's call to action read two different things depending on the session, and neither was a call
to action:

```astro
{isLoggedIn ? t.nav.dashboard : t.landing.hero.cta_primary}   // "Dashboard" / "Get Started"
```

The signed-in half borrowed `nav.dashboard`, which is the label the sidebar, the breadcrumb, the
footer and the user menu all use. A visitor who already has a session was being offered their own
navigation, verbatim. The signed-out half was the generic "Get Started" — the reference site's own
masthead button says "Start your 30-day free trial", which is specific about what starts and what it
costs. Ours said neither.

Visually it was a 16px solid button, `rounded-lg`, with `--shadow-primary-sm`, no direction indicator
and no size advantage over the secondary button beside it.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Visual treatment | **C** of three rendered candidates: `bg-linear-to-b` from `--color-primary-500` to `--color-primary-700`, plus a two-layer shadow — a 4px ring in the brand colour and a coloured drop shadow — with a `-translate-y-px` lift and a deeper ring on hover. Chosen by the owner from live renders. Option A was the gradient alone and B the solid fill with a deeper shadow; C is the one that reads as *the* action on the page. |
| D2 | Signed-out copy | `Break down your first story` / `Desglosa tu primera historia`. Option 1 of four rendered. Specific about the action, honest about the scope (one story), and it does not promise pricing inside the button. |
| D3 | Signed-in copy | `Open your board` / `Abre tu tablero`, in a **new key** `landing.hero.cta_authed`. `nav.dashboard` stays untouched: it is a navigation label in six places and must not bend to a button. |
| D4 | The navbar does not follow | The navbar keeps "Get Started" / "Comienza", and it now reads `nav.cta_label` instead of the hero's key, so the hero's longer copy cannot leak into it. Rendering is unchanged: the same two strings, in a key that says where they are used. Also makes the split honest — a nav label lives under `nav`, a hero button under `landing.hero`. |
| D5 | Where the shadows live | Two theme tokens, `--shadow-cta` and `--shadow-cta-hover`, in `@theme`, rather than long arbitrary `shadow-[…]` values in the class list. The project already keeps `--shadow-primary-sm/-lg` this way, and `color-mix(in oklch, …)` inside an arbitrary Tailwind value needs underscore escaping that is easy to get wrong. |
| D6 | Geometry | 17px text, `px-7.5` (30px), `py-4.25` (17px), `rounded-lg` (12px), arrow 17px with a 10px gap. The radius is `rounded-lg` and not `rounded-xl` because **this theme redefines the radius scale** (`--radius-xl: 1rem`), so `rounded-xl` renders 16px, not 12px — confirmed against the computed value after the first attempt shipped 16px. |

## Non-goals

- The navbar's copy and treatment are unchanged (D4).
- The hero's secondary "View Demo" button is **not restored**. The owner removed it in an uncommitted
  edit that `5c17bc2` then carried (disclosed in that commit's message, since it was staged without
  the file's full diff being read first). Two consequences left standing, not fixed:
  `#demo` no longer has an in-page link anywhere — the embed script's
  `#demo iframe[data-target-origin]` selector is the only remaining reference to it — and
  `landing.hero.cta_secondary` is unconsumed.
- Three unconsumed i18n keys are reported rather than deleted, because they did not die from this
  change: `landing.hero.cta_secondary`, `landing.cta_start` ("Get Started") and `landing.cta_learn`
  ("Learn More"), each with zero consumers in `src`. Removing them is a cleanup of its own.
- No change to where the buttons link. Both states still go to `/dashboard` or `/login`.
- No unit test. The string is read from `en.json`/`es.json` and asserted for parity and neutral
  Spanish by the existing i18n suite; the geometry is checked against the rendered page.

## Tasks

- [x] T1 — `en.json` / `es.json`: new hero copy, new `cta_authed` key, new `nav.cta_label` key.
- [x] T2 — `PublicLayout.astro`: point `ctaLink` at `nav.cta_label` so the navbar is untouched.
- [x] T3 — `index.astro`: treatment C, the arrow, and the label expression off `cta_authed`.
- [x] T4 — `globals.css`: `--shadow-cta` and `--shadow-cta-hover`.
- [x] T5 — Verify: suite, build, computed geometry, and that the navbar still renders its own label in
      both locales.
- [x] T6 — Commit and record the numbers here.

## Verification

- `cd frontend && npx vitest run` → `Test Files 50 passed`, `Tests 567 passed`.
- `cd frontend && npx astro build` → complete.
- Rendered `/en/`, read with `getComputedStyle` on the hero's primary anchor.

## Evidence

Measured on the rendered page, `/en/` at 1440px, forced to the light theme:

| Property | Value |
|---|---|
| label | `Break down your first story` |
| `font-size` | 17px |
| `padding` | 17px 30px |
| `border-radius` | 12px |
| `background-image` | `linear-gradient(oklch(0.55 0.15 250) 0%, oklch(0.39 0.12 250) 100%)` |
| `box-shadow` | includes `oklch(0.47 0.14 250 / …)` — the ring layer resolved in the brand colour |
| arrow | 17x17, inside the anchor |
| box | 310x60 |

The first attempt shipped `border-radius: 16px`: the class said `rounded-xl` and this theme maps that
token to `1rem`. Caught by reading the computed value rather than trusting the class name, and
corrected to `rounded-lg`.

The navbar was checked separately, because D4 is the part most likely to break silently: `/en/`
contains exactly **1** anchor labelled `Get Started` (the navbar's own), and `/es/` still renders
`Comienza` **2** times — its desktop and mobile nav buttons — with zero occurrences of `Ver demo`,
matching the owner's removal of the hero's secondary button. The hero's own label appears once in each
locale and never in the other language's build.
