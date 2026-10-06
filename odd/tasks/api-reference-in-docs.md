# ODD Feature: api-reference-in-docs

> **Status**: closed, branch `feat/api-reference-in-docs`, stacked on `feat/docs-header-nav-scope`
> (both unpushed). The stack exists because this change edits `src/lib/public-nav.ts` and
> `src/i18n/__tests__/docs-header-nav.test.ts`, the two files the lower branch rewrote; merged in the
> other order the second one conflicts.
> **Created**: 2026-10-06
> **Workflow**: Organic Driven Development (ODD)
> **Source**: the owner asked to delete `frontend/src/pages/[locale]/api.astro` and point its link at
> `/docs/api-reference`.

## Problem

The app ships its own API reference page at `/en/api` and `/es/api`. Its endpoint list is
hand-written prose, and the reason it needed a guard (`api-docs-copy.test.ts`) was exactly that: it
once advertised a `POST /api/v1/batch` endpoint that has never existed, plus two extraction paths the
API had already left behind.

Meanwhile the same reference now exists **inside the docs**, generated from the FastAPI application
itself (`frontend/src/content/docs/{en,es}/docs/api-reference.md`, already wired into the Starlight
sidebar at `astro.config.mjs:117`) and byte-compared against a fresh render by
`backend/tests/test_api_reference.py:18`, with `:35` asserting every operation in the spec reaches the
page. One of the two references is generated and cannot lie. The other is prose that needed a guard
because it lied once.

So the app-side page is deleted and every link that pointed at it points at the docs page instead.

## The owner's decisions

- **Delete the page**, and repoint its link to `/docs/api-reference`.
- **Delete the 14 `pages.api.*` catalogue keys in both locales** (28 keys). Nothing else reads them,
  and no guard detects an orphaned key, so leaving them would be invisible debt.
- **Redirect the old URLs** rather than let them 404. `/en/api` and `/es/api` are live in production
  today; the match is an exact pathname, never a prefix.

## The one way this change can break production

`/api` is not only the retired page: it is the prefix of this app's own Astro endpoints
(`src/pages/api/health/services.ts`, reached by the status page) and of the proxy to the backend. The
middleware already skips those with `SKIP_PREFIX = ['/api/', …]`, and `/api` without the trailing
slash is not skipped.

A redirect written as a prefix — `/api` matching with `startsWith` — would swallow `/api/health/*`
and the backend proxy, and the status page would break with no error at the redirect level. The match
must be exact `pathname === '/api'` (plus the two locale-prefixed forms), and that is the property the
new guard has to pin, with the real strings rather than a paraphrase.

## Scope

1. **Delete `frontend/src/pages/[locale]/api.astro`.**
2. **Repoint every link** that pointed at `/api`:
   - `src/lib/public-nav.ts` — `PUBLIC_NAV_PATHS`' `/api` entry and its label key;
   - `src/layouts/PublicLayout.astro` — the mobile menu's Resources entry;
   - `src/components/astro/PublicFooter.astro` — the footer's Resources link;
   - `src/components/react/AccountPage.tsx` — the About card's API link.
3. **`src/i18n/utils.ts`** — drop `'/api'` from `PUBLIC_PATHS`. The new redirect fires first, so the
   entry is dead; and the nested docs path is not added, because no nested path is listed there today
   (`/docs/quickstart` is not either).
4. **The redirect**, in a new pure module `src/lib/retired-paths.ts`, called from `src/middleware.ts`.
   Pure and separate on purpose: `middleware.ts` imports `astro:middleware` and `auth-astro/server`,
   which are virtual modules a unit test cannot load, so the decision has to be testable without them.
5. **`src/middleware.test.ts`** (new) — the guard for the decision function.
6. **Delete `src/i18n/__tests__/api-docs-copy.test.ts`.** Its subject is the deleted page and the copy
   that rendered it. The property it protected — "the reference advertises only paths the routers
   declare" — is now held more strongly by `backend/tests/test_api_reference.py`, which re-renders the
   page from the spec and byte-compares it.
7. **Delete `pages.api` from both catalogues.**
8. **`src/i18n/__tests__/docs-header-nav.test.ts`** — the app navbar's pinned list changes with it.
9. **`docs/testing.md`** — row 10 of the manual walkthrough tests the deleted page's endpoint list. It
   becomes the check for the redirect and for the endpoints that must NOT be redirected.
10. **Verify**: the focused tests, the full suite, `tsc`, a build, and a dev-server check that
    `/api/health/services` is not redirected while `/en/api` is.

## Non-goals

| Out of scope | Reason |
| --- | --- |
| Moving the "no batch endpoint" assertion to the backend | It existed because hand-written prose could lie about the API. The generated reference cannot: `test_api_reference.py` re-renders it from the spec and byte-compares, so an endpoint that appeared or vanished fails there. Recorded rather than relocated. |
| A `.vercel.json` redirect | There is no such file, `output` is `'server'`, and the middleware already owns locale-aware redirects. A second mechanism for one URL is a second place to look. |
| Nested locale-less docs paths like `/docs/api-reference` | They do not redirect today either (`/docs/quickstart` does not), and the new redirect always emits a locale. Fixing that is a different change about `PUBLIC_PATHS`, not about this page. |
| The `Storico Docs` label and the brand text | Landed separately in `1091035`; its two known defects are recorded there. |

## Tasks

- [x] 1. **The pure redirect module and its guard**, test-first — `b75f0bc` (RED: the module's import
      could not resolve; GREEN: 13 cases).
- [x] 2. **The middleware calls it**, and `/api` leaves `PUBLIC_PATHS` — `b75f0bc`. The placement is
      load-bearing and moved during verification; see below.
- [x] 3. **The page, the dead test and the dead keys go**, and every link is repointed — `66fd869`.
- [x] 4. **The docs walkthrough row is rewritten** — `b75f0bc`.
- [x] 5. **Verify and close** — this commit.

## Constraints

- **The prefix trap is the thing being guarded.** `retiredPathRedirect('/api/health/services')` must
  be null, and so must `/api/v1/workspaces/x/extract/`. A test that only checks `/en/api` redirects
  would pass while production broke.
- **The redirect emits a locale.** `/api` has none, so it is detected from `Accept-Language` through
  the existing `detectLocale`, the same way `isPublicPagePath` does it. `es-MX` must land on `/es/…`.
- **No link may be left pointing at `/api`.** Grep is the check; the guard in
  `docs-header-nav.test.ts` pins the navbar's list but knows nothing about the footer or the account
  card.
- **404 vs 302.** The existing redirects in this middleware use 302; this one matches them rather
  than introducing a second status code for one URL.

## Evidence log

### Reconnaissance

- The destination already exists and is already linked from the sidebar: `astro.config.mjs:117`
  `link: '/docs/api-reference'`, content at `src/content/docs/{en,es}/docs/api-reference.md`.
- Five link sites, found by grepping for the exact app path (not the `/api/v1/…` API paths, which are
  a different thing entirely): `public-nav.ts:19`, `PublicLayout.astro:65`, `PublicFooter.astro:43`,
  `AccountPage.tsx:273`, and `i18n/utils.ts:41`.
- `src/middleware.ts` has no test today, and the file cannot be imported by one: `astro:middleware`
  and `auth-astro/server` are virtual. Hence the pure module.
- `docs/testing.md:248` (row 10) walks the reader through `/en/api` checking that every listed path
  answers `401` and never `404`.
- `SKIP_PREFIX = ['/api/', '/_astro/', '/favicon']` (`middleware.ts:10`) uses a trailing slash, so
  `/api` itself is not skipped and reaches the page logic — which is why leaving `'/api'` in
  `PUBLIC_PATHS` would send it to the locale redirect instead of the new one.

### The wiring defect that the unit tests could not see

The first implementation placed the redirect after the `SKIP_PREFIX` early return, and every one of
its unit cases was green. A running dev server said otherwise:

```
/api/  404 ->           ← but retiredPathRedirect('/api/') returns a target, and a test asserted it
```

`SKIP_PREFIX` is `['/api/', …]` matched with `startsWith`, so `/api/` **with the trailing slash**
was skipped before the redirect ever ran. The pure rule was right and the wiring was wrong, which is
exactly the difference a test of the pure rule cannot see. The manual walkthrough the brief asked
for would also have been wrong: it claimed `/api/` redirects.

The redirect now runs before the early return. That is safe precisely because the match is exact:
`/api/health/services` and `/api/v1/…` do not match the regex and still fall through to the skip.
The ordering is pinned by a source-level case in `retired-paths.test.ts` — the middleware cannot be
imported, since it pulls two virtual modules — and that case is proven by triangulation:
re-breaking the order makes it fail, restoring it makes it pass, and `middleware.ts` is
byte-identical after the probe (`cmp`).

### Live verification against a dev server

| request | result |
| --- | --- |
| `/api`, `/api/`, `/en/api`, `/en/api/`, `/es/api`, `/es/api/` | `302` → the docs reference in the right locale |
| `/api` with `Accept-Language: es-MX` | `302` → `/es/docs/api-reference` |
| **`/api/health/services`** | **`504`, reached the app's own endpoint, NOT redirected** |
| `/api/v1/tasks/`, `/api/v1/workspaces/x/extract/` | `401` from the backend, NOT redirected |
| `/en/status`, `/en/docs/api-reference`, `/es/docs/api-reference` | `200` |

The `504` on the health endpoint is this machine's condition, not the change's: the endpoint
aggregates services and Ollama is not running (`odd/tasks/dev-reset-0028.md`). What the row proves is
the absence of a `302`. But it is also why `docs/testing.md` was corrected: it promised JSON there,
which this environment cannot deliver, so the step now asserts "anything but a `302`".

Suite **71 files / 806 tests** green (804 before: −11 from the deleted `api-docs-copy.test.ts`, +13
from the new guard), `tsc --noEmit` exit 0, build exit 0, and the build artifacts carry no `/api`
page for either locale — only `docs/` under `dist/client/{en,es}/`, with
`.vercel/output/static/{en,es}/docs/api-reference/index.html` present.

## Limitations carried forward

- **The locale-less nested form still does not redirect.** `/docs/api-reference` without a prefix
  answers 404, exactly as `/docs/quickstart` already did before this change. `PUBLIC_PATHS` lists
  top-level paths only and this change did not widen it. Pre-existing, recorded, not fixed.
- **The app navbar's link now leaves the app.** `Referencia API` still sits in the navbar and the
  footer, but it lands inside Starlight's docs, so the two surfaces have different chrome. That is
  the point of the change, and it is worth knowing before someone reports it as a bug.
- **`retired-paths.ts` is a table with one row.** It is shaped for more entries than it has; if it
  never grows, it reads as a module that exists only to be testable — which it does, and that is the
  reason it is separate from the middleware rather than a sign it should be merged back.
