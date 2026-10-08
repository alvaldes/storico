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
| A schema change makes the committed API-reference pages stale, and a test enforces it | `backend/tests/test_api_reference.py::test_committed_pages_match_a_fresh_render`; the fix is `conda run -n storico python -m storico.scripts.render_api_reference` from `backend/`, which writes `frontend/src/content/docs/{en,es}/docs/api-reference.md`. WU1 hit it. |

## Tasks

- [ ] **WU1 — Story version summary (backend)**: `ExtractionRepository` aggregate read
  (`version_summaries(ids)`, plural — the batched-read convention `list_page` uses) + port read
  model `StoryVersionSummary` + `version_summary` on `UserStoryResponse` + projection in
  `list_stories`, `get_story`, `update_story` + backend tests + API-reference regeneration.
- [ ] **WU2 — Task version projection and `project_id` scope (backend)**: `TaskResponse` gains
  `extraction_id`/`version_number`; the list route resolves version numbers in one batched lookup;
  `TaskRepository.list_page` gains the `project_id` branch; the route accepts `project_id` with
  membership validation and refuses multiple scopes with 422; backend tests.
- [ ] **WU3 — Story card version badge (frontend)**: `StoriesList.tsx` renders `v{n} · current` /
  `v{n} · {status}` and the version count; `UserStory` type gains `versionSummary`; i18n keys;
  component tests.
- [ ] **WU4 — Kanban cascade filters (frontend)**: project → story → version selects, `taskStore`
  and `tasks-api` filter plumbing, filter-aware empty state; tests.
- [ ] **WU5 — Kanban version chip (frontend)**: `KanbanCard.tsx` shows the version of the task;
  tests.
- [ ] **WU6 — Specs and docs**: `openspec/specs/extraction-versioning/spec.md` (story version
  summary), `openspec/specs/kanban-board/spec.md` (filters, `project_id` scope, chip); closure of
  this document with commit evidence.

## Limits and follow-ups

- **Regenerating the API reference is part of any unit that changes a response schema.**
  `tests/test_api_reference.py` fails otherwise, and the generator writes outside the unit's own
  files; the worker must be given those two page paths in its allowed surfaces (recorded policy:
  ask first only when a render would touch a file outside that pair).
- The board's `size=100` cap is unchanged (D-non-goal) and is the reason the cascade is strict:
  project → story → version, with no workspace-wide story select.
- `version_summary` is projected on three read paths; a future write path that returns
  `UserStoryResponse` must project it too or answer `null` knowingly.
