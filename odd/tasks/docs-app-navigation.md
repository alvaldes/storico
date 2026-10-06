# ODD Feature: docs-app-navigation

> **Status**: complete on `feat/docs-app-navigation` off `main` @ `7728963`. Tasks 1–6 done and
> verified; the last commit is `80ba4be`. **Not pushed**: the owner reviews before deciding push and
> PR, exactly as `starlight-docs` was left.
>
> **Verified**: `/en/docs` and `/es/docs` serve a header whose brand returns to the app and whose
> `Docs` label opens the docs home, with the app's three public nav links from `md` up. **763/763
> tests in 68 files**, `tsc --noEmit` exit 0, build exit 0 with ten prerendered routes and Pagefind
> at five pages per locale, and a real-browser pass over both locales at desktop and mobile widths.
> **Created**: 2026-10-05
> **Workflow**: Organic Driven Development (ODD)
> **Source**: open points 1 and 2 of `odd/tasks/starlight-docs.md`, chosen by the owner as the next
> line of work on the Starlight documentation site. Nothing here re-opens the closed feature; it
> closes the two navigation gaps that feature recorded and left to the owner.
> **Branch**: `feat/docs-app-navigation`

## Problem

Two things are wrong with the header of the Starlight docs site, and they are the same problem seen
from two sides: **the docs do not know where they live, and they do not know where the app is.**

1. The header title renders `Storico Documentation` and links to `/en` — the app root — not to the
   docs home. Starlight computes that href as `formatPath(locale)`
   (`node_modules/@astrojs/starlight/utils/routing/data.ts:126-128`, consumed by the default
   `SiteTitle.astro:3,8`), so the link is a locale root **by construction**, not by misconfiguration.
   The label is a lie about its destination, and in `/es/docs` it is also English copy inside a
   Spanish locale, which ADR-008 governs.
2. There is no path from the docs back into the app: no logo, no nav, no footer. Once you are in
   `/en/docs` the only way out is editing the URL.

## Decision

Recorded from the owner's answers, with the evidence that produced them.

| Question | Owner's answer | Consequence |
| --- | --- | --- |
| How far does the way back go? | Minimal (brand → app, title → docs) **plus the app's nav links in the docs header** | The header gains `/docs`, `/api`, `/status`, mirroring `PublicLayout.astro:34-38` |
| What happens to the title? | Shorten it to `Docs` | The visible header label is `Docs` in both locales. No new Spanish copy, so the neutral-Spanish guard stays valid without widening |

**On the title, a call made while planning, recorded so it can be reversed cheaply.** Starlight's
`title` config is not only the header label: it feeds the document `<title>` and the social metadata.
Shrinking `title: 'Storico Documentation'` to `'Docs'` would turn every docs tab into
`Quickstart | Docs` and quietly degrade the SEO strings. So `astro.config.mjs` keeps its `title` and
the **header label** is shortened to `Docs` inside our `SiteTitle` override, which is the surface the
owner was looking at when choosing. One string changed, tab and social metadata untouched. If the
owner wants the document title shrunk too, it is a one-line change in `astro.config.mjs`.

## Scope

Give the docs header (a) a title that goes where it says, (b) a brand link into the app, and (c) the
app's three public nav links — all locale-aware, all in pure `.astro`, with the app's navbar
rendering unchanged.

## Non-goals, and why

| Out of scope | Reason |
| --- | --- |
| Open points 3, 4, 5 and 6 of `starlight-docs` | Callout hues, the untinted search modal, the dark sidebar contrast, and the 404 trade all remain open and undecided. This feature touches navigation only. |
| The `JetBrains Mono` / `Geist Mono` inconsistency | App-level debt recorded by the previous feature. It needs its own decision, not a ride along this branch. |
| Upgrading Starlight past `0.37.7` | Starlight `>=0.38` requires Astro 6. Out of reach until the Astro upgrade, which is its own feature. |
| An app-identical navbar inside the docs | `PublicNavbar` is `.astro` plus three React islands (`ThemeToggle`, `MobileNav`, `PublicUserMenu`, all `client:idle`). Embedding it would drag React into Starlight's layout and erase the boundary between the two surfaces. The docs get Astro links, and Starlight's own theme, search and language controls stay in charge of their jobs. |
| Replacing the docs' mobile menu with the app's | Starlight's mobile drawer owns the small viewport. The brand link in the header is the always-visible way back on mobile; changing the drawer is a different feature. |
| Making `/docs` reachable from inside the docs nav | The nav carries `/docs`, which is the docs site itself. Harmless, and it is what the app advertises. |

## Tasks

- [x] 1. **One source for the app's public nav links.** — `694dcc7` Extract the desktop nav list out of
      `src/layouts/PublicLayout.astro:34-38` into a module (proposal: `src/lib/public-nav.ts`) and
      consume it from there, with the rendered `PublicNavbar` output unchanged. The docs header
      consumes the same module, so the list cannot drift into three copies.
- [x] 2. **Give the docs a header that knows where it is.** — `80ba4be` Add `src/components/starlight/SiteTitle.astro`:
      the brand mark links to `L('/')` (app home) and the label reads `Docs` and links to `L('/docs')`
      (docs home). Locale-aware through `localizedPath`, the same helper `PublicNavbar` and
      `PublicFooter` already use.
- [x] 3. **Put the app's nav into the docs header.** — `80ba4be` Fork Starlight's default `Header.astro` into
      `src/components/starlight/Header.astro` and insert the shared nav links in the right-hand
      cluster, visible from `md` up. The fork must carry a comment naming the upstream version it was
      copied from (`@astrojs/starlight@0.37.7`) and the obligation to re-sync it on upgrade.
- [x] 4. **Wire both overrides** — `80ba4be` in `astro.config.mjs` (`components.SiteTitle`, `components.Header`)
      alongside the existing `Head` and `ThemeSelect` entries.
- [x] 5. **Guards.** — `80ba4be` A test that the docs header nav list equals the app's public nav list, so a
      divergence fails the suite instead of shipping, plus a check that both overrides stay wired.
- [x] 6. **Verify.** — see the evidence log and the browser pass below `pnpm test`, `pnpm exec tsc --noEmit`, `pnpm build` (ten routes, Pagefind per
      locale), the app's navbar unchanged, and a real-browser pass over `/en/docs` and `/es/docs` at
      mobile and desktop widths: title goes to the docs home, brand goes to the app, the three links
      carry the right locale prefix.

## Constraints

- **English technical artifacts.** Code, comments, commits and this file. The Spanish *copy* rule
  applies only if new Spanish copy appears — this feature adds none.
- **Neutral Spanish, never voseo** (ADR-008). `Docs` is identical in both locales, so
  `neutral-spanish.test.ts` needs no widening. If the label ever becomes Spanish, that guard must
  learn to read `src/components/starlight/**` in the same commit.
- **`pnpm preview` does not work here**: `@astrojs/vercel` rejects it. Serve the built output instead
  (`cd .vercel/output/static && python3 -m http.server 4322`). Pagefind only runs in a production
  build, not under `pnpm dev`.
- **Playwright is absent.** Browser evidence comes from a real ego-browser session and must say so.
- **A forked `Header.astro` is upstream markup we now own.** Every Starlight upgrade must diff it
  against the new default. This is the price of changing header structure without abusing the
  `SocialIcons` slot, and it is paid explicitly rather than silently.
- The docs still do not use `PublicLayout`, and this feature does not change that.

## Evidence log

| Work unit | Commit | Evidence |
| --- | --- | --- |
| 1 | `694dcc7` | `public-nav.ts` holds the paths and maps them onto the existing `footer.*` keys; `PublicLayout` consumes it. `pnpm test` **763/763 across 68 files** with the refactor in place, and the app home's server-rendered HTML still carries `data-public-nav` with `/en/docs`, `/en/api`, `/en/status` (measured with `curl`, not inferred — the app home is SSR-only, so it has no prerendered HTML to grep). |
| 2–5 | `80ba4be` | Emitted HTML: brand `<a href="/en/" class="brand-link">` with the favicon and the text `Storico`; `<a href="/en/docs" class="docs-home-link">Docs</a>`; header nav `/en/docs`, `/en/api`, `/en/status`. Spanish: `/es/`, `/es/docs`, `/es/api`, `/es/status`. **Zero nested anchors across all ten emitted docs pages.** `<title>` still reads `Documentation \| Storico Documentation`, proving the `title` config was not shrunk. `tsc --noEmit` exit 0; 12 warnings, all the three known-benign classes, no new one. |
| 6 | (no commit) | Real browser, ego-browser on `pnpm dev` port 4322: desktop 1440 and mobile 390, both locales. Brand visible and named `Storico` at both widths, `Docs` visible at both widths, app nav visible at 1440 and correctly hidden at 390 — where the brand is what keeps a way back. Zero nested anchors in the live DOM, no header overflow, no horizontal body overflow at either width. Clicking the brand from `/en/docs` lands on `/en/`; clicking `Docs` from `/en/docs/quickstart` lands on `/en/docs`. |

## Open decisions carried in

- **Point 6 of `starlight-docs` stands**: a bad URL under `/docs` still renders the app's branded
  404, because `disable404Route: true` keeps the brand's 404 site-wide. Not revisited here.
- **The mono debt stands**: `globals.css:141` declares `JetBrains Mono`, which is never loaded, and
  `Geist Mono` is what actually arrives.

## The defect verification caught, and the guard gap it exposed

The first implementation of task 2 **passed its own guard while shipping invalid markup**. The
emitted header was an anchor inside an anchor:

```html
<a href="/en/" class="site-title sl-flex"><a href="/en/docs" class="docs-home-link"> Docs </a></a>
```

Two consequences, and the second is the one that matters: the markup is invalid HTML, and because
Starlight has **no `logo` configured** the outer brand anchor held no image and no text, so the link
whose entire job is "return to the app" serialised with no accessible name and no visible target.

The guard missed it because it asserted that `href={L('/')}` appears in the source, and an anchor
nested inside an anchor satisfies that. **The defect was found by reading the emitted HTML, not the
source** — which is why the verification step checks the built bytes and not the code that produces
them.

The fix is two **sibling** anchors inside the `.site-title` wrapper: the brand carries the favicon
and `t.app.name` (mirroring `PublicNavbar`), and `Docs` carries its own link. The anchor walk was
added to the guard so this class fails the suite, labelled in the test file as a source-level
approximation whose authoritative check remains the emitted HTML. It is not a rendering test and does
not claim to be.

**`/en/` with the trailing slash is correct — do not "fix" it.** `localizedPath('/', 'en')` produces
it and the app's own navbar builds its brand with the same `L('/')`, so the two surfaces agree.

**A note for whoever verifies next by browser.** A dev server from a previous session was already
listening on 4321 and answered `200` for `/en/docs`; `pnpm dev` then started on 4322. The browser
pass above reads 4322 deliberately, because a stale server on 4321 would answer with old bytes. The
foreign server was left running and untouched.

