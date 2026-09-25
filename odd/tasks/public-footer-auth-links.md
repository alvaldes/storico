# ODD Feature: public-footer-auth-links

> **Status**: done — `79b83fc fix(nav)` plus `docs(odd)` carrying this record, on
> `fix/public-footer-auth-links`, stacked on `feat/mobile-nav-functional`, which is stacked on
> `feat/public-nav-profile-menu`. Nothing pushed; the three branches are reviewable as a chained set.
> **Created**: 2026-09-25
> **Workflow**: Organic Driven Development (ODD)
> **Receipt-driven development**: off in this clone.

## Problem

An independent verifier auditing the mobile sheet's link set found the same defect one surface over
and reported it as out of scope. Reproduced by fetching the anonymous landing page: the response
contained exactly three links to authenticated routes — `/dashboard`, `/stories` and `/kanban` — and
all three came from `frontend/src/components/astro/PublicFooter.astro`, whose Product column has no
session guard at all. `PROTECTED_PATHS` in `i18n/utils.ts:43` lists those three, so the middleware
bounces every one of them to `/{locale}/login?redirect=…`.

It is the same defect class the mobile slice removed from the sheet, and worse in extent: the footer
renders on **every** public page — the landing page, about, privacy, terms, docs, api, status and
the 404 — so a visitor who never signs in meets the dead end on all of them, in both locales. (The
column is hidden below 431px, so small phones do not show it; everything wider does.)

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Fix shape | Gate the Product column on the session, exactly as the mobile sheet's Product group is gated. Chosen by the owner over keeping the links and pointing them at an explicit `/login?redirect=…`, and over recording it as debt. |
| D2 | How the footer learns the session | A required `isLoggedIn: boolean` prop, passed by `PublicLayout`, which already computes it and is the footer's only consumer. Not a second `getSession()` call inside the footer, and not optional-with-default: a silent default is how an anonymous-only regression gets reintroduced. |
| D3 | Scope | The two files that carry the prop and the guard. No new column replaces the hidden one, no copy changes, no new i18n keys. |

## Non-goals

- No change to which footer columns an anonymous visitor sees beyond dropping Product: Resources,
  Company and the brand block are untouched.
- No change to `PROTECTED_PATHS`, the middleware, or the login redirect.
- No new unit test. There is no test harness for `.astro` templates in this repository, and the
  behavioural claim is checked end to end instead: the anonymous response must contain zero links to
  protected routes, on every public page.
- No change to `PublicNavbar`, `MobileNav` or the mobile sheet.

## Tasks

- [ ] T1 — `PublicFooter.astro`: required `isLoggedIn` prop; the Product column renders only when it
      is true.
- [ ] T2 — `PublicLayout.astro`: pass `isLoggedIn` to the footer.
- [ ] T3 — Fetch every public page in both locales as an anonymous visitor and confirm zero links to
      `dashboard`, `stories`, `kanban`, `account` and `export`.
- [ ] T4 — Frontend suite, typecheck and build.

## Verification

- `cd frontend && pnpm test`
- `cd frontend && npx tsc --noEmit`
- `cd frontend && pnpm build`
- `curl -sS http://127.0.0.1:4321/{en,es}/<page>` for the landing page, about, privacy, terms, docs,
  api, status and a non-existent path, grepping for `href="/{locale}/(dashboard|stories|kanban|account|export)"`.

## Evidence

Observed, on the final tree. Suite `Test Files 44 passed` / `Tests 504 passed`; `npx tsc --noEmit`
exit 0; `pnpm build` complete.

An anonymous sweep of every public page in both locales — `/en/`, `/en/about`, `/en/privacy`,
`/en/terms`, `/en/docs`, `/en/api`, `/en/status`, `/en/does-not-exist`, `/es/`, `/es/about` — returns
**zero** links matching `href="/{locale}/(dashboard|stories|kanban|account|export)"`, on both
`localhost` and `127.0.0.1`, including a full-response token scan that would also catch escaped JSON
in island props. The 404 renders the footer and is clean too. The footer's own labels are
`Resources / Company / Storico` in English and `Recursos / Compañía / Storico` in Spanish: no
Product column. One independent verification reproduced all of it and also confirmed that the
`MobileNav` island's decoded props and the desktop navbar's anonymous CTA still carry no guarded
link, so the three branches together leave none reachable.

### Findings and dispositions

**F1 — "byte-identical" was the wrong claim, and the verifier caught it.** This record originally
said the Product block was byte-identical and merely wrapped. It is not: every line was re-indented
by two spaces and the one-line `<!-- Product -->` comment became a two-line why-comment. Rendered
output for `isLoggedIn === true` is the same modulo insignificant whitespace, so the substance
holds, but the word did not. Corrected here rather than left standing. This is the second time in
this chain that a verifier corrected an over-claim of mine, and both times the correction was right.

**F2 — Nothing in this repository type-checks `.astro` props. Accepted, and wider than this slice.**
`tsc --noEmit` cannot parse `.astro` files, `astro build` does not check props, and
`.github/workflows/ci.yml` runs only tsc, vitest and build. `@astrojs/check` is not a dependency and
`astro check` is not in CI. So "the required prop cannot be silently omitted" is enforced by editors
and by an `astro check` nobody runs, not by any gate. Adding it is a repository-wide decision with a
potentially large first-run error surface, and it belongs to its own slice, not to this three-line
fix.

**F3 — The why-comment ships to the client. Nit, not a defect.** Astro emits HTML comments into the
response. It is the same trade-off the navbar's comments already make and it carries no secret.

**F4 — `max-[431px]:hidden` stays. Confirmed deliberate.** It is inert for anonymous visitors now
(the block does not render) and still hides the column on narrow signed-in viewports.

**F5 — The signed-in footer was never observed at runtime by anyone.** No shell here holds a session
cookie, so both `localhost` and `127.0.0.1` are anonymous and no `curl` can reach the authenticated
rendering. It is inferred from the diff plus `PublicLayout` passing `!!session?.user`, and that
inference is sound but it is not an observation. The live signed-in check needs the browser, which
the owner is holding.
