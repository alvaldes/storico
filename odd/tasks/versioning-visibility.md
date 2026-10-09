# ODD Feature: versioning-visibility

> **Status**: in progress. This slice closes the last user-visible gaps of the extraction-versioning
> feature: the story cards never said which version you are looking at, and the board could not be
> filtered by project, story or version.
> **Created**: 2026-10-07 (owner request on that date)
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/versioning-visibility`, off `main` @ `b3403d7`.

## Problem

Three measured gaps, all of them "the data exists but the surface does not show it or let you ask
for it":

1. **Story cards carry no version information.** Both story-card surfaces render the same
   component: `frontend/src/components/react/StoriesList.tsx` (mounted by
   `frontend/src/pages/[locale]/stories.astro` and, with `projectId`, by
   `frontend/src/components/react/ProjectDetail.tsx`). The card shows status, date and short UUID
   only. The version history is a per-story read (`GET /api/v1/stories/{story_id}/versions`,
   `backend/src/storico/api/routes/stories.py:271`), and `UserStoryResponse`
   (`backend/src/storico/api/schemas/story.py:35`) carries no version field at all — so showing it
   on a 100-row list from the frontend alone would cost one request per card.
2. **The board has no filters.** `KanbanBoard.tsx` fetches
   `GET /api/v1/tasks/?workspace_id={workspaceId}` and offers no project/story/version narrowing.
   The route already accepts `user_story_id` and an optional `extraction_id`
   (`backend/src/storico/api/routes/tasks.py:178-256`) but has **no `project_id` filter**.
3. **Board cards do not say which version they belong to.** `TaskResponse`
   (`backend/src/storico/api/schemas/task.py:102`) carries no `extraction_id` and no
   `version_number`, so a mixed board is unreadable.

Two measured limits that shape the design, both pre-existing and neither introduced here:

- `listTasksByWorkspace` asks for `size=100` (`frontend/src/lib/tasks-api.ts:31-36`). Client-side
  filtering over what is already loaded would therefore be wrong past 100 tasks, which is why the
  board filters are server-side.
- `TaskRepository.list_page` accepts **exactly one** scope among `workspace_ids`, `user_story_id`
  and `workspace_id` and raises `ValueError` otherwise
  (`backend/src/storico/infrastructure/database/repositories/task_repository.py:122-129`). The
  `workspace_id` scope also applies `_current_version_only`, so a frozen version's tasks are
  invisible on the board unless that exact `extraction_id` is requested
  (`task_repository.py:54-77,148-168`).

## Decisions

| #  | Decision | Choice |
|----|----------|--------|
| D1 | What the story card shows | Owner's choice (2026-10-07): `v3 · current` badge, the existing story-status badge (`[Extracted]`, `[Failed Extraction]`, …), the version count (`5 versiones`), date and short UUID. **Never lie about currency**: with no completed run the badge shows the newest run and its own status (`v1 · failed`) instead of the word "current". |
| D2 | Where the card's version data comes from | **Backend projection, one batched statement per list page.** A frontend-only version needs one request per card (up to 100). The projection is a new aggregate read on the extraction repository, called by the story read paths, not a per-story loop. |
| D3 | The projected shape | A nested `version_summary` on `UserStoryResponse`: `{count, current_number, latest_number, latest_status}` and `null` when the story has no runs at all. Flat fields would need four of them and could not express "no history" distinctly from "not projected". |
| D4 | Which story read paths project it | `list_stories`, `get_story` and `update_story` (all three have the story id at hand). `create_story` answers `null`, which is true for a story that was just created. |
| D5 | Kanban filter semantics | Owner's choice: **cascade project → story → version, resolved server-side, most specific filter wins.** Version → `user_story_id` + `extraction_id`; story → `user_story_id` (current version, per the existing read contract); project → the new `project_id` scope; nothing → `workspace_id` (today's board). |
| D6 | `project_id` on the tasks route | A new scope branch in `TaskRepository.list_page`, mirroring the `workspace_id` branch (`task → story → project`) and carrying the same `_current_version_only` predicate, so a project-scoped board obeys the same currency contract as the workspace board. |
| D7 | Several scope filters at once | **Refused with 422 `REQUEST_VALIDATION_FAILED`**, in the route, before any repository call — the same posture the route already takes for `extraction_id` without `user_story_id` (`api/routes/tasks.py:205-218`). Today the route silently prefers `workspace_id` over `user_story_id`; silently picking one is the failure mode this decision removes. No known client sends two scopes (`frontend/src/lib/tasks-api.ts:26,33`). |
| D8 | The version chip's data | `TaskResponse` gains `extraction_id` (already on the domain entity, `domain/entities/task.py:30-32`) and `version_number`. `version_number` is resolved by the route in **one batched lookup** of the page's distinct extraction ids — not by threading a new column through the `Task` entity or the port signature. Recorded as a second small index-backed statement because the alternative (a join in every task read branch) spreads a half-populated field across the domain entity. |
| D9 | Export | `TaskResponse`'s two new fields default to `None`; `api/routes/export.py:104` is left untouched. Export keeps its current shape. |
| D10 | Version labels | The cascade's version select labels are `v{n}` plus the currency marker (`v2 · current`), reusing `versionSelector.current` / `versionSelector.failed` copy rather than the full model-and-date label the story page's selector uses — the filter bar has one line, and the model/date is not a filter key. |
| D11 | Copy | Spanish UI copy stays neutral international per ADR-008; every new key lands in both `en.json` and `es.json`, guarded by the existing key-parity and neutral-Spanish tests. |

## Non-goals

- **No pagination work on the board.** The `size=100` cap stays. A workspace with more than 100
  current-version tasks already truncates today; this slice neither fixes nor worsens it.
- **No change to the current-version read contract.** The board still shows each story's current
  version unless a specific `extraction_id` is asked for (that is the point of the version filter).
- **No new version-selection on export**, and no change to `ExportPanel`.
- **No `project_id`/`version_number` on the export response.**
- **No chip on the story-detail task cards** — that surface already has the version selector.

## Verified facts (with evidence)

| Fact | Evidence |
|------|----------|
| Both story-card surfaces are the same component | `frontend/src/pages/[locale]/stories.astro` renders `<StoriesList>`; `ProjectDetail.tsx:127` renders `<StoriesList … projectId>`. |
| The story list read is capped at 100 by the store | `frontend/src/stores/storyStore.ts` → `api.listStories(projectId, 1, 100, workspaceId)`. |
| `UserStoryResponse` has no version field | `backend/src/storico/api/schemas/story.py:35-48`. |
| `is_current` is derived in the versions route, never stored | `api/routes/stories.py:303-307`. |
| `TaskResponse` has no `extraction_id` / `version_number` | `backend/src/storico/api/schemas/task.py:102-116`. |
| The domain `Task` already carries `extraction_id` | `domain/entities/task.py:30-32`; set in `task_repository.py:277`. |
| The board read is one scope, current-version-only | `task_repository.py:122-168`. |
| The board keeps no filter state | `KanbanBoard.tsx:31-58`; `taskStore.fetchTasksForWorkspace` (`stores/taskStore.ts:397`). |
| `ExportPanel` shares the same store slot and fetch | `ExportPanel.tsx:19,101,143`. |
| A third story-list surface exists, and it is in scope by owner decision | `Dashboard.tsx:124-135` ("Recent stories") lists stories with the project name and a date badge, and no version; WU3b adds the shared badge there. |
| A schema change makes the committed API-reference pages stale, and a test enforces it | `backend/tests/test_api_reference.py::test_committed_pages_match_a_fresh_render`; the fix is `conda run -n storico python -m storico.scripts.render_api_reference` from `backend/`, which writes `frontend/src/content/docs/{en,es}/docs/api-reference.md`. WU1 hit it. |

## Tasks

- [x] **WU1 — Story version summary (backend)** → `e9d0a4b`. `ExtractionRepository` aggregate
  read (`version_summaries(ids)`, plural — the batched-read convention `list_page` uses) + port
  read model `StoryVersionSummary` + `version_summary` on `UserStoryResponse` + projection in
  `list_stories`, `get_story`, `update_story` + backend tests + API-reference regeneration.
- [x] **WU2 — Task version projection and `project_id` scope (backend)** → `eaecad6`.
  `TaskResponse` gains `extraction_id`/`version_number`; the list route resolves version numbers
  in one batched lookup; `TaskRepository.list_page` gains the `project_id` branch; the route
  accepts `project_id` with membership validation and refuses multiple scopes with 422.
- [x] **WU3 — Story card version badge (frontend)** → `1b654c6`. `UserStory` type gains
  `versionSummary`; i18n keys; component tests.
- [x] **WU3b — Dashboard recent-stories version badge (frontend)** → `e875553` (owner's decision,
  2026-10-07). The row is a third surface of the same data and the payload already carried it — no
  backend change. The badge and the count label are now one shared piece
  (`StoryVersionBadge.tsx`), which is what the three surfaces needed to stop being three copies.
- [x] **WU4 — Kanban cascade filters (frontend)** → `70f0793`. The cascade resolves to a single
  server-side scope before the request leaves; the retry carries the active filters and a
  workspace switch clears them, both pinned by tests that assert the query, not the select's
  rendered value. Nine `kanban.*` keys added, `stories.allProjects`/`stories.selectProjectFirst`
  reused instead of duplicated.
- [x] **WU5 — Kanban version chip (frontend)** → `2947a83`. `Task`/`RawTaskItem` gained
  `extractionId`/`versionNumber`, `mapTaskItem` maps them, and `KanbanCard.tsx` renders a bare
  `v{n}` in the label row — never a currency marker, because the card cannot tell a frozen
  version's tasks from a current one's. `null` renders nothing. Three board-level tests pin it,
  including the absence of `v{n} · current` on a version-filtered board.
- [x] **WU6 — Specs and docs** → `7d8037f`. `extraction-versioning` gained the one-scope task
  read and the story version-summary requirement (22 → 23 requirements, 70 → 75 scenarios);
  `kanban-board` gained the Filter Cascade and Card-Version requirements and the third empty
  state (5 → 7 requirements, 8 → 18 scenarios). Both files are now the record of what the slice
  shipped, not of what preceded it.

## Limits and follow-ups

- **Regenerating the API reference is part of a unit only when the change alters what the generator
  renders** — a new or renamed component schema, or a route whose shape or summary moves. A field
  added to an existing response model does **not** change the rendered pages: the generator names
  component schemas without expanding their fields, so both pages stay byte-identical and
  `tests/test_api_reference.py` passes unedited. **Corrected on 2026-10-08:** this note used to claim
  the test fails otherwise, and the claim was false for field-level changes — measured when
  `TaskResponse` gained `project_id`/`project_name` (`dbbfab8`, feature `kanban-card-project-story`),
  where `python -m storico.scripts.render_api_reference` reported "already current" with zero diff.
  The two page paths still belong in a worker's surfaces whenever a render is expected, because the
  generator writes outside the unit's own files.
- The board's `size=100` cap is unchanged (D-non-goal) and is the reason the cascade is strict:
  project → story → version, with no workspace-wide story select.
- `version_summary` is projected on three read paths; a future write path that returns
  `UserStoryResponse` must project it too or answer `null` knowingly.
- **The cascade's story select is capped at 100** (`listStories(projectId, 1, 100, workspaceId)`),
  so a project with more than 100 stories has unselectable ones. Accepted for the same reason the
  board's task read is capped: this slice is about naming what is on the board, not about paging
  the selectors. A story's *versions* are not capped — `listVersions` returns the whole history,
  which is bounded by how many times the story was extracted.
- **The filter bar's story options are labelled with a raw `actor: feature` pair** — an
  implementer's choice for a select-sized label, **not** the stories page's copy: `StoriesList`
  renders the full sentence (`As a(n) X, I want Y, so that Z`, `StoriesList.tsx:469-476`), and the
  condensed pair is neither translated nor guaranteed unique within a project. Two options can
  therefore read identically. Nobody records a decision here because none was asked for; if the
  label needs to match the page's voice, that is a follow-up, not a defect of this slice.
- **Nine `kanban.*` keys were added and two `stories.*` keys reused.** `stories.allProjects` and
  `stories.selectProjectFirst` already carried exactly those ideas, so `kanban.filter_all_projects`
  and `kanban.filter_select_project` do not exist. A reader looking for the project select's
  "All …" copy will find it under `stories.*`.
- **D10 is implemented in part: `versionSelector.failed` is not used.** D10 names
  `versionSelector.current` / `versionSelector.failed` as the cascade's copy. The select reuses
  only `current`; a `failed` version reads as a bare `v{n}`, so the bar says less about it than
  the decision text anticipated. Recorded as a deviation, not a defect: the version is still
  selectable and the story page's selector names its status. If the bar should say so too, that
  is a follow-up.
- **`Task.extractionId`/`versionNumber` are optional, not required-nullable.** The truthful type
  is required-nullable — `TaskResponse` declares both and the API always sends them — but the
  legacy, uncalled mapper in `frontend/src/lib/api.ts` also constructs `Task` and was outside every
  unit's scope. `mapTaskItem` always sets both, and the type's docstring records the cause.
  Tightening is a one-liner once that mapper goes; deleting it is a separate cleanup.
- **The statement-count pins were measured, and there is no gap.** The tasks endpoint's page now
  issues one extra statement against `extractions` (WU2's batched version-number lookup).
  `test_unfiltered_list_queries.py` pins statements *against the endpoint's own table*, so its
  `1` for `tasks` is still exactly true; the extra read is pinned one level down by
  `test_version_numbers_resolves_a_batch_in_one_statement` and, for WU1,
  `test_version_summaries_issues_exactly_one_statement_for_the_batch` (with their two
  empty-input cases asserting zero statements). A comment was added to the endpoint pin so a
  future reader does not mistake it for a whole-endpoint count.
- **The cascade's story options are read once per project selection**, `listStories(projectId,
  1, 100, workspaceId)` from the board's own effect, never through `useStoryStore` — the stories
  page owns that store, and a board read must not overwrite the list it renders.

## Closure

Branch `feat/versioning-visibility`, off `main` at `b3403d7`. The slice is one work unit per task,
nine commits:

| Commit | Unit |
|--------|------|
| `9aedb2d` | plan (this document) |
| `e9d0a4b` | WU1 — story version summary projection |
| `eaecad6` | WU2 — task version projection and `project_id` scope |
| `1b654c6` | WU3 — story card version badge |
| `e875553` | WU3b — shared badge on the Dashboard's recent stories |
| `70f0793` | WU4 — kanban cascade filters |
| `71e52a4` | doc record for WU1–WU4 |
| `2947a83` | WU5 — kanban card version chip |
| `7d8037f` | WU6 — spec deltas, the pin comment and the `AGENTS.md` entry |

Gates, each run by the orchestrator on the full tree and not only on a worker's slice:

- `frontend`: `pnpm exec tsc --noEmit` exit 0, `npm test` 76 files / 862 tests passing, and
  `pnpm build` completing (the Astro build is the one gate vitest and `tsc` cannot cover).
- `backend`: `python -m ruff check src tests` clean, `python -m ruff format --check src tests`
  reporting 277 files already formatted, and the full suite — `python -m pytest -q` — at
  **1333 passed, 45 skipped**. The skips are the suite's own environment conditions and were
  neither added nor removed here: 21 for the missing Docker daemon (testcontainers Postgres),
  22 for `STORICO_TEST_LIVE_QDRANT` and 2 for `STORICO_TEST_LIVE_OLLAMA`. So the Docker-gated
  integration paths were **not exercised** by this run, and no claim in this document rests on
  them.
- The i18n key-parity and neutral-Spanish guards ran inside the frontend suite, so D11 holds by
  test and not by reading.

Left open, deliberately, and recorded above rather than fixed here: the D10 `versionSelector.failed`
copy the bar does not use, `Task`'s optional version fields (caused by the dead legacy mapper),
the 100-story select cap, the untranslated `actor: feature` story label, and the dead
`api.listTasksByWorkspace` / `mapTaskResponse` pair in `frontend/src/lib/api.ts`.
