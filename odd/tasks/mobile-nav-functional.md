# ODD Feature: mobile-nav-functional

> **Status**: done — three work-unit commits on `feat/mobile-nav-functional` (`6b3e87e` session-built
> links, `940e494` the sheet's groups/targets/top edge, plus `docs(odd)` carrying this record).
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/mobile-nav-functional`, stacked on `feat/public-nav-profile-menu` (which holds
> the desktop menu, the mobile identity block and the navbar alignment fix). Nothing is pushed, so
> the two branches are reviewable as a chained pair.
> **Receipt-driven development**: off in this clone.

## Problem

The public mobile sheet was shipped in the previous slice with the identity block and sign-out, and
a browser pass found it structurally wrong in four ways. All four were measured live, not inferred.

1. **"Dashboard" is offered up to three times to the same signed-in visitor on the landing page**:
   the hero CTA (`pages/[locale]/index.astro:71-74`), the first row of the sheet's Product group, and
   the sheet's footer CTA. Two of those are one tap apart in the same panel.
2. **The group separators are anonymous.** `MobileNav.tsx` renders three `<hr>` elements — one
   opening each group — while the `<p>` that carries the category name sits inside a `{/* … */}`
   comment. The sheet therefore shows nine links split by three unexplained rules, one of them
   directly under the identity block. This is unfinished code, not a style choice.
3. **The panel does not line up with the header.** `top: '3.75rem'` is 60px; the header measures 69px
   on mobile and 79.5px on desktop, so the panel overlaps the header by 9px and its square top
   corners land inside the header's bottom border rather than under it.
4. **Touch targets are undersized.** Rows are 36px tall with `text-xs` (12px). Apple's minimum is
   44px and Material's is 48dp; the landing page's own body text is larger than this navigation.

Plus one functional dead end: for a **signed-out** visitor the sheet advertises Dashboard, User
Stories and Kanban Board, and `PROTECTED_PATHS` in `i18n/utils.ts:43` bounces all three to
`/login?redirect=…`. The anonymous sheet sells three routes it cannot open.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Scope | "Functional reorganisation", chosen by the owner over both a cosmetic-only pass and a full-height drawer redesign. The floating panel stays; the content, the labels, the alignment and the touch targets change. |
| D2 | The duplicate "Dashboard" | The footer CTA keeps it and the Product group **loses** it. The CTA is the primary action; a navigation list that repeats the primary action one row above it is the redundancy. Product becomes Stories + Kanban. |
| D3 | The anonymous Product group | **Not rendered at all** when signed out. Those three routes are behind the auth guard, so listing them is a funnel that bounces; the single CTA points at `/login` with `t.landing.cta.button` and carries that job. `PublicLayout` already knows `isLoggedIn`, so it builds the link set, and `MobileNav` stays a dumb renderer. |
| D4 | Group labels | Rendered, replacing the per-group `<hr>`. One rule below the identity block and the footer's own top border are the only separators left. |
| D5 | Touch targets | Rows become 44px (`h-11`) with `text-sm`, matching the minimum and the rest of the page's type scale. |
| D6 | The identity block | Becomes a link to `/{locale}/account` with a hover state and a trailing chevron, so the block that shows who you are is also how you manage it. `t.nav.account` supplies the accessible name. |
| D7 | The panel's top edge | The sheet is portaled to `<body>`, so it cannot be anchored with `top-full`. The navbar publishes its own height as `--public-nav-h` and `MobileNav` reads `top: 'var(--public-nav-h, 4.25rem)'`, replacing the hardcoded `3.75rem` that went stale at the other breakpoint. |
| D8 | The landing hero CTA | **Not touched**, decided by the owner. It is a marketing block, not navigation. |

## Non-goals

- No full-height drawer, no per-row icons, no drop of the sheet's "Storico" title: those were the
  rejected third option.
- No change to the desktop dropdown, its trigger, or its contents.
- No i18n additions: `t.footer.product/resources/company`, `t.nav.account`, `t.nav.dashboard` and
  `t.nav.logout` already exist in both locales and cover every string this slice adds.
- No change to `frontend/src/components/ui/sheet.tsx`. It is a shared primitive; the panel's geometry
  is the caller's business.
- No change to `PROTECTED_PATHS` or the auth guard.

## Tasks

- [x] T1 — `PublicLayout.astro`: build `mobileNavLinks` from the session (Product only when signed
      in, without Dashboard).
- [x] T2 — `MobileNav.tsx`: visible group labels replacing the per-group rules, 44px `text-sm` rows,
      the identity block as an `/account` link with a hover state and a chevron.
- [x] T3 — `MobileNav.tsx`: one separator below the identity block, a top-bordered footer, and the
      CTA plus sign-out beneath it.
- [x] T4 — `PublicNavbar.astro`: publish the header height as `--public-nav-h`; `MobileNav` consumes
      it for the panel's top edge, with the hardcoded value gone.
- [x] T5 — `MobileNav.test.tsx`: the contract this slice exists to protect.
- [x] T6 — Frontend suite, typecheck, build, and a live browser pass at 390px in both session
      states.

## Verification

Run from `/Users/alvaldes/Developer/storico`, observed on the final tree:

- `cd frontend && npx vitest run src/components/react/__tests__/MobileNav.test.tsx` → 1 file, 4 tests
  pass.
- `cd frontend && pnpm test` → `Test Files 44 passed`, `Tests 504 passed` (baseline 43/500).
- `cd frontend && npx tsc --noEmit` → exit 0.
- `cd frontend && pnpm build` → `[build] Complete!`, exit 0.

One independent verification re-ran all four and reproduced them. It also decoded the
`astro-island` props of the anonymous response and found the Product links absent, which is the
strongest available evidence for T1: that rule lives in an `.astro` template with no unit harness.

### Live pass, measured in a real browser

Signed in, at a 390px-wide panel:

| Signal | Before | After |
|---|---|---|
| `Dashboard` occurrences in the panel | 2 | **1** (the CTA) |
| Group labels rendered | 0, plus 3 orphan `<hr>` | **3** (Product / Resources / Company) |
| Row height | 36px, 12px text | **44px**, `text-sm` |
| Panel top vs header bottom | overlapped by 9px | **flush** (69 vs 68.7) |
| Avatar left edge vs label/row text | 146 vs 158 | **158 / 158 / 158** |
| Product rows | Dashboard, Stories, Kanban | Stories, Kanban |

Anonymous, obtained for real by fetching `127.0.0.1:4321`, which does not carry the `localhost`
session cookie: no Product group, no identity block, no sign-out, and a single 44px `Get Started`
CTA pointing at `/en/login`.

## Findings and dispositions

**F-a — The identity block did not align with the navigation. Fixed.** `px-4` on a full-bleed
element put the avatar at x=146 while the group labels and the row text sat at x=158. The nav rows
get their 28px offset from `nav.px-4` plus `px-3` on each row; the identity link now uses `mx-4 px-3`
for the same 28px, which also makes its hover rectangle inset like the rows instead of touching the
panel edges. Measured after: 158/158/158.

**F-b — A stacking listener. Fixed.** The writer guarded the `resize` registration with a
`documentElement.dataset` flag but registered `astro:after-swap` unconditionally, and a view
transition re-runs the module, so the sheet's script added one more listener per navigation. Both
registrations now sit behind a single `publicNavBound` guard. The verification checked the case that
matters and that nobody had established: if Astro re-executes the module the top-level call
re-measures, and if Astro caches it the once-registered `document` listener survives the swap, since
`document` outlives the swap. Neither path goes stale.

**F-c — `PublicFooter.astro` still advertises protected routes to anonymous visitors. Escalated, not
fixed here.** Fetching the anonymous landing page returns exactly three links to authenticated
routes — `/dashboard`, `/stories`, `/kanban` — and all three come from `PublicFooter.astro`, whose
Product column is unconditional. This is the same defect class D3 removes from the sheet, on a
different surface that this slice does not own, and it affects every public page rather than one
panel. It needs its own decision and its own slice.

**F-d — The signed-out test is partly circular. Accepted, with the gap covered by other evidence.**
`signedOutLinks` is filtered inside the test file, so `queryByText(t.footer.product)` proves only that
`MobileNav` does not invent a label when handed no Product links; it never exercises
`PublicLayout.astro`. The claim it appears to make is instead carried by the decoded island props on
the anonymous response, which show the Product links absent from the payload the layout actually
produced. Two of the four tests — the locale-prefixed hrefs and the signed-out gating — would pass
without this slice; the identity-block test is the one that fails against the previous code.

**F-e — Asymmetric spacing around the separator. Accepted.** `SheetContent` is `flex flex-col gap-4`,
so the gap between the identity text and the first group label (`~12+16+1+16+12 = 57px`) is roughly
twice the gap between groups (`~24px`). Visible, deliberate-ish, purely cosmetic, and the separator
delimits a region the footer's border does not.

**F-f — The height is measured before web fonts settle. Accepted.** `--public-nav-h` is set on first
paint and re-read on resize and after a swap, so a late font-induced change with no resize would not
be caught. The header's height comes from its 36px control row rather than from text, so a font swap
cannot move it; the fallback (`4.25rem` = 68px against a measured 69px header) is overwritten on
first paint anyway.

**F-g — `langToggleHref` is a dead prop in `MobileNav.tsx`. Accepted, pre-existing.** Declared and
destructured, never read. Same shape as the dead `isLoggedIn` in `PublicNavbar.astro` recorded in the
first slice's record; both are pre-existing and neither is worth a drive-by change across two files.

## Evidence

Nothing pushed and no tag created. The commits are local to `feat/mobile-nav-functional`, which is
stacked on `feat/public-nav-profile-menu`; the two branches are reviewable as a chained pair.
`make bump` was not run, and it remains the owner's call.

One process note worth keeping: `npx astro build` run from the repository root instead of
`frontend/` fails with `UNRESOLVED_ENTRY` and litters the root with `.astro/` and
`node_modules/.astro/`. Both were removed; the build only works from `frontend/`.
