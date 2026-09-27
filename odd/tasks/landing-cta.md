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

---

## Follow-up: the attention hop (D7) and the disconnection question

The owner's next report was two requests in one sentence: *the CTA looks a bit disconnected there,
give me options — but for now add a bounce animation that highlights it and moves the user's focus to
this button.* Those are two different problems and the record keeps them apart, because the animation
does not fix the disconnection.

### D7 — The hop

| Aspect | Decision |
|---|---|
| Trigger | `IntersectionObserver` at `threshold: 0.6`, wired on `astro:page-load`. The button sits **1146px** down a 760px viewport, so it is off-screen on load and a page-load animation would never be seen. |
| Repetition | Once. The observer disconnects on the first hit; the class is never removed. |
| Motion | Damped bounce: 16px, then 7px, then 2px, then rest, over 1050ms, with a per-segment `cubic-bezier` so each arc leaves fast (`0.16, 1, 0.3, 1`) and falls under gravity (`0.5, 0, 1, 0.5`) instead of riding a sine wave. |
| Extra | A 2px ring in `--color-primary-400` expands to 1.3x and fades over 700ms on the first launch. |
| Focus | **Deliberately not `.focus()`ed.** Taking focus on scroll reorders the tab sequence and scrolls the document out from under the visitor. Visual attention only. |
| Reduced motion | Already covered by the global clamp at the bottom of `globals.css`; verified below rather than assumed. |

### Evidence

`requestAnimationFrame` is not a measuring instrument in headless: it returned **5 frames in 1400ms**.
The curve was instead read by pausing the CSS animation through the Web Animations API and seeking
`currentTime`, which is deterministic.

| `currentTime` (ms) | 0 | 115 | 230 | 340 | 460 | 570 | 650 | 720 | 820 | 900 | 955 | 1050 | 1200 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `translateY` (px) | 0 | -15.54 | **-16** | -13.72 | -1.84 | -6.89 | **-7** | -6.25 | -0.09 | -1.97 | **-2** | 0 | 0 |

Timing: `duration 1050ms`, `fill none`, `iterations 1`; the ring is `700ms`, `fill none`.

Rest state, after `finish()` on both animations: `0` running animations, the button reads
`transform: none` and the ring reads `opacity: 0`. Nothing is left pinned, so the hover lift still
belongs to the button afterwards.

Emulated `prefers-reduced-motion: reduce` → computed `animation-duration: 1e-05s`. The global clamp
reaches this animation without a local guard.

**A comment written here was wrong and was corrected before it shipped.** It claimed a `forwards` fill
mode would strand `hover:-translate-y-px`. Tailwind v4's translate utilities emit the standalone
`translate` property, not `transform`, so the two compose instead of competing — confirmed by reading
both mid-flight: `translate: 0px -1px` alongside `transform: matrix(1, 0, 0, 1, 0, -1.04708)`. The
comment now states the property split instead of a cascade rule that does not apply.

### The disconnection, measured

Not an opinion — the geometry that produced the report:

| | value |
|---|---|
| gap, demo → CTA | **64px** (the section's `gap-16`) |
| gap, CTA → next visible surface (the features card) | **150px** (100px section padding + 50px features padding) |
| CTA box | 310x60 |
| its row | 1120px wide, `siblingsInCtaRow: 1` |

A 310px object alone in a 1120px row, with 2.3x more air below it than above. It is closer to the demo
than to the features band, so it reads as the demo's orphan.

### Five rendered options (open — awaiting the owner's pick)

Preview page: `/tmp/cta-options.html`, built from the real theme tokens; panels in
`/tmp/storico-shots/cta-conn-{HOY,A,B,C,D}.png`.

| Option | Move | Cost | Risk |
|---|---|---|---|
| **A · Demo caption** | gap above 64 → 20px | one spacing value | none; pure proximity |
| **B · Microcopy** | keep the position, add a reassurance line under the button | 2 i18n keys, must pass the neutral-Spanish test | needs copy that does not over-promise |
| **C · Up into the headline** | title → subtitle → CTA → demo, the reference site's own order | reorders the hero | **reverses D12 of `landing-hero-redesign.md`**, where the owner sealed copy → demo → CTAs. Also relocates the hop or makes it moot, since there is no scroll left to trigger it |
| **D · On a band** | the CTA gets a tinted full-width surface with hairline borders | a new section-like band | heaviest option; reads as a section closing |

Nothing was implemented from this table. The hop shipped because it was explicitly asked for; the
disconnection is the owner's call.
