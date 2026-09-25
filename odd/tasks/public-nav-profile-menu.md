# ODD Feature: public-nav-profile-menu

> **Status**: done — five work-unit commits on `feat/public-nav-profile-menu` (`c03e0ee` desktop
> menu, `9373ba7` mobile sheet, `9178e5e` initials, `fix(nav)` vertical centring, plus `docs(odd)`
> carrying this record). Nothing
> pushed. Receipt-driven development is **off** in this clone, so no native review ran; two
> independent verifications did, both recorded below with their findings and dispositions.
>
> The commits are path-disjoint slices of one verified tree. They were not each built in isolation;
> the only cross-slice dependencies are the helper and the `PublicNavUser` type that the first
> commit introduces, and every later slice imports both from it.
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/public-nav-profile-menu`, branched from `main` at `f3476cb`.

## Problem

The public navbar (`frontend/src/components/astro/PublicNavbar.astro`) renders one CTA on the
right. `PublicLayout.astro:55` flips that CTA to **"Dashboard" → `/{locale}/dashboard`** as soon as a
session exists, so a signed-in visitor landing on `/en/` or `/es/` sees a bare link where their
identity should be. There is no avatar, no name, no account shortcut and no sign-out anywhere in
the public surface: the only user menu in the product lives inside the dashboard sidebar
(`frontend/src/components/nav-user.tsx`) and is unreachable from the landing page, which is exactly
where a signed-in visitor arrives.

A second, structural problem: `getSession()` was already called in `PublicLayout`, but only the
**boolean** `isLoggedIn` crossed into the islands. The serialized user never reached the navbar, so
no public component could render identity at all.

`nav-user.tsx` is not reusable as-is: it depends on the shadcn `Sidebar` context (`useSidebar`,
`SidebarMenu`, `SidebarMenuButton`), which does not exist outside `DashboardShell`.

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Design reference | The shadcn **Base UI** avatar-dropdown example (`https://ui.shadcn.com/docs/components/base/avatar`, "Dropdown" section): `DropdownMenuTrigger render={<Button variant="ghost" size="icon" className="rounded-full" />}` wrapping an `<Avatar>`. Avatar-only trigger, no name, no chevron. |
| D2 | Trigger scope | Desktop-only (`lg+`). On smaller viewports the hamburger sheet owns identity, so the navbar does not get a fifth control crowding the lang/theme/GitHub trio. |
| D3 | Replaces or coexists | The avatar menu **replaces** the logged-in "Dashboard" CTA. Dashboard stays one click away in the menu's first item. The anonymous CTA (`t.landing.cta.button` → `/login`) is untouched. |
| D4 | Menu contents | Header block (avatar + name + email) + `Dashboard`, `Account` (`/{locale}/account`), `Projects` (`/{locale}/projects`), separator, `Log out` (`variant="destructive"`). No theme or language items: the navbar already exposes both as standalone controls, so duplicating them would be two sources of truth for one action. |
| D5 | Mobile | The sheet gets an identity block above the nav groups (avatar + name + email) and **keeps** the existing Dashboard CTA at the foot, with `Log out` added below it. Chosen by the owner over replacing the CTA. |
| D6 | User data transport | A plain serializable object (`{ name, email, avatarUrl }`) from `PublicLayout` → `PublicNavbar` → islands. Not `userJson`, not `authStore`: the public nav needs three display fields, and `DashboardShell`'s store hydration exists for the dashboard's API-driven profile fetch (`fetchFullUserProfile`), which the public nav should not trigger on every landing-page view. |
| D7 | Avatar source | `session.user.image` (Auth.js standard) normalised to `avatarUrl` in `PublicLayout`. `avatar_url` is the backend's field name and is absent from the session object. |
| D8 | Sign-out | `signOut({ callbackUrl: \`/${locale}/login\` })` from `auth-astro/client`, the same call `nav-user.tsx:54` already makes. No confirmation dialog: that would be a new product decision, not part of this slice. |
| D9 | Width override | `ui/dropdown-menu.tsx`'s `DropdownMenuContent` applies `w-(--anchor-width) min-w-32` to the Base UI popup. Against a 32 px icon trigger that collapses the menu, so the content sets `min-w-64` — a `min-width` beats the anchor `width` regardless of merge order. |

## Non-goals

- No changes to the bottom CTA section of `PublicLayout` (`showCta`), which keeps saying "Dashboard"
  for a signed-in user. It is a marketing block, not navigation.
- No extraction of a shared user menu out of `nav-user.tsx`: the two menus differ in trigger,
  placement and contents, and the shared surface would be thinner than the coupling it adds.
- No session-fetching change in `PublicLayout`: `getSession()` is already called and reused.
- No `settings` item in the menu: there is no public `/settings` route.
- No unit tests for the `.astro` templates: there is no harness for them in this repo, and the logic
  they add is prop plumbing. Their signed-out behaviour was established by source reading instead.
- No dependency changes.

## Tasks

- [x] T1 — `PublicUserMenu` island: avatar-only Base UI dropdown, identity header, three navigation
      items, destructive sign-out.
- [x] T2 — `nav.open_user_menu` in `en.json` and `es.json`.
- [x] T3 — Thread the serialized session user through `PublicLayout` → `PublicNavbar`, rendering the
      island on desktop for signed-in users and keeping the anonymous CTA.
- [x] T4 — Mobile sheet identity block and sign-out, keeping the Dashboard CTA.
- [x] T5 — Behaviour tests for `PublicUserMenu`.
- [x] T6 — Frontend suite, typecheck and build, verified twice by an independent verifier.
- [x] T7 — Fix round: code-point-safe `getInitials` shared by four call sites, plus a comment
      placement nit (see Findings).

## Verification

Run from `/Users/alvaldes/Developer/storico`, observed on the final tree:

- `cd frontend && npx vitest run src/lib/__tests__/initials.test.ts src/components/react/__tests__/PublicUserMenu.test.tsx`
  → `Test Files 2 passed`, `Tests 16 passed` (9 helper + 7 component).
- `cd frontend && pnpm test` → `Test Files 43 passed`, `Tests 500 passed` (baseline 42/490).
- `cd frontend && npx tsc --noEmit` → exit 0, no output.
- `cd frontend && pnpm build` → `[build] Complete!`, exit 0. The only two warnings come from
  `node_modules/.pnpm/zod@4.6.4/` (Rollup comment-position notices); no diff file is referenced.

Two independent verifications (neither by the writer) re-ran all four commands and reproduced the
numbers. Not observed, by anyone: real browser rendering, the live OAuth session flow, and the
menu's actual pixel width — the E2E suite is not executable in this repository. The width behaviour
of D9 rests on CSS reasoning and a passing render, not on a layout assertion.

## Findings and dispositions

**F1 — Astral-character initials. Fixed (T7).** `getInitials` built initials with `charAt(0)`,
which indexes a UTF-16 unit; for an astral character that splits a surrogate pair and renders as the
replacement glyph (`'😀 Smith'` → `'\ud83dS'` → `�S`). The same class existed in `nav-user.tsx` and
`UserAvatar.tsx` before this slice. Rather than patch one instance, the helper moved to
`frontend/src/lib/initials.ts` and all four call sites now route through it. An exhaustive grep for
remaining string-indexing initial computation (`charAt`, `[0]`, `slice(0, 2)`, `substr`) found no
surviving real instance; the remaining hits capitalise provider or icon-name labels, which is a
different concern.

**F2 — Undeclared behaviour deltas in `nav-user.tsx` and `UserAvatar.tsx`.** The writer reported one
deliberate change; the verifier found **five** input classes that render differently, all of them
improvements on invalid input, and this record states them rather than the reported one:

| Input | `nav-user.tsx` before → after | `UserAvatar.tsx` before → after |
|---|---|---|
| `''` | `'??'` → `'?'` | `'?'` → `'?'` |
| `'   '` | `''` (blank circle) → `'?'` | `' '` → `'?'` |
| `'\tAda'` | `'\t'` → `'A'` | `'\t'` → `'A'` |
| `'Ada\tLovelace'`, `'Ada\nLovelace'`, `'Ada\u00a0Lovelace'` | `'A'` → `'AL'` | (single initial, unchanged) |
| `'😀 Smith'`, `'😀'` | lone surrogate → `'😀S'`, `'😀'` | lone surrogate → `'😀'` |

Leading/trailing **spaces** and multi-space runs are equivalent in both files, and every other
non-astral input renders identically. The old code split on a literal `' '` while the helper splits
on `\s+`, which is what makes tabs, newlines and NBSP word separators now work.

**F3 — `max = 0` contradicts the doc comment. Accepted.** `getInitials(name, 0)` returns `''`, not
`'?'`. Unreachable: `UserAvatar` passes `1` and every other caller uses the default `2`. Left as-is
rather than adding an unreachable branch.

**F4 — Trailing comment placement. Fixed (T7).** A comment introduced with the feature sat *after*
the expression it described. Moved above it.

**F5 — Misleading test name. Fixed inline by the orchestrator.** A helper test was named for
"non-BMP-adjacent CJK characters"; `李` is U+674E, i.e. BMP, so that case passes an indexing
implementation and does not discriminate the fix. Renamed and annotated with what it actually pins,
after the verifier independently confirmed the correction.

**F6 — `isLoggedIn` is a dead prop in `PublicNavbar.astro`. Accepted, pre-existing.** Declared and
destructured, never used in the body — and it was already dead at `f3476cb`, before this slice
(`git show HEAD:...PublicNavbar.astro | grep -c isLoggedIn` = 2, both in the declaration lines).
`tsc` is silent because Astro's strict tsconfig does not enable `noUnusedLocals`. Removing it is a
drive-by cleanup across two files and is left out of this slice.

**F7 — Wasted hydration. Accepted.** The desktop island sits in `display: none` below `lg` and
hydrates anyway. No clean fix exists: SSR has no viewport, and `client:visible` would never fire
inside a hidden element.

**F8 — Empty `src` on the avatar. Not a defect.** `AvatarImage` receives `src={user.avatarUrl ?? ''}`.
Base UI short-circuits in `useImageLoadingStatus` on `!src && !srcSet`, so no request is issued and
`AvatarFallback` renders. This matches the pre-existing `nav-user.tsx` pattern.

**F9 — The navbar's vertical alignment. Fixed after the first review.** Measured in a real browser,
not inferred: every control in the row centred at `delta −0.5px` from the header's centre line
except two, which sat at `−3.8px` — the avatar trigger introduced by this slice, and the logo, which
predated it. One cause for both: a `display: block` wrapper (`div.hidden.lg:block`, `div.flex-1`)
whose only child is an inline-level element (`inline-flex`). That child gets a line box and rides
the font's text baseline, which lifts it inside a wrapper 6.5px taller than the control it holds.
Every sibling control is a flex item, and flex items are blockified, which is why only these two
drifted. Changing each wrapper to `flex` puts delta at `−0.5px` for all eight controls and drops the
header from 79.5px to 77px. Verified by measuring before and after in the live page, and by
zooming the header at 4x. The ODD prompt for this slice missed it because no automated check looks
at layout; the E2E suite that could have is not executable here.

## Evidence

Nothing pushed and no tag created. The four commits are local to `feat/public-nav-profile-menu`;
`make bump` was not run, and it is the owner's call when this lands.
