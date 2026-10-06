# ODD Feature: docs-truth-closure

> **Status**: in progress on `feat/docs-visual-polish`'s stack (branch to be cut off it).
> Nothing is pushed; `main` stays at `7728963`.
> **Created**: 2026-10-06
> **Workflow**: Organic Driven Development (ODD)
> **Source**: the gaps found while inventorying "what is left to finish the docs". Every task here is
> a place where a public surface says something the code does not, or where a document of record
> points at something that moved.

## Problem

Four public or semi-public surfaces are out of step with the code, and they are the cheapest thing
left to fix:

| Surface | What it says | What the code does |
| --- | --- | --- |
| `frontend/src/content/docs/{en,es}/docs/llm-providers.md` | Nothing at all about automatic validation — **zero** matches for `judge`, `validation`, `confidence` or the Spanish equivalents | The app **never** asks for it: `frontend/src/lib/tasks-api.ts:139` sends `run_validation: false`, and the route default is `False` (`backend/src/storico/api/schemas/extraction.py:67`). A confidence score only exists when validation runs. |
| `frontend/src/content/docs/{en,es}/docs/export.md` | "JSON as an array of tasks, Markdown with one section per story" | `backend/src/storico/api/routes/export.py:35-71` and `:95-135`: Markdown is `# Tasks Export` + `## {story}` + `- **{title}** — {description} #{label} → {dependency}`, and JSON is an array of ten named fields. Also undocumented: unsupported formats answer `400 UNSUPPORTED_EXPORT_FORMAT`, and the export carries only the workspace's **current** tasks. |
| `AGENTS.md` feature table 6 and section 8 | *Validación LLM-as-a-Judge* as MVP feature 6, drawn inside the extraction pipeline | Same as the first row. The owner decided to correct it: **implemented, not reachable from the web app.** |
| `prod.todo.md:49` | `POST /api/v1/tasks/` is announced as `201` and returns `500` — filed as an **open code defect** | **The endpoint no longer exists.** It is retired at `backend/src/storico/api/routes/tasks.py:137-165`: `@router.api_route("/", methods=["POST"], status_code=410, include_in_schema=False)`, `TASK_CREATION_ENDPOINT_REMOVED`. `DELETE /api/v1/tasks/{task_id}` retired the same way at `:423`. |

Plus one document-of-record defect: `prod.todo.md:97` names `pages.docs.step_6` among the keys to
change when the extraction-versioning feature alters behaviour — **that key was deleted** by task 3 of
`starlight-docs`. The copy it refers to now lives in the Starlight markdown.

## The correction that removed a whole feature

Decision 3 of this session was "fix the backend route before documenting it", taken on the premise
that `POST /api/v1/tasks/` declares `201` and returns `500`. Measuring first showed the premise is dead
in the working tree, so **no backend work is needed and none will be written**. What remains is not a
code defect but a **deployment gap**:

- `AGENTS.md` records that the published `v0.9.0` shipped **only the schema side** of the
  extraction-versioning feature — no endpoints, no UI. The retirement above is part of that code side.
- The operator's measurement of production (`prod.todo.md:49`, 2026-09-30) found the `201` declared
  and Swagger publicly reachable.

So production plausibly still serves the old shape. **That is an inference, not a measurement**: the
production API host is in the VM's `.env` and Vercel's environment, not in this repository, so nothing
here can confirm it. Two ways to settle it, both cheap: ask for the host and read
`GET /openapi.json`, or read it at the next backend deploy. Recorded as an inference with its
verification named — never as a fact.

## Scope

1. **`llm-providers.md`, both locales** — the honest caveat: the product does not run automatic
   validation from the web app today, so no confidence score is shown to the user. Must not present
   validation as something the product does; must not imply the engine lacks it.
2. **`export.md`, both locales** — the real shapes of both formats, the `400` on an unsupported format,
   and the fact that invalidated tasks are excluded. Every claim sourced from `routes/export.py`.
3. **`AGENTS.md`** — feature table 6 and section 8 say the implementation exists and the web app does
   not reach it. Minimal edit: no rewrite of the product definition.
4. **`prod.todo.md`** — two rows. `:49` becomes a deployment gap with the retirement cited and the
   production question marked unverified; `:97` is retargeted from the deleted `pages.docs.step_6` to
   the Starlight markdown that now carries that copy.
5. **`frontend/src/styles/starlight.css` header comment** — it says a value change in `globals.css`
   "must be mirrored here by hand". The drift guard now enforces it; the comment must say so, or the
   next reader will think the discipline is voluntary.
6. **Verify** and one work-unit commit per surface, docs copy included.

## Non-goals, and why

| Out of scope | Reason |
| --- | --- |
| Any backend change | Measured: the retirement already exists. Writing a fix for a defect that is not in the code would be work manufactured from a stale row. |
| The API reference itself | Its own feature, and it waits on the spike that measures whether a generator survives Starlight 0.37.7. |
| The CSV import page | Still blocked by the app, not by the docs: follow-up 11 of `odd/tasks/csv-story-import.md`. |
| The mono font and the `StatusPanel` key defect | Both touch the app, not the docs. Separate feature. |
| The guard's count-calibrated floors, the stale `starlight.css` comment aside | Recorded in `odd/tasks/docs-visual-polish.md`; the comment is task 5 here, the floors are recorded and left. |
| `docs/` (the repository's own prose) | Its recorded drift (Docker Compose vs the real dev database) is a separate decision the owner already made: recorded, not corrected. |

## Constraints

- **The source of truth is the code**, never another document. Every claim in the two pages carries a
  `path:line` into the evidence log.
- **Neutral Spanish** (ADR-008), and the terminology comes from `es.json`: *espacio de trabajo*,
  *historia de usuario*, *etiquetas*, *descarga*.
- **`AGENTS.md` is the project's constitution.** The edit stays minimal and additive: it corrects a
  claim about the software's reachable surface, it does not rewrite the product's definition.
- **A stale row is evidence, not a task list.** The `:49` correction is the model: measure, then write
  what is true, including the part that remains unverified.

## Tasks

- [ ] 1. **`export.md`, both locales** — the real shapes, the `400`, the current-only scope.
- [ ] 2. **`llm-providers.md`, both locales** — the validation caveat.
- [ ] 3. **`AGENTS.md`** — table 6 and section 8.
- [ ] 4. **`prod.todo.md`** — the `:49` deployment gap and the `:97` retarget.
- [ ] 5. **`starlight.css` comment** — say that the drift guard enforces the mirroring.
- [ ] 6. **Verify**: docs guards, suite, `tsc`, build; and a read-back of every edited claim against
      its source line.
- [ ] 7. **One work-unit commit per surface.**

## Evidence log

| Task | Commit | What ran, and what it proved |
| --- | --- | --- |
| 1–2 | `3f41536` | Both pages deepened in both locales. **The delegation failed mid-flight** — `gentle-ai-worker` died with "assistant reported an error" after 16 turns, so no evidence report ever arrived; the edits were on disk and the parent audited every claim against the source instead. That audit is what caught the one claim that would have shipped wrong: the first draft said the export carries "the same current version the version selector shows", which is true of the selector's default and misleading about the rest. Verified while auditing: `_current_version_only` (`task_repository.py:54-77`) requires the task's run to be `COMPLETED` **and** forbids a higher-numbered completed run, so two exclusions were missing from the page and are now stated — a pending or failed run contributes nothing, and the export ignores the selector. The JSON field list matches `routes/export.py:104-115` one for one. Docs guards 31/31; full suite **798/798 in 70 files**. |
| 3 | `c5a7409` | Three sites, not the two the decision named: the executive description at line 197 also asserted the capability, and leaving the summary contradicting the corrected table would have been worse than doing nothing. **Correction of my own earlier record**: the previous feature logged that section 8 "draws the judge in the pipeline". It does not — section 8's diagram has no judge box; what it carries is a `confidence score` line in its response step, and that is what needed the qualifier. The note added says the engine flow is correct *as a description of the engine*, rather than deleting the flow. |
| 4 | `f2f3bdb` | Both rows measured before rewriting. `:49` — the endpoint is retired (`routes/tasks.py:137-165`, 410, `include_in_schema=False`), so the owner's decision to fix the route first had no object and no backend work was written. It is a deployment gap, and the production reading is marked unverified on purpose with its two ways to close it. `:97` — three intents, not zero: invalidation is implemented **as a mark** with single-task deletion retired (D12), the export is half done (it already carries only the current version, but the user cannot choose), and editability is still pending; the third key no longer exists. |
| 5 | `7209ded` | The comment now says the mirroring is enforced. Drift guard re-run after the edit: 13/13. |

### Not verified, and why

| Item | Why |
| --- | --- |
| The API-reference approach | The measurement spike **failed twice**: once because `gentle-ai-explore` has no shell, and once as a plain model error (`assistant reported an error`, 28 turns). Nothing was measured, so nothing is claimed. The one mechanism that *is* sourceable says a plugin would have to write into the single `docs` collection whose slug is the file path, which our `en/docs` + `es/docs` nesting turns into locale-less slugs — the failure already recorded in `astro.config.mjs:29`. |
| Production's current `openapi.json` | The production API host is not in this repository. |

## Findings recorded, not fixed

- `prod.todo.md:49`'s defect is fixed in the working tree and outstanding in production. Until a
  backend deploy lands, production's public Swagger and `openapi.json` keep describing the retired
  endpoint — and generating an API reference from *production's* spec would inherit it. The reference
  feature must therefore generate from the working tree, not from the live endpoint.
