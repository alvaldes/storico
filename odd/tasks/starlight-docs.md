# ODD Feature: starlight-docs

> **Status**: planned, not started. Branch `feat/starlight-docs` off `main` @ `54abdc7`; the Starlight
> integration is not installed in the repository.
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

- [ ] 1. Skeleton verified end to end: branch, Starlight `^0.37.7` installed, integration added to
      `astro.config.mjs` under Option B, `src/content.config.ts` with the `docs` collection, one
      placeholder page per locale, and a `pnpm build` that emits prerendered `/en/docs/` and
      `/es/docs/` with a populated Pagefind index.
- [ ] 2. Port the copy **before** deleting anything: five pages per locale, authored from
      `pages.docs.*` and `landing.features.card_3`, in neutral Spanish.
- [ ] 3. Retire the old surface: delete `src/pages/[locale]/docs.astro`, drop the now-orphaned
      `pages.docs.*` keys from both locales, and retire the architecture half of `more_coming`.
- [ ] 4. Guards: neutral-Spanish coverage for the markdown (the existing guard only reads `es.json`),
      and a locale-parity test that both locales expose the same page slugs.
- [ ] 5. Decide `api.astro` — deleted with a redirect, or kept as a landing that links to the future
      reference — and record the decision.

Task 2 is deliberately ordered before task 3: `docs.astro` is the only user-facing documentation that
exists today, and deleting it before its content is ported leaves `/en/docs` as a 404.

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
| 1 | _pending_ | |
| 2 | _pending_ | |
| 3 | _pending_ | |
| 4 | _pending_ | |
| 5 | _pending_ | |

## Open decisions carried in

- `api.astro`: delete with redirect, or landing (task 5).
- The `more_coming` promise: retired in task 3, since the architecture half has no content and the
  API half belongs to the deferred reference.
