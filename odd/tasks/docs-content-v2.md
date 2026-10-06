# ODD Feature: docs-content-v2

> **Status**: in progress on `feat/docs-content-v2`, stacked on `feat/docs-app-navigation` @ `95986cc`.
> Nothing is pushed, and `main` is untouched at `7728963`.
> **Created**: 2026-10-05
> **Workflow**: Organic Driven Development (ODD)
> **Source**: point 7 of `odd/tasks/starlight-docs.md` — *"Five thin pages, a faithful port of the
> `pages.docs.*` copy. The note's v2 pages … are unwritten."* — plus the owner's decisions on which
> pages to write, what to do with the false claims found in `AGENTS.md`, and whether to localize the
> sidebar.
> **Branch**: `feat/docs-content-v2`

## Problem

The documentation site has five pages of 12–15 lines each: a faithful port of retired placeholder
copy. Meanwhile the product has real, server-enforced behaviour that no page describes — a task state
machine that rejects invalid transitions, extraction versions that freeze when superseded, historical
context retrieved from a vector store, and a role model.

And the repository's own prose is not a safe source for any of it. Two false claims were found while
planning this feature:

| Claim | Reality |
| --- | --- |
| `AGENTS.md` ADR-003: *"Solo admins pueden crear workspaces"* | **False.** Any authenticated user creates a workspace and becomes its `ADMIN` (`backend/src/storico/api/routes/workspaces.py:112-115` guards nothing beyond `get_current_user`). There is **no system-level admin** anywhere in the codebase. |
| `AGENTS.md` feature table 6 and section 8: LLM-as-a-Judge validation as an MVP capability | **Not reachable from the web app.** `run_validation: false` is hardcoded in that path (`odd/tasks/rag-per-environment.md`, follow-up F6). The implementation exists and the UI never asks for it. |

## The rule that governs every page

**The source of truth is the code — never `AGENTS.md`, never `docs/`, never the landing copy.** Those
are exactly the surfaces that drifted. Every page must contribute a **claim → source map**
(`path:line`) to the evidence log below. **No claim without a source.** A claim that cannot be sourced
is omitted, not softened.

This is the rule `api.astro` paid for: a public page once advertised `/api/v1/batch`, an endpoint that
never existed, and `odd/tasks/csv-story-import.md` records the standard that followed — functional
verification, not inference.

## Scope

Write four pages, in English and neutral Spanish, each from the code, and wire them into the sidebar:

| Page | Slug | What it documents |
| --- | --- | --- |
| Kanban states and workflow | `kanban` | The five states, their order, the transitions the server allows, and what dragging a card actually sends |
| Extraction versions | `extraction-versions` | Versions, invalidation, and what happens to the tasks of a superseded version |
| Historical context (RAG) | `embeddings-rag` | Where the few-shot examples come from, the three per-workspace settings and their defaults, and the degraded path when the vector store is unreachable |
| Roles and permissions | `roles-permissions` | The two real roles, who owns a workspace, and what each role may do |

Plus: localize every sidebar label, and correct ADR-003.

## Non-goals, and why

| Out of scope | Reason |
| --- | --- |
| The CSV import page | Still **blocked**: the feature exists in code (`stories.py:479-484`, `story_csv.py:99`) and shipped in `v0.8.0`, but follow-up 11 of `odd/tasks/csv-story-import.md` is open — the production composition has never carried a real upload. |
| A public architecture overview | **Retired by decision** in `starlight-docs`; only internal ADRs document the architecture. |
| Deepening the five existing pages | The honest caveat on `llm-providers` (no automatic validation, no confidence score) and the real shapes of the two export formats are worth their own change. This feature adds pages; it does not rewrite the ported ones. |
| The prompt-versioning slice | `odd/tasks/extraction-versioning-prompt/apply-progress.md` is in progress. The versions page documents what is merged and nothing speculative. |
| The visual polish of points 3–5, the mono debt, the Starlight pin | Each needs its own decision. |
| Any backend change | This feature writes documentation and one correction to `AGENTS.md`. If a page turns out to need a code fix to be true, that is a finding, not a licence to edit the backend. |

## Tasks

- [x] 1. **Kanban states and workflow page** — `79d45e3`
- [x] 2. **Extraction versions page** — `79d45e3`
- [x] 3. **Historical context page** — `fcbdb35`
- [x] 4. **Roles and permissions page** — `fcbdb35`
- [x] 5. **Widen the guard over the Spanish sidebar labels** — `ca81ac1`. **Part one of this task was
      already done before the feature started, and the premise that produced it was mine and wrong**
      (see the correction of record below): all nine sidebar entries already carried a Spanish
      `translations` value, five of them since before this branch. The real work was the guard hole,
      and that was genuine — the variant rule read `es.json` and `content/docs/es/**` and never
      `astro.config.mjs`, so all nine Spanish labels were unguarded.
- [x] 6. **Correct ADR-003** — `5a8e1a1`, in its own commit. Two falsehoods, not one: the claim that
      only admins create workspaces, and a permission model with a team level that does not exist.
      The judge finding is recorded below rather than written into feature table 6.
- [x] 7. **Verify.** Done on the final tree, with the whole stack in place: the docs guards, the full
      suite (**777 tests in 68 files**), `tsc --noEmit` exit 0, a **genuinely cold** build (exit 0, zero
      duplicate-id warnings, **18 routes**, Pagefind **9 per locale**), and a real-browser pass over the
      eight new pages plus every docs link in both locales. Details below, including the one procedure
      error of mine that the verifier caught.
- [x] 8. **One work-unit commit per change**, on the feature branch, nothing pushed.

## Constraints

- **English technical artifacts.** The Spanish *copy* is the product and is neutral Spanish, never
  voseo (ADR-008). Terminology comes from `es.json`, not from invention: the app says *espacio de
  trabajo*, not *workspace*, and *Descargar*, not *Download*.
- **The sidebar labels are Spanish strings that escaped the guard.** `neutral-spanish.test.ts` read
  `es.json` and `content/docs/es/**`; `astro.config.mjs` was in neither. Task 5 closed that. The
  labels themselves already existed — that half of the finding was wrong, see the correction below.
- **Sidebar entries must use `link` with a locale-less path** (`/docs/<slug>`), never `slug`: with
  `prefixDefaultLocale: true` a `slug` entry aborts the build with *"The slug … does not exist"*
  because the prerendered 404 resolves the sidebar with no locale.
- **Every page must be listed in the sidebar.** `docs-content.test.ts` parses `astro.config.mjs` and
  fails on an unlisted page, which is the natural RED for each page task.
- **The route count changes from 10 to 18** (nine pages per locale) and Pagefind from 5 to 9 per
  locale. The previous feature's verification asserted 10 and 5; those numbers must be updated
  deliberately, not treated as a regression.
- **The versions page documents behaviour that is merged in this branch but absent from the published
  `v0.9.0`.** That is recorded here rather than hidden: `v0.9.0` shipped only the schema side of that
  feature.
- **No page may present LLM-as-a-Judge validation or a confidence score as something the product
  does.** It is unreachable from the web app.

## Evidence log

| Task | Commit | Claim → source map, and the checks that ran |
| --- | --- | --- |
| 1–2 | `79d45e3` | Both pages written from the code and audited clause by clause by an independent verifier: the transition table direction by direction, `INVALID_STATE_TRANSITION` with its 400 and its three fields, the drag's `PUT /api/v1/tasks/{task_id}` checked against the backend router, the three frozen operations with `TASK_VERSION_FROZEN`, `TASK_ALREADY_MARKED`, the single-active-mark index, the owner-or-admin gate, and the two 410-Gone endpoints. **Two defects were caught in the first draft and fixed before the commit** (see below). Guards 19/19; suite **765/765 in 68 files**; `tsc --noEmit` exit 0; build exit 0 with **14 routes** and Pagefind **7 per locale**. |
| 3–4 | `fcbdb35` | Both pages audited claim by claim by an independent verifier: **every flagged claim PASS**, including the ones I expected to be weakest. The per-environment collection *rationale* is stated verbatim in `config/settings.py:46-48`; the page names the mechanism and the default and asserts no deployed collection name; all ten payload fields exist in `infrastructure/vector/qdrant_adapter.py:317-326`; and the roles page matches `require_admin` and `require_owner` per endpoint. The writer refused to invent dev and prod collection names because they are not sourceable from the repository, and the verifier confirmed that reasoning. Suite **767/767 in 68 files**; `tsc --noEmit` exit 0; build exit 0 with **18 routes** and Pagefind **9 per locale**. |
| 5 | `ca81ac1` | The guard now extracts only the `translations.es` values from `astro.config.mjs`, so English labels, code and URLs are out of scope by construction, and asserts at least nine entries were found so a broken extraction fails loudly instead of passing vacuously. Observed RED before GREEN: a voseo label reports `carries voseo forms: descargá`. The whole-word tokenizer earns its keep here — a raw substring match would trip on `sos` inside `roles-permissions`. |
| 6 | `5a8e1a1` | ADR-003 corrected with the code as evidence: the create route requires only `get_current_user`, the creator becomes owner and admin, the roles are `admin` and `member`, ownership is `workspaces.owner_id`, there is no system-level admin, and none of the **fourteen** schema tables is a team. The Auth.js half was left alone because it is **real**: `@auth/core` in the frontend and the sync endpoint its JWT callback calls. |
| 7 | this commit | Verification on the final tree: **777 tests in 68 files**, all passing; `tsc --noEmit` exit 0; cold build exit 0 with **zero** duplicate-id warnings, **18 routes** (nine `index.html` per locale), Pagefind `en: 9` / `es: 9`; the two guard files at 31 tests. Browser pass over the eight new pages in both locales: correct `lang`, title and `h1` per locale, the Spanish sidebar rendering `Documentación` … `Roles y permisos`, **zero nested anchors**, all **18** docs URLs answering 200, and no horizontal overflow at 390 px. Two blemishes of mine, both recorded rather than tidied away: the procedure above named the wrong cache, and one evidence screenshot is named `storico-es-kanban-desktop.png` while showing the roles page. |

Two sentences were softened **after** the audit, on the verifier's own reading, so that no absolute
outlives the code: storage is described as what the server does when a run completes rather than as a
guarantee that every run is stored, and the degraded path no longer says an extraction *always*
succeeds — it says it *still* succeeds. Task 7 re-checks the final bytes.

### Defects verification caught in the first draft

Both were the failure mode this feature exists to prevent, and both were in the *writing*, not in
the plumbing:

1. **"records … your name" was false.** The invalidation mark stores `marked_by: UUID`,
   `marked_at`, `revoked_by` and `revoked_at` (`backend/src/storico/api/schemas/task.py:63-67`) — an
   identity and a timestamp. **No display name is stored or resolved anywhere.** The page now says it
   records which user marked it and when, which is what the row actually holds.
2. **The frozen condition was incomplete.** The page tied freezing to a newer run completing. The
   code says *"Frozen means: the story has no `completed` version at all, or the task belongs to a
   superseded one"* (`backend/src/storico/api/routes/tasks.py:120-134`). Both cases are now stated.

### Findings recorded, not fixed

- **The app's own Spanish copy contradicts itself about "workspace".** `frontend/src/i18n/es.json`
  says *espacio de trabajo* 38 times and leaves the English *workspace* 11 times, and the two live in
  the same feature area: `kanban.no_workspace` and `kanban.empty_board` say *workspace*, while
  `export.no_workspace` on the same screen family says *espacio de trabajo*. The docs use *espacio de
  trabajo*, which is the majority and the better Spanish. Fixing the app's copy is its own change.
- **A `[starlight-docs-loader] Duplicate id "en/docs"` warning appeared in the build — the conclusion
  was right, the mechanism I wrote down was wrong.** The real content store is
  **`node_modules/.astro/data-store.json`**, not `frontend/.astro`. Astro's glob loader warns when
  `store.has(id)` (`astro/dist/content/loaders/glob.js:107`), and that store survived every earlier
  "cold" build because it lives under `node_modules`. The final verification reproduced the warning
  under my literal procedure (2 warnings, same 18 routes, Pagefind still 9/9) and cleared it to **zero**
  once `node_modules/.astro` was moved aside too. The effect is benign and the loader's own message
  says so — *"later items with the same id will overwrite earlier ones"* — and the output carries
  exactly nine `index.html` per locale, so nothing was duplicated on disk. A CI build is cold by
  construction, which is why this never escaped into a deploy.

### Correction of record — a finding I asserted without verifying it

While planning task 5 I claimed that `/es/docs` shows its sidebar in English, and asked the owner to
have it localized. **That was false.** All nine sidebar entries already carried a Spanish
`translations` value; the five older ones were present at the branch base — `git show
95986cc:frontend/astro.config.mjs` holds five of them — and in `main` as well.

The mistake was mine, and it is the exact failure this feature exists to prevent: I read the `label:`
values, which are the English labels, and concluded from those neighbours that no other locale had
copy, instead of reading the file. The owner's answer to that question was therefore moot.

What survives is the **other** half of the same observation: the guard never read that file, so those
nine Spanish strings were genuinely unguarded. That half was real work and it landed in `ca81ac1`.

Rule worth keeping: a claim about what a file contains is verified **in the file**, never inferred
from a list of its neighbours' fields.

**Second correction, same shape.** The `Duplicate id` closure above named `frontend/.astro` as the
cache. That is not the content store — `node_modules/.astro/data-store.json` is — which is why the
warning survived my "cold" build and only vanished under the verifier's genuinely cold one. The
conclusion held (stale cache, not content); my mechanism did not, and the bullet above now carries the
sourced one.

### The judge finding, recorded for the owner

`AGENTS.md` still lists *Validación LLM-as-a-Judge* as MVP feature 6 of the core engine, and section 8
still draws it in the extraction pipeline. The implementation exists and **the web app never asks for
it**: `frontend/src/lib/tasks-api.ts:139` sends `run_validation: false`, the route default is `False`
(`backend/src/storico/api/schemas/extraction.py:67`), and a confidence score is only produced when
validation runs. The new docs page says exactly that.

Feature table 6 and section 8 were **not** rewritten: that is a decision the owner has not made. The
honest state of the product is now written down in two places — the docs page and this file — instead
of zero.
