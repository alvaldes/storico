# ODD Feature: navbar-link-centering

> **Status**: done — `c5a6446 fix(nav)` plus `docs(odd)` carrying this record, on
> `fix/navbar-link-centering`, stacked on `fix/mobile-sheet-overflow` (the head of a four-branch
> chain). Nothing pushed.
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.

## Problem

Reported as "the Documentation / API Reference / Status links are not in the centre of the screen".
Measured before touching anything, and the report did not survive contact with the instrument:

| Surface | Offset from the viewport centre |
|---|---|
| The header's link group, at 10 widths from 1024 to 2560 | **0px at every width** |
| The same, on `https://storico.vercel.app` | **0px** |
| Logo distance from the left edge vs controls distance from the right edge | **equal** (80/80 … 720/720) |
| The footer's Resources column, which holds the same three links | **+259.4px** (by design: `justify-between` over four columns) |

The group really was on the viewport's centre line. What was **not** symmetric was the space around
it, and that is what the owner was seeing:

```
gap (logo → links):       279.0px
gap (links → controls):   255.4px   → 23.6px less
```

Both side wrappers were `flex-1`, which gives them equal *widths* and therefore puts the nav at the
screen centre — but the right cluster (avatar + controls, 144.4px) is 23.6px wider than the logo
cluster (120.8px), so the equal-width gutters leave unequal gaps. The screen centre also fell in the
**gap** between "Documentation" and "API Reference": no link sat on the centre line, and the middle
link was 31.9px to its right.

## Decision

**"Centred" here means centred between its neighbours, not centred on the screen.** Chosen by the
owner from four measured interpretations (the others were: put the middle link on the centre line,
drop the 1280px cap so the header goes full-bleed, or re-examine the measurement). The consequence is
deliberate and worth stating: the link group now sits **11.8px left of the viewport centre**, because
that is what equal gaps cost when the right cluster is wider than the left one. This is recorded
because it reads like a defect to anyone who measures the group against the screen centre — which is
exactly what the original report did.

## The change

Three classes in `frontend/src/components/astro/PublicNavbar.astro`:

- the row gains `justify-between`;
- the left wrapper loses its `flex-1`;
- the right wrapper loses its `flex-1` and its now-inert `justify-end`.

`justify-content: space-between` flushes the first item to the start and the last to the end and
distributes the remaining space **equally between** consecutive items, so with three items the two
gaps are equal by construction rather than by arithmetic that happens to work out.

**What that guarantee depends on, and what would break it.** The equality holds only while no
main-axis child has an `margin: auto` and while no child grows. Neither is true today: the row has
no `gap-*`, no child carries an auto margin, and after removing both `flex-1`s no child has
`flex-grow`. Put `flex-1` back on either wrapper and the free space is consumed before `space-between`
ever sees it — the gaps stop being equal and the group drifts back to the screen centre, which is the
state this slice exists to leave. **The absence of `flex-grow` is the point, not an oversight.**

A second assumption worth naming: the design requires exactly three children in the row (logo, nav,
controls) for the nav to be the item that is centred between its neighbours. A fourth row child would
leave no single element playing that role.

## Non-goals

- No change to the footer. Its Resources column measured 259px right of centre because the footer is a
  `justify-between` block whose columns have unequal widths — a `space-between` block equalises the
  gaps *between* columns, not their positions, so no column lands on the container centre. Note that
  the column count is session-dependent: signed in there are four and `Brand` carries
  `md:order-first`, which puts Resources third; signed out there are three and Resources is the middle
  column while still off centre, because `Brand` is capped at `max-w-[313px]` and its neighbours differ
  in width. The owner's decision was about the header. Its own slice if wanted.
- No change to the `max-w-7xl` cap, to the vertical alignment, or to the mobile layout.
- No test. There is no harness for `.astro` templates, and the claim is a CSS mechanism verified by
  measurement at ten widths. Asserting layout in a unit test would pin Tailwind classes.
- No ODD task checklist: this is one bounded step, so the work stays small.

## Verification

- `cd frontend && npx tsc --noEmit`
- `cd frontend && pnpm test`
- `cd frontend && pnpm build`
- Measured in the live page at 1024, 1080, 1152, 1280, 1366, 1440, 1536, 1728, 1920 and 2560px.

## Evidence

Suite `Test Files 44 passed` / `Tests 505 passed`, `npx tsc --noEmit` exit 0, `pnpm build`
`[build] Complete!`.

Measured after the change, at all ten widths:

| Width | gap left | gap right | Group offset from screen centre | Logo / controls distance from their edge |
|---|---|---|---|---|
| 1024 | 139.2 | 139.2 | −11.8 | 80 / 80 |
| 1280 | 267.2 | 267.2 | −11.8 | 80 / 80 |
| 1440 | 267.2 | 267.2 | −11.8 | 160 / 160 |
| 1920 | 267.2 | 267.2 | −11.8 | 400 / 400 |
| 2560 | 267.2 | 267.2 | −11.8 | 720 / 720 |

Every vertical control still centres at −0.5px from the header's centre line, so the alignment work
from the first slice is intact.

An A/B on the live DOM, restoring the previous classes without touching the working tree, closed the
one claim that was otherwise only argued. At 390px and 768px — widths where the nav is hidden — the
logo's distance from the left edge and the controls' distance from the right edge are identical in
both layouts (16/16 and 32/32), so the header below `lg` is unchanged. The same A/B at 1024px and
1440px reproduced the pre-change gaps of 151/127.4 and 279/255.4 with a 0px offset, matching the
measurements this slice started from.

## Findings and dispositions

**F1 — The `space-between` guarantee was stated unconditionally, and it is not. Corrected in the
Decision section above.** An independent verification confirmed the mechanism against the Flexbox
specification and the generated CSS, and then named the two preconditions the doc had left implicit:
no auto margins on a main-axis child, and no growing child. Both hold here, so the claim is true as
written *for this markup* — but the doc also claimed robustness to either cluster changing width,
which is only true because the `flex-grow`s were removed. Re-adding `flex-1` to a wrapper silently
undoes the fix, so the reason its absence matters is now written down rather than left to look like a
style choice.

**F2 — The footer's characterisation was loose. Corrected in Non-goals above.** This record said the
Resources column is off centre "by design" over "four columns". Neither is precise: the footer was
laid out edge-to-edge, not designed around centring one column, and the count is session-dependent
(four signed in with `Brand` reordered first, three signed out, where Resources is the middle column
and still off centre). The verifier also noted the ordering fragility that follows from F1's second
assumption: the row must keep exactly three children.

**F3 — Everything else re-verified.** The three commands reproduced the 44/505 baseline with a clean
`tsc` and a complete build; the scope was exactly one modified file and one untracked doc; both
`flex-1` removals were confirmed from source with the left wrapper's `flex` intact, which is what the
earlier baseline fix depends on; the removed `justify-end` was confirmed inert on a content-sized
container; `data-public-nav`, the `--public-nav-h` script and its `publicNavBound` guard, the
`data-nav="public"` active-link contract and the island props were all confirmed untouched; and the
`11.8px` offset was re-derived independently as `(W_left − W_right) / 2` with the correct sign.

**F4 — The mobile layout: measured, then corrected from an argument.** Below `lg` the nav is
`display: none`, leaving two children, where `space-between` anchors first-to-start and last-to-end
exactly as the previous two-halves layout did — that is a class-level argument, and on its own it is
not evidence. It was then checked directly in the page by restoring the old classes on the live DOM
(removing `justify-between`, adding `flex-1` back to both wrappers) and comparing: at a 390px viewport
the logo sits at 16px from the left edge and the controls end 16px from the right, **identically in
both layouts**, and the same holds at 768px (32/32). Below `lg` the header is therefore provably
unchanged, not merely expected to be. The same live A/B at 1024 and 1440 reproduced the old state
exactly — gaps of 151/127.4 and 279/255.4 with a 0px offset — which independently confirms the
diagnosis this slice started from, and demonstrates F1's caveat rather than asserting it: restoring
`flex-1` does return the unequal gaps.
