# ODD Feature: starlight-docs

> **Status**: in progress on `feat/starlight-docs` off `main` @ `54abdc7`. Tasks 1–3 verified and
> committed as `20d6bc9`, `693db17` and `32bfcf8`; tasks 4–5 pending. Not pushed, not merged.
> **Created**: 2026-10-05
> **Workflow**: Organic Driven Development (ODD)
> **Source**: the vault note `Starlight — documentación del sitio con Starlight` (second-brain,
> `01 - Projects/Storico/Notas/`), reviewed against the repository and then verified by an
> empirical spike before a single line of product code was written.
> **Branch**: `feat/starlight-docs`

## Problem

The page that today lives at `/en/docs` and `/es/docs`
(`frontend/src/pages/[locale]/docs.astro`) is not documentation: it is one paragraph of copy held in
`src/i18n/en.json` and `es.json` under `pages.docs.*` and rendered as a list of six steps. The site
has a documentation URL and no documentation. The goal is a real docs site — shadcn/zod style —
mounted with **Starlight** inside the existing Astro project, in both locales.

## What the spike settled, measured

The source note chose Starlight and analysed it well as a *framework*, but it never tested it against
the application's real `astro.config.mjs`. Three of its premises were unvalidated; two were wrong or
incomplete. All of the following was measured in throwaway projects under `/tmp` (Astro 5.18.2,
Starlight 0.37.7, `@astrojs/vercel` 9.0.5), with the repository untouched.

| Premise | Measured outcome |
| --- | --- |
| `npx astro add starlight` is the way in | The command pins nothing. Latest Starlight (0.42.5) peers `astro ^7.2.10`; `>=0.38.0` requires Astro 6. **0.37.7 is the ceiling for Astro 5**, and `^0.37.7` cannot float past it. The repo is pnpm, and the command must be pnpm's. |
| Starlight can carry its own `locales` next to the app's i18n | **Hard failure.** With both configured the build dies in `astro:config:setup`: `[AstroUserError] Cannot provide both an Astro 'i18n' configuration and a Starlight 'locales' configuration.` Not a warning — the whole application build fails. |
| Starlight mounts at `/docs` | Starlight mounts at the **site root**: `src/content/docs/index.md` maps to `/` and collides with the landing page. The docs path comes from nesting the content. |
| Pagefind needs `output: 'static'` | **Not true here.** Under `output: 'server'` + `@astrojs/vercel`, Starlight prerenders its routes into `.vercel/output/static/` and Pagefind indexes them with real content. Search works. |

Retracted along the way: a first reading that pnpm breaks Starlight. It does not. pnpm's isolated
linker with unapproved build scripts silently generates zero docs pages with no error; with
`allowBuilds: {esbuild: true, sharp: true}` — which `frontend/pnpm-workspace.yaml` already carries —
pnpm behaves exactly like npm.

## Decision: Option B — Astro keeps owning i18n

Two configurations were built and verified end to end. Option B was chosen.

| | Option A (the note's decision) | **Option B (chosen)** |
| --- | --- | --- |
| i18n owner | Starlight (`defaultLocale: 'root'`) | Astro — the existing `i18n` block, untouched |
| Starlight `locales` | declared | **not declared** |
| Content layout | `src/content/docs/docs/`, `es/docs/` | `src/content/docs/en/docs/`, `es/docs/` |
| URLs | `/docs`, `/es/docs` | **`/en/docs`, `/es/docs`** |
| `astro.config.mjs` i18n block | must be **removed** | **unchanged** |
| Links, `PUBLIC_PATHS`, tests | four call sites plus one test pin `/en/docs` | **no change needed** |

Option B is not a downgrade in localisation: Starlight consumes Astro's i18n and the emitted Spanish
pages carry `lang="es"`, Spanish Starlight UI strings, `hreflang` alternates for `en`/`es`, and the
language picker. Measured on the built HTML, not inferred.

It also preserves the URL contract the app already has. `/en/docs` is pinned in
`frontend/src/components/react/__tests__/MobileNav.test.tsx:21,104`; `src/layouts/PublicLayout.astro:44,61`,
`src/components/astro/PublicFooter.astro:40` and `src/components/react/AccountPage.tsx:265` build the
link through `L('/docs')`/`localizedPath`. `/docs` unprefixed already reaches the right locale through
`src/middleware.ts` (`/docs` is in `PUBLIC_PATHS`, `src/i18n/utils.ts:41`), which is existing
behaviour, not new work.

## Scope

Replace the placeholder page with a Starlight site in both locales, losing nothing that exists today,
and stop shipping copy the product cannot keep.

## Non-goals, and why

| Out of scope | Reason |
| --- | --- |
| API reference rendered in Starlight from `openapi.json` | The community OpenAPI plugin is unnamed. There is no candidate to pin against Starlight 0.37.7, and the alternative (linking production Swagger) is a different feature. Must be decided separately. |
| The CSV import page | Its source is [[Storico — Qué se puede importar en CSV y qué no]], and the note requires publishing it only after follow-up 11 of `odd/tasks/csv-story-import.md`, which is still open: the production composition has never carried a real upload. Documenting it as verified now would repeat exactly the `api.astro` mistake. |
| Versioned documentation | Starlight has no native versioning. |
| A public architecture overview | The only documented architecture is internal ADRs. The prompt is retired rather than written. |
| Moving `docs/` into the docs site | `docs/` is internal engineering documentation (debt, VM runbook, auth model, an `AGENTS.md` mirror). It stays in the repository. Starlight is a renderer, never the source of truth — the file is. |

## Tasks

- [x] 1. Skeleton verified end to end: branch, Starlight `^0.37.7` installed, integration added to
      `astro.config.mjs` under Option B, `src/content.config.ts` with the `docs` collection, one
      placeholder page per locale, and a `pnpm build` that emits prerendered `/en/docs/` and
      `/es/docs/` with a populated Pagefind index. — `20d6bc9`
- [x] 2. Port the copy **before** deleting anything: five pages per locale, authored from
      `pages.docs.*` and `landing.features.card_3`, in neutral Spanish. — `693db17`
- [x] 3. Retire the old surface: delete `src/pages/[locale]/docs.astro`, drop the now-orphaned
      `pages.docs.*` keys from both locales, and retire the architecture half of `more_coming`.
      — `32bfcf8`
- [ ] 4. Guards: neutral-Spanish coverage for the markdown (the existing guard only reads `es.json`),
      and a locale-parity test that both locales expose the same page slugs.
- [ ] 5. Decide `api.astro` — deleted with a redirect, or kept as a landing that links to the future
      reference — and record the decision.

Task 2 is deliberately ordered before task 3: `docs.astro` is the only user-facing documentation that
exists today, and deleting it before its content is ported leaves `/en/docs` as a 404.

**Measured while closing task 1, and it changes that reasoning:** the prerendered Starlight route wins
route priority over the dynamic `[locale]/docs.astro`, so from `20d6bc9` onward `/en/docs` and
`/es/docs` already serve the placeholder instead of the existing page — the file still exists, but it
is no longer reachable. Tasks 1 and 2 therefore must land in the same unreleased slice; nothing is
deployed from this branch, and the window closes as soon as task 2 puts the real copy in place.

## Constraints

- **English technical artifacts.** All content, keys, commits and this file are in English. The
  Spanish *copy* is the exception and it is the product.
- **Neutral Spanish, never voseo** (ADR-008): "Selecciona", "Revisa", "Guarda". Starlight pages are
  not covered by the existing `neutral-spanish.test.ts`, which only scans `src/i18n/es.json`; task 4
  closes that hole rather than leaving the rule unenforced.
- **If the note and the code disagree, the code wins.**
- `frontend/src/content/docs/` does not exist yet, and neither does `src/content.config.ts`. No
  content collection is defined anywhere in the project today.

## Evidence log

| Work unit | Commit | Evidence |
| --- | --- | --- |
| 1 | `20d6bc9` | `pnpm build` emits `.vercel/output/static/en/docs/index.html` and `es/docs/index.html`; `.vercel/output/static/pagefind/pagefind-entry.json` reports `en` and `es` with `page_count: 1` each; `pnpm exec tsc --noEmit` exit 0; `pnpm test` **717/717 across 63 files**, unregressed; `astro.config.mjs` diff is additive only and the top-level `i18n` block is byte-for-byte unchanged. Pagefind found 3 HTML files. |
| 2 | `693db17` | Ten routes prerendered, five per locale; `pagefind-entry.json` reports `page_count: 5` for `en` and for `es`; sidebar links resolve to `/en/docs/...` and `/es/docs/...`; `lang="es"` and `hreflang` `en`/`es` present on the Spanish pages; a voseo grep over `src/content/docs/es/**` is empty; `tsc --noEmit` exit 0; `pnpm test` **717/717 across 63 files**. 20 of the 22 `pages.docs.*` keys ported, 2 retired by instruction. |
| 3 | `32bfcf8` | `docs.astro` deleted and `pages.docs` gone from both catalogs (`git diff --stat`: 24 deletions per file, zero insertions — no `\uXXXX` un-escaping leaked in); key parity holds at **763 = 763**; RED observed before the repoint (both catalogs failed with “does not declare pages.docs.step_2”) and GREEN after; `pnpm test` **719/719 across 63 files**; `tsc --noEmit` exit 0; build exit 0 with the ten routes and Pagefind at 10 HTML files, and the `[router]` duplicate-`/404` warning is gone. |

### Findings that changed the plan

- **Starlight's 404 shadowed the app's, site-wide — fixed in `693db17`.** Adding Starlight made `/404`
  defined twice: the build warned about it and the emitted `.vercel/output/static/404.html` was
  Starlight's, so every 404 on the site, not just under `/docs`, stopped serving
  `src/pages/404.astro` (app layout plus i18n). `disable404Route: true` restores it. The option
  exists in 0.37.7 (`utils/user-config.ts:227`). Astro says the duplicate route becomes a hard error
  in a future version, so this was not survivable.
- **Sidebar entries must use `link`, not `slug`.** With `prefixDefaultLocale: true` every route slug
  is locale-prefixed, and `slug` entries abort the build with “The slug \"docs/index\" specified in
  the Starlight sidebar config does not exist”: the prerendered 404 page resolves the sidebar with
  no locale, and the raw lookup never matches. `link` entries are locale-stripped paths and Starlight
  injects the current locale when rendering. Recorded in a comment in `astro.config.mjs`.
- **The note's claim that a test pins the docs copy was wrong, and this file repeated it.**
  `src/i18n/__tests__/api-docs-copy.test.ts` guards `api.astro` and the router table — it has
  nothing to do with `pages.docs`. The guard that actually pinned the docs copy is
  `provider-copy.test.ts`, via `pages.docs.step_2` in `ALL_PROVIDER_KEYS`. It was repointed to the
  four markdown files that now carry the provider enumeration.
- **A benign upstream warning, recorded so it is not mistaken for ours:** every build emits
  `[WARN] Astro.request.headers was used when rendering the route …starlight/routes/static/index.astro
  … not available on prerendered pages`, once per docs route. Measured present in the task-2 builds
  (10 occurrences each) and before task 3, so it comes from Starlight 0.37.7's own route under
  `output: 'server'`. Each locale's pages render with the right locale, so it has no observed effect.
- **`llm_backend_gemini` was dead copy.** The key existed in both locale files and was never
  rendered by `docs.astro`. It is visible now.
- **The app's own copy was not the source of truth for the UI labels.** The Spanish export page
  first said “haz clic en **Download**” over a button that reads **Descargar**, and called the
  selector target a “workspace” where the app says “espacio de trabajo”. Both corrected against
  `es.json` before committing.
- **Content links are locale-absolute in the markdown** (`[Quickstart](/en/docs/quickstart)` in the
  English files, `/es/...` in the Spanish ones). They render correctly and are verified, but the
  locale is duplicated per file and a future routing change would have to touch every link. Task 4
  pins the shape; normalising to Starlight's locale-less links needs its own verification, since it
  is not established here that Starlight rewrites body links the way it rewrites sidebar ones.
- **A `Duplicate id "es/docs/export"` warning from `starlight-docs-loader` is a stale-content-cache
  artefact, not a defect.** It appears only when a content file is edited between builds, the new
  entry wins (the rendered HTML carries the corrected copy), and removing `.astro/` yields zero
  warnings. `.astro/` is gitignored, so a fresh build never sees it.
| 2 | _pending_ | |
| 3 | _pending_ | |
| 4 | _pending_ | |
| 5 | _pending_ | |

## Open decisions carried in

- `api.astro`: delete with redirect, or landing (task 5).
- The `more_coming` promise: retired in task 3, since the architecture half has no content and the
  API half belongs to the deferred reference.
