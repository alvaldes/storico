# ODD Feature: api-reference

> **Status**: in progress, same stack, nothing pushed.
> **Created**: 2026-10-06
> **Workflow**: Organic Driven Development (ODD)
> **Source**: the largest missing surface in the docs, and the owner's decision on how to close it.

## Problem

The docs site documents the product's behaviour, not its API. `frontend/src/pages/[locale]/api.astro`
is a hand-written page that names a handful of endpoints, and the recorded debt was to revisit it
"when the Starlight API reference exists". Meanwhile the API has **36 paths, 54 operations and 60
schemas** — measured by generating the spec from the application:

```
conda run -n storico python -c "from storico.api.app import create_app; s = create_app().openapi(); ..."
→ paths: 36 | operations: 54 | schemas: 60 | $ref uses: 135
→ tags: workspaces 10, workspace-settings 9, stories 8, tasks 7, projects 5, health 3,
        settings 3, extract 2, extractions 2, users 2, auth 1, export 1, llm 1
```

## What the measurements settled, before any design

| Route | Verdict | Evidence |
| --- | --- | --- |
| Community OpenAPI plugin for Starlight | **Dead** | `starlight-openapi@0.26.3` peers `astro >=7.0.2` and `@astrojs/starlight >=0.41.0`; this repo is Astro 5.18.2 + Starlight 0.37.7. `astro-plugin-openapi` and `starlight-api-docs` do not exist on the registry at all. |
| Scalar island (`@scalar/astro@0.4.27`) | **Viable but invisible** | It installs and builds on Astro 5 — and contributes **zero searchable words**. Measured in a scratch project: the emitted HTML keeps an empty `<div id="app"></div>`, the spec travels only inside an inline `<script>`, Pagefind indexed 3 pages / 5 words, and a reader without JavaScript gets a blank page. |
| Hand-rolled prerendered page | **Chosen** | The owner's decision. Its value is that the endpoint names are in the HTML, and Pagefind indexes the docs because Starlight prerenders them. |

**And one constraint that decides where the spec comes from**: it must come from the **working tree**,
never from production. Production still declares `POST /api/v1/tasks/` as `201` while the route is
retired from the code (`routes/tasks.py:137-165`, 410, `include_in_schema=False`). A reference
generated from production's `openapi.json` would document an endpoint that no longer exists.

## Design

**A Python generator writes committed markdown into the docs collection.** The owner chose a
hand-rolled prerendered page; this is that, with the renderer in the language that already owns the
spec, and with the output landing where the docs infrastructure already polices it.

```
backend/scripts/render_api_reference.py
  reads  create_app().openapi()
  writes frontend/src/content/docs/{en,es}/docs/api-reference.md
```

Why this shape rather than a TypeScript renderer inside an Astro page:

- **Pagefind indexes it for free.** Starlight prerenders content-collection pages; an app page under
  `output: 'server'` has no HTML to index, which is the measured reason `/api` is invisible to search.
- **The docs guards already cover it**: slug parity between locales, sidebar coverage in both
  directions, link integrity, and the neutral-Spanish rule over markdown. A new hand-rolled page would
  need all of that again.
- **No `$ref` walker in the browser.** 135 `$ref` uses resolve on the server, once, with a cycle guard.
- **The guard is a byte comparison.** `backend/tests/` regenerates the pages in memory and fails when
  the committed files differ, so the reference cannot describe an API that changed underneath it.

### Deterministic output, or the guard is noise

Sorted tags, sorted paths, fixed method order, sorted field names, and a depth limit with a visited
set for recursive schemas. Same application, same bytes; that is what makes a byte comparison a
legitimate guard rather than a flaky one.

### The honest limitation, stated up front

**The API body is English in both locales.** The spec's summaries, field names and types are English
because the API is; only the page's chrome (title, description, intro) is localized. Publishing a
translated API in one locale and not the other would be worse than publishing one honest language, and
inventing Spanish field names would be a lie about the wire format.

## Scope

1. **The generator** — `backend/scripts/render_api_reference.py`, deterministic, with a cycle guard.
2. **The generated pages** — `frontend/src/content/docs/{en,es}/docs/api-reference.md`, committed.
3. **The sidebar entry** — `frontend/astro.config.mjs`, with its Spanish translation, so the docs
   guards accept the new pages.
4. **The drift guard** — a backend test that re-renders in memory and compares with the committed
   files, failing with the first differing line.
5. **Verify** — the new test, the docs guards, the frontend build, and Pagefind going from 9 to 10
   pages per locale.

## Non-goals

| Out of scope | Reason |
| --- | --- |
| `api.astro` | It stays as the short public overview. Replacing it with the reference is a separate decision, and the debt is recorded in `odd/tasks/starlight-docs.md`. |
| `docs/api.md` (408 lines of in-repo API prose) | Repository prose, not the docs site. It may well be stale — recorded as a finding, not fixed here. |
| `backend/spec-api-endpoints.md` and `spec-tasks-api-endpoints.md` | They are SDD **requirement** specs written before the implementation, duplicated under `docs/api/`. They are historical, not a competing reference. |
| Interactive "try it", generated clients, a machine-readable download | The measured alternative offers these and cannot be found by search. The trade was made deliberately. |
| Authentication flows, rate limits, versioning policy | Product prose, not endpoint shapes. |

## Tasks

- [x] 1. **The generator** — `445f931`: deterministic, with the one real bound (`seen`) stated as such
      after the depth limit that could never fire was removed.
- [x] 2. **Generate and review** both pages — `445f931`. 1555 lines per locale; the review was the
      generator plus the output, and what makes the result worth reading is that the code's own
      docstrings arrive with it (the extraction endpoint comes with its 202, its polling path, its 403
      codes and its `LLM_CONFIG_INCOMPLETE` refusal).
- [x] 3. **The sidebar entry** and its Spanish label — `445f931`.
- [x] 4. **The drift guard** — `445f931`, proven non-vacuous by injecting a stray line, watching it
      fail naming the file and printing the remedy, then regenerating.
- [x] 5. **Verify** — backend 5/5, docs guards 33/33, frontend suite **801/801 in 71 files**, cold
      build clean, **Pagefind `page_count: 10` per locale** (was 9), `ruff check` and
      `ruff format --check` clean.
- [x] 6. **One work-unit commit per task** — one commit, because the pieces are not independently
      committable: the guard fails without the generated pages, and the docs guards fail without the
      sidebar entry. Splitting them would have produced commits that do not stand alone, which is the
      opposite of reviewable.

## Constraints

- **Determinism is a requirement, not a preference.** The guard compares bytes; a generator that emits
  a set or a dict traversal whose order can vary would make it flaky.
- **The cycle guard must be exercised**, not assumed — and measuring showed the sentence I first
  wrote here was **wrong**: there is no recursive schema among the 60 components (every schema's
  `$ref`s were walked: zero self-references, zero cycles). The guard is exercised by a unit test with
  a synthetic recursive schema instead, and it pins which of the two bounds does the work.
- **No internal links from the generated page** unless they resolve per locale; the docs link guard
  fails otherwise, and a generated link is exactly the kind of thing that is correct in `en` and wrong
  in `es`.
- **The generated files are committed.** They are content, they are reviewed, and the guard keeps them
  true.

## Evidence log

| Task | Commit | What ran, and what it proved |
| --- | --- | --- |
| 1–6 | `445f931` | 6 files, 3483 insertions. The 3100 lines of generated markdown are the bulk and the least interesting part of it; the review surface is the 286-line generator and the 78-line guard. Measured end to end: the reference is in the search index (`page_count: 10` per locale) and the endpoint paths are text in the built HTML — the two things the rejected Scalar island could not do. |

### Corrections of record

1. **The design note claimed "a recursive schema exists in the 60". It does not.** Walking every
   schema's `$ref`s found **zero self-references and zero cycles**. The guard is therefore exercised by a
   unit test with a synthetic recursive schema, and the note says so now. Same shape as the others in
   this session: an assertion about the code, written before measuring it.
2. **The generator's first version carried a depth limit that could never fire** — `depth` was never
   incremented on the `$ref` descent — behind a comment claiming it bounded the expansion. Removed; the
   comment now names `seen` as the whole bound. Found by reading my own code against its own comment,
   which is the only way that defect is ever found.
3. **`ruff format --check` rejected the generator.** CI runs it over `src tests`, so this would have
   failed the pipeline rather than the review. Formatted, re-checked, re-tested.

### Not verified

| Item | Why |
| --- | --- |
| That the page **reads** well in a browser | The HTML is prerendered and the search index covers it, but nobody looked at the rendered page. Same posture as the rest of this session's visual work: measured mechanically, handed to the owner's eye. |
| `api.astro`'s relationship to the new page | It stays as the short public overview; replacing it with the reference is a separate decision and the debt stays recorded in `odd/tasks/starlight-docs.md`. |

## Findings recorded, not fixed

- `docs/api.md` is live in-repo prose about the API and nothing checks it against the code.
- `/api` exists in `PUBLIC_PATHS` and is not prerendered, so it is not searchable — the same reason
  the reference cannot live there.
