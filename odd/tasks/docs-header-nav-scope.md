# ODD Feature: docs-header-nav-scope

> **Status**: closed, branch `feat/docs-header-nav-scope` off `main`, two commits, nothing pushed.
> One unrelated in-flight edit from another session is parked in a named stash — see below.
> **Created**: 2026-10-06
> **Workflow**: Organic Driven Development (ODD)
> **Source**: the owner asked that the docs header show only *Inicio* and *Estado*, pointing at
> `const navLinks = publicNavLinks(locale);` in `frontend/src/components/starlight/Header.astro`.
> **Supersedes**: the docs-header nav decision recorded in `odd/tasks/docs-app-navigation.md:38`
> ("the header gains `/docs`, `/api`, `/status`, mirroring `PublicLayout.astro`") and the guard it
> commissioned at `:82` ("a test that the docs header nav list equals the app's public nav list, so
> a divergence fails"). That doc is history and is not rewritten; this one records the change.

## Problem

The docs header renders the app's three public nav destinations — `/docs`, `/api`, `/status`, with
the labels `Documentación`, `Referencia API`, `Estado` — because it calls the same
`publicNavLinks(locale)` the app's navbar calls.

Two things are wrong with reading the request as a filter over that list:

1. **There is no "Inicio" to keep.** `PUBLIC_NAV_PATHS` has no `/` entry, and no translation key in
   either catalogue says *Inicio* or *Home* (`nav.back_to_home` is "Volver al inicio", a different
   thing). So "Inicio" is either a new destination or a relabelling.
2. **Filtering in the template is not available.** The guard at
   `frontend/src/i18n/__tests__/docs-header-nav.test.ts` forbids `Header.astro` from containing the
   strings `'/docs'`, `'/api'` or `'/status'` at all, so the header cannot name a destination and
   cannot express an exclusion. The list has to be declared in the module that owns it.

## The owner's decisions

- **"Inicio" is the app landing page (`/`)**, as a new destination with a new label key. The docs
  header nav becomes exactly `/` then `/status`.
- **Scope is the docs header only.** The app's public navbar keeps `Documentación`, `Referencia API`
  and `Estado`; the footer and the mobile nav keep theirs. This is a change to one surface, not a
  product-wide reduction.

## Why the list moves rather than filters

`src/lib/public-nav.ts` exists so the destinations cannot drift into a third hardcoded copy, and the
guard enforces that by refusing to let the header name a path. That constraint is worth keeping, so
the module gains a second declared list instead of the header gaining a filter:

- `PUBLIC_NAV_PATHS` — unchanged, `['/docs', '/api', '/status']`, consumed by the app navbar.
- `DOCS_HEADER_NAV_PATHS` — new, `['/', '/status']`, consumed by the docs header.

Both go through one builder, and every path in either list must have a label key, so a destination
cannot be added to a surface without a translation. `'/'` is deliberately **not** added to
`PUBLIC_NAV_PATHS`: the app navbar is out of scope.

## Scope

1. **`src/lib/public-nav.ts`** — declare `DOCS_HEADER_NAV_PATHS`, extend the label-key map with
   `'/' → 'home'`, and export a `docsHeaderNavLinks(locale)` that shares one builder with
   `publicNavLinks(locale)`.
2. **`src/i18n/en.json` + `src/i18n/es.json`** — add `footer.home`: `Home` / `Inicio`. Both
   catalogues, because the key-parity guard compares them key for key.
3. **`src/components/starlight/Header.astro`** — render from `docsHeaderNavLinks(locale)`, and
   correct the file's header comment, which currently describes the three-link list and cites the
   superseded decision.
4. **`src/i18n/__tests__/docs-header-nav.test.ts`** — redefine the guard: the app navbar's list must
   still be exactly the original three (that is the regression this change could cause), the docs
   header must still name no path itself, both lists must derive their labels from the catalogues,
   and every declared path must have a label key.
5. **`astro.config.mjs`** — one comment says the header carries "the shared public nav links"; that
   stops being true, and a comment that describes behaviour has to describe it correctly.
6. **Verify** — the focused guard, the catalogue guards, the full suite, `tsc`, a build, and the
   emitted docs HTML for both locales.

## Non-goals

| Out of scope | Reason |
| --- | --- |
| `PUBLIC_NAV_PATHS`, the app navbar, its mobile menu, the footer | The owner scoped this to the docs header. `mobileNavLinks` in `PublicLayout.astro:56-68` builds its own Resources links from the same three labels and stays as it is. |
| The docs sidebar | `astro.config.mjs`'s sidebar is Starlight's own structure, with its own labels; unrelated to this nav. |
| Rewriting `odd/tasks/docs-app-navigation.md` | It is the record of a decision that was correct when taken. This doc records the supersession; rewriting history would hide it. |
| Relabelling the `Docs` link in `SiteTitle.astro` | It goes to the docs home, and the owner chose the app landing for "Inicio". The two are different destinations, so there is no duplication to resolve. |

## Tasks

- [x] 1. **The module's second list and the new label key**, in both catalogues — `de02090`. Green on its
      own: nothing consumed the new list yet, so no rendered output changed.
- [x] 2. **The header renders from it**, comment corrected — `d729e45`, together with the guard.
- [x] 3. **The guard redefined**, with the app-navbar list pinned so this cannot spread — `d729e45`. The
      header and the guard move in one commit on purpose: the old guard is what pins the old header
      behaviour, so changing the header alone leaves the suite red.
- [x] 4. **Verify and close** — this commit.

## Constraints

- **The app navbar's list must be pinned, not merely untouched.** The dangerous outcome of this
  change is that a future edit reduces the navbar by editing the shared list, which is why the guard
  asserts the three app destinations explicitly rather than asserting a subset relation.
- **No path literal in `Header.astro`.** The existing guard case stays: it is what forces the list to
  live in the module.
- **Both catalogues or neither.** `neutral-spanish.test.ts:152` compares them key for key.
- **Neutral Spanish.** `Inicio` is standard Spanish, not voseo; `neutral-spanish.test.ts:144` checks
  the whole catalogue.
- **The label comes from a real key.** No hardcoded `Inicio` in the template.

## Evidence log

### Reconnaissance

- `PUBLIC_NAV_PATHS = ['/docs', '/api', '/status']` (`src/lib/public-nav.ts:19`), labels via
  `t.footer.{documentation,api_reference,status_page}`. No `/`, no home key in either catalogue.
- `localizedPath` is `/${locale}${path}` (`src/i18n/utils.ts:25`), so `'/'` yields `/en/` and `/es/`.
- `PublicLayout.astro:50` calls `publicNavLinks(locale)` and passes it to the navbar at `:131`, so
  leaving `PUBLIC_NAV_PATHS` alone leaves the navbar alone.
- `PublicFooter.astro` names each footer key explicitly; a new sibling key changes nothing there.
- Catalogue guards that will see the new key: key parity (`neutral-spanish.test.ts:152`), duplicate
  keys (`no-duplicate-keys.test.ts`), and the export-copy sweep over every string value
  (`export-copy.test.ts:59`), which only looks for retired export formats.

### The builder's type hole, caught in review

The first draft typed `buildNavLinks(paths: readonly PublicNavLink['path'][], …)` — which is
`readonly string[]` — and silenced the gap with `path as keyof typeof NAV_LABEL_KEYS`, while its
comment claimed that a path without a label key was a compile error. It was not. Proven by probe:
with the loose signature `tsc --noEmit` exited **0** on `buildNavLinks(['/no-such-path'], 'en')`;
with the parameter typed against the union of both path unions it fails with
`Type '"/no-such-path"' is not assignable to type 'NavPath'` and exits 2. Fixed in `de02090`, and
`public-nav.ts` is byte-identical after the probe was reverted (`cmp`).

### Emitted output, which is the only check that proves the header actually changed

| page | links inside `<nav class="… docs-app-nav …">` |
| --- | --- |
| `.vercel/output/static/en/docs/index.html` | `/en/` → `Home`, `/en/status` → `Status` |
| `.vercel/output/static/es/docs/index.html` | `/es/` → `Inicio`, `/es/status` → `Estado` |

Two links per locale, and the absence of `Documentación`/`Documentation` and
`Referencia API`/`API Reference` was checked **inside that element only**: both strings are also the
page `<title>` and a sidebar label, so a whole-document absence check would pass for the wrong
reason. Suite **71 files / 804 tests** green (main is 71 / 801; the guard goes from 12 cases to 15),
`tsc --noEmit` exit 0, `pnpm build` complete.

### An in-flight edit from another session, parked rather than absorbed

`frontend/src/components/starlight/SiteTitle.astro` was modified at **14:28** — after the previous
feature's commits and before this feature's worker started — by a session that is not this one. The
edit comments out the `brand-name` span and relabels the docs link from `Docs` to `Storico Docs`.
It is not part of this feature, so it is **not committed**. It is parked in a named stash:

```
stash@{0}: On feat/docs-header-nav-scope: wip: Storico Docs relabel (foreign edit, parked by the docs-header-nav-scope session)
```

Proven orthogonal by parking it: with the file back at `HEAD` the guard is **15/15 green**; with the
edit in the tree it is 14/15, failing only `keeps the visible header label at Docs in both locales`,
a case this feature does not touch.

Three defects travel with that edit. None is fixed here, because none belongs to this feature, and
all three are recorded so they are not lost when the stash is popped:

1. **The brand anchor loses its accessible name.** The emitted markup is
   `<a href="/en/" class="brand-link"> <img src="/favicon.svg" alt=""> </a>`. The file's own comment
   says the favicon is not a substitute and that without `t.app.name` the anchor "would serialise
   empty and have no accessible name". The guard does not catch it: it only requires `<img` **or**
   `t.app.name` to be present, and `<img` is still there.
2. **An unevaluated Astro expression ships as an HTML comment** on every docs page:
   `<!-- <span class="brand-name" translate="no">{t.app.name}</span> -->`. Astro preserves HTML
   comments written in the template and does not evaluate interpolations inside them.
3. **English copy inside `/es/docs`.** `Storico Docs` is the same string in both locales, and the
   file's comment justifies the single-word label precisely to avoid new untranslated copy.

## Limitations carried forward

- **The parked stash is not durable against an editor.** If a session has
  `SiteTitle.astro` open, saving it reproduces the edit and re-reddens the suite. Resolve it before
  pushing this branch.
- **The brand's accessible name is not guarded, only its presence as an image or text.** A future
  edit that empties the only text node of the brand anchor passes the guard. Closing that hole
  belongs with the `Storico Docs` decision, not with this feature.
- **The app navbar's list is pinned at the source level only.** The landing page is server-rendered
  and the build output has no prerendered copy of it, so the navbar pin rests on the module test and
  the source guard; it was not re-checked against emitted HTML here.
