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
- [ ] 5. **Localize the whole sidebar** with per-item `translations`, and widen
      `neutral-spanish.test.ts` to cover `astro.config.mjs` in the same commit — the new Spanish
      labels live in a file that guard does not read today, which is the same hole the `SiteTitle`
      literal opened.
- [ ] 6. **Correct ADR-003** in `AGENTS.md` with the code as evidence, in its own commit, and record
      the judge finding for the owner rather than silently rewording feature table 6.
- [ ] 7. **Verify.** The docs guards (slug parity, link integrity, sidebar coverage, neutral Spanish),
      the full suite, `tsc --noEmit`, the build, and a real-browser pass over every new page in both
      locales.

## Constraints

- **English technical artifacts.** The Spanish *copy* is the product and is neutral Spanish, never
  voseo (ADR-008). Terminology comes from `es.json`, not from invention: the app says *espacio de
  trabajo*, not *workspace*, and *Descargar*, not *Download*.
- **The sidebar label is a Spanish string that escapes today's guard.** `neutral-spanish.test.ts`
  reads `es.json` and `content/docs/es/**`; `astro.config.mjs` is in neither. Task 5 closes that.
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
- **A `[starlight-docs-loader] Duplicate id "en/docs"` warning appeared in the build — SETTLED, and it
  was cache, not content.** Measured with `frontend/.astro` moved aside and the build repeated: four
  `Duplicate id` warnings (the two index pages and the two `extraction-versions` pages) **became
  zero**, with the same 18 routes and Pagefind at 9 per locale in both builds. The earlier feature's
  diagnosis holds.
