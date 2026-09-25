# ODD Feature: mobile-sheet-overflow

> **Status**: done — `d6e2a40 fix(nav)` plus `docs(odd)` carrying this record, on
> `fix/mobile-sheet-overflow`, stacked on `fix/public-footer-auth-links`, which is stacked
> on `feat/mobile-nav-functional`, which is stacked on `feat/public-nav-profile-menu`. Nothing
> pushed; the four branches are reviewable as a chained set.
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.

## Problem

Reported by the owner after using the shipped sheet on a phone, and reproduced in a real browser.
Two defects, and the first is worse than "there is a lot of content".

**1. The panel's footer is unreachable on most phones.** The panel is `top: var(--public-nav-h)`,
`bottom: auto`, `height: auto`, and its content sizes to a **constant 780.8px** regardless of the
viewport. It has `overflow-y: visible` and no internal scroll, so when the viewport is shorter than
that, everything past the bottom edge is simply gone:

| Viewport | Panel | Available below the header | Cut off | CTA visible | Sign out visible |
|---|---|---|---|---|---|
| 414×896 | 780.8 | 827 | −46.2 | yes | yes |
| 390×844 | 780.8 | 775 | **+5.8** | on the edge | on the edge |
| 375×667 | 780.8 | 598 | **+182.8** | **no** | **no** |
| 360×640 | 780.8 | 571 | **+209.8** | **no** | **no** |

375×667 is an iPhone SE, so on an ordinary phone a signed-in visitor cannot reach Dashboard or Sign
out at all. This is not a density problem; it is a reachability defect.

**2. The group headings and the options are the same colour.** Measured computed styles: the label is
`10px / 600 / uppercase` and the row is `14px / 400`, and both are
`oklch(0.63 0.01 260)`. The only differentiators are size, weight and case, and the option is
*larger* than its heading, so the heading reads as fine print above the real content. The repository
already answers this question one surface over: `ui/sidebar.tsx`'s `SidebarGroupLabel` is
`text-sidebar-foreground/70`, and `SidebarMenuButton` items run at full foreground. The sheet
diverged from the pattern the dashboard already established.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Reachability | The panel gets `max-h-[calc(100dvh-var(--public-nav-h))]` and the `<nav>` becomes the scroll region (`min-h-0 overflow-y-auto`), with the header and footer pinned. The panel can then never be taller than the space below the header. |
| D2 | Why `shrink` and not `flex-1` | `flex-1` is `flex: 1 1 0%`. In an auto-height flex container the item's hypothetical main size becomes 0, so the nav would collapse instead of sizing to its content. Shrink-only (`flex-shrink: 1`, the default) with `min-h-0` shrinks the nav only when the max-height is reached, and leaves it content-sized otherwise. Header and footer get `shrink-0`. |
| D3 | Group hierarchy | Rows move to full contrast (`text-foreground`), matching `SidebarMenuButton`. Labels stay small, uppercase, tracked and muted. Grey small caps = heading; full-contrast = clickable. |
| D4 | The redundant header title | The visible "Storico" title is replaced by the identity row: `[avatar] Name / email  ✕`. It duplicated the logo visible directly behind the panel and cost ~60px. When signed out there is no identity, so the visible title stays; either way one `SheetTitle` remains for the panel's accessible name (visually hidden when the identity row is shown). |
| D5 | The two short groups | Product renders full width; Resources and Company share a two-column grid, saving three rows (~132px). Approved by the owner as the way to make an iPhone SE fit without scrolling. |
| D6 | Row type in the grid | Measured with the project's real font at a 375px viewport: the panel is 281.3px, so a two-column grid with an 8px gap leaves 120.6px per column. "Documentation" measures 100.6px at 14px and 93.4px at 13px; with `px-2` the text room is 104.6px. At 14px that is 4px of margin and it already fails at a 360px viewport, so grid rows use `text-[13px] px-2`. |
| D7 | Narrow-screen degradation | The grid is `grid-cols-1 min-[360px]:grid-cols-2`, so below 360px the groups stack instead of squeezing. With D1 the stacked result scrolls rather than overflowing. |

## Non-goals

- No change to `PublicLayout.astro` or `PublicNavbar.astro`, and no change to the `MobileNavLink`
  contract: the flat link list with a `category` already carries everything needed to render the
  grid, and the layout rule is a rendering concern.
- No change to `ui/sheet.tsx`. The geometry stays the caller's business, as in the previous slice.
- No change to the desktop dropdown, the footer, or the auth guard.
- No new i18n keys: every label already exists in both locales.
- No test for the grid or the max-height. They are layout, and asserting Tailwind classes would pin
  the implementation rather than the behaviour. They are verified by measurement in the live page
  instead, in both locales and at several viewport sizes.

## Tasks

- [x] T1 — `MobileNav.tsx`: cap the panel's height and make the nav the scroll region.
- [x] T2 — `MobileNav.tsx`: merge the identity block into the header row, keep one `SheetTitle` for
      the accessible name, drop the now-redundant `Separator` and give the header a bottom border.
- [x] T3 — `MobileNav.tsx`: full-contrast rows, and the two-column grid for the short groups with the
      narrow-screen fallback.
- [x] T4 — `MobileNav.test.tsx`: keep the four existing contracts and add the accessible-name one.
- [x] T5 — Suite, typecheck, build, and a measured live pass at 375×667, 360×640, 390×844 and
      414×896, in both locales and both session states.

## Verification

- `cd frontend && npx vitest run src/components/react/__tests__/MobileNav.test.tsx` → 1 file, 5 tests
  pass.
- `cd frontend && pnpm test` → `Test Files 44 passed`, `Tests 505 passed` (baseline 504 + the new
  accessible-name test).
- `cd frontend && npx tsc --noEmit` → exit 0.
- `cd frontend && pnpm build` → `[build] Complete!`, exit 0.

### The live pass, measured in a real browser

Signed in, in both locales. The panel is now a constant **528.6px**, down from 780.8px:

| Viewport | Panel | Available below the header | Slack | CTA | Sign out |
|---|---|---|---|---|---|
| 375×667 (iPhone SE) | 528.6 | 598 | **+69.4** | visible | visible |
| 360×640 | 528.6 | 571 | +42.4 | visible | visible |
| 390×844 | 528.6 | 775 | +246.4 | visible | visible |
| 414×896 | 528.6 | 827 | +298.4 | visible | visible |

Every viewport that previously hid the footer now fits it with room to spare, and no row is clipped
anywhere. The `en` and `es` locales agree: the widest label inside a grid column is
`Documentation` at 100.6px and `Documentación` at 96.6px against 105px of text room at a 360px
viewport, leaving 4.4px and 8.4px of slack. `Product` renders full width and only `Resources` and
`Company` share the grid, at `120.625px 120.625px`. The nav reports `scrollHeight === clientHeight`
at every size, so the scroll region is the safety net rather than the everyday path, which is the
intended shape.

The hierarchy fix is measurable, not asserted: the resting row is `oklch(0.93 0.01 260)` and the
label stays `oklch(0.63 0.01 260)`.

Anonymous, obtained from `127.0.0.1:4321`, which carries no session cookie: the panel is 330.3px,
the header falls back to the visible brand title, there is no identity row and no avatar, `Resources`
and `Company` share the grid at `120.625px 120.625px` because there are only two groups, six rows,
and the single CTA points at `/en/login`.

## Findings and dispositions

**F1 — The panel's height cap could vanish silently. Fixed.** The panel's `top` used
`var(--public-nav-h, 4.25rem)` while the new `max-h` class used `var(--public-nav-h)` with no
fallback. Measured both ways in the live page: with the variable the computed `max-height` was
`598px`; with the variable removed it was **`none`**. An unset variable therefore dropped the cap
and restored the original unreachable-footer defect with no error and no visible symptom at this
content size — the panel still measured 528.6px because the content happens to fit, so nothing would
have looked wrong until the link list grew. The class now carries the same `4.25rem` fallback as the
`top`, verified the same way: `599px` with the variable removed. One line, one file.

**F2 — The identity row's tap target shrank. Accepted.** Merging it into the header took the account
link from ~60px to 44px (6px of padding around a 32px avatar). That still meets Apple's 44pt minimum
and is under Material's 48dp guidance, in exchange for the ~52px this merge saves. The close button
keeps its own target beside it.

**F3 — `whitespace-nowrap` with visible overflow. Accepted, with the margin measured.** A future
label longer than its column would overflow into the gap rather than wrap or ellipsise, because the
row has no `overflow-hidden`. Today's widest leaves 4.4px at a 360px viewport, which is thin. Left as
it is because truncating a navigation label is worse than a hypothetical overflow, and the measured
slack is recorded here so the next added label can be checked against it.

**F4 — The grid rule and the cap have no unit test. Accepted by design.** Both are layout. Asserting
Tailwind classes would pin the implementation rather than the behaviour, and the test that does exist
(the accessible name in both session states) covers the part of this change that is a real contract.
The layout claims rest on the measurements above.

**F5 — The header's padding override works by stylesheet order, not by merge removal. Corrected.**
This slice's delegation and the parent's report both claimed that `tailwind-merge` drops the base
`p-4` from `SheetHeader` when `px-3 py-2` is passed, leaving the latter as the only padding. The
verifier read `tailwind-merge@3.7.0`'s `conflictingClassGroups` and established that `px` and `py` do
**not** list `p`, so a later `px-3` does not remove an earlier `p-4`: both survive into the class
attribute. The effective padding is still `px-3 py-2`, because Tailwind emits the shorthand `.p-4`
before the longhands `.px-3` and `.py-2` in the generated stylesheet and a longhand beats a shorthand
at equal specificity. The measured 65px header is consistent with that outcome and inconsistent with
`p-4`. No code change: the failure mode if Tailwind's emission order ever changed is a header 16px
taller, cosmetic, and the ordering is deterministic by design. Recorded so the next reader does not
repeat the wrong explanation — and so nobody "cleans up" the class list on the strength of it.
`gap-2` winning over `gap-0.5` *is* a genuine merge removal, and that half of the claim stands.

**F6 — `pb-3 last:pb-0` is asymmetric across the grid boundary. Accepted.** The lead group is never
`:last-child` of `<nav>` (the grid wrapper follows it), so it always keeps its `pb-3`, while inside
the grid only the final item reaches `pb-0`. The difference is one 12px bottom padding, and the
footer's own `border-t` dominates the boundary. Cosmetic.

**F7 — A single-category input would render one half-width grid column. Unreachable, noted.** With
one group the wrapper's `min-[360px]:grid-cols-2` would leave the lone group in the left half.
`PublicLayout.astro` always supplies two or three categories and `PublicNavbar`'s
`mobileNavLinks ?? navLinks` fallback is never taken, so no live path reaches it. Left alone rather
than guarded, because a guard for an unreachable state is its own kind of debt.

## Evidence

Nothing pushed and no tag created. The commits are local to `fix/mobile-sheet-overflow`, the head of a
four-branch chain; `make bump` was not run.

One caveat worth carrying forward: this pass measured text width and clipping in the page's real font
at four viewports and two locales, but it did not run on a physical device. Rendered `Inter` on a real
phone is the same font the page loads, so the risk is low, but nobody has held this in their hand.
