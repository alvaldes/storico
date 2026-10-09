# Kanban cards name their project and their story

> Increment of the `versioning-visibility` branch, 2026-10-08. Requested by the owner after using the
> board: a card says which version it belongs to and nothing about where it came from.

## Problem

The board mixes every project of the workspace into one set of columns, and un-filtered there is no
way to tell where a card came from. The card shows a title, a description, its labels and its
version chip — never the project or the story.

Two facts shape the work:

- **The story id is already on the card's data.** `TaskResponse.user_story_id` has been there all
  along, and the card already uses it as the title's link target. Nothing new is needed to name the
  story.
- **The project is not reachable from a task.** `TaskResponse` carries no `project_id`, and the
  frontend cannot derive one: it holds the workspace's projects (`projectStore`) but no task →
  story → project link, and the cascade only loads the stories of the *selected* project — never
  the ones the unfiltered board needs.

## Decisions

| #  | Decision | Choice |
|----|----------|--------|
| D12 | How the card names the story | **Owner's choice (2026-10-08): the story's short id, as the story cards already show it** (`shortUUID`, the first 8 characters). Chosen over `actor: feature` (the cascade's label) and over the story's sentence, because it is the shortest thing that identifies a story and the app already uses it for exactly this. |
| D13 | How the card names the project | The project's **name**, as text. Not a link: the card already has one click target (the title, which goes to the story), and a second link inside a draggable card is a mis-click waiting to happen. |
| D14 | Where the project name comes from | **A batched read in the tasks route, one statement per page**, following the `version_numbers` precedent (D8 of `versioning-visibility`): resolve the page's distinct story ids to their project label in one join, rather than a per-task lookup or a frontend join. The frontend cannot do it: see the second verified fact above. |
| D15 | How the chips sit in the UI | Owner's requirement: they must blend with the existing badges. So the same `outline` variant and the same sizing classes as the label and version chips, muted like the version chip, ordered **project → story → labels → version**. The labels keep the foreground colour because they are the task's own attributes; the three context chips are the "where". **The order is superseded by D20 of `kanban-context-tooltips`:** the owner moved the labels last the same day, so the row now leads with project → story → version. Everything else in this row stands. |

## Non-goals

- No new endpoint: the projection rides on the task reads that already exist.
- No change to the cascade, the filters, or the version chip.
- No linking of the two new chips (D13), and no per-project colour coding.
- **No change to `shortUUID` itself** — see the limit below.

## Tasks

- [x] **WU13 — Project label projection (backend)** → `dbbfab8`: a batched story → project label read on the
  story repository, `TaskResponse.project_id`/`project_name`, projection on every construction site
  in the tasks route, tests including the one-statement pin, and API-reference regeneration.
- [x] **WU14 — Card chips (frontend)** → `b69d770`: `Task`/`mapTaskItem` carry the two fields, `KanbanCard`
  renders the project and story chips in the agreed order and styling, tests for present, absent and
  truncated cases.
- [x] **WU15 — Spec delta and closure** → `654330e` plus this document's closing commit: `openspec/specs/kanban-board/spec.md` gains the requirement
  for what a card names; closure of this document with the evidence.

## Verified facts (with evidence)

| Fact | Evidence |
|------|----------|
| The story id already reaches the card | `TaskResponse.user_story_id`; `KanbanCard.tsx` links the title to `/{locale}/stories/${task.storyId}` |
| The project does not reach the card | `TaskResponse` has no project field (`api/schemas/task.py`); `task → story → project` is the only path |
| The route already has what a join needs | `list_tasks` injects `story_repo` and `project_repo` (`api/routes/tasks.py`), so no new dependency wiring |
| The join is a single indexed hop on both legs | `user_stories.project_id` (FK + `ix_user_stories_project_id`), `projects.id` (PK) |
| Nothing pins `shortUUID`'s output | No test in `frontend/src` asserts a short id, so its format is free to change later (see the limit below) |

## Limits and follow-ups

- **`shortUUID` takes the *first* 8 characters, and these are uuid7s — time-ordered.** The leading
  bits are a timestamp, so stories created in the same session share a long prefix: in the dev
  workspace the story `01a10dee-6d92-7d13-812f-bc39dfd8e767` shortens to `01a10dee`, while the
  workspace id next to it is `01a103f8`. Two stories created a minute apart read `01a10dee` and
  `01a10df1`: six identical characters, and the distinguishing ones are the last two. The chip works
  for the common case of a handful of stories and degrades exactly when a project has many; the
  owner chose it for consistency with the story cards, and this note exists so the collision is a
  known property rather than a later surprise. Changing the function to a distinguishing slice would
  fix every surface at once (`StoriesList`, `StoryDetail`, `AutoBreadcrumb`) and no test pins its
  output, which is why it is a small follow-up rather than a large one.
- **The card grows a row.** Three context chips plus the task's labels is a lot in a ~260 px column;
  if it reads as crowded, the labels are the ones to move (they are the task's own attributes and the
  least about *where* the card is).
- **`project_name` can be renamed out from under a card.** It is a label, not an identity; the id
  next to it in the same row is what a future grouping or link would use.

## Closure

Branch `feat/versioning-visibility`, on top of the loading increment's nine commits.

| Commit | Unit |
|--------|------|
| `dbbfab8` | WU13 — one batched story → project read, projected on every task read |
| `b69d770` | WU14 — the two context chips on the card |
| `654330e` | WU15 — the kanban requirement, the task-read amendment, and the API-reference correction |

Gates, run by the orchestrator on the full tree: backend `ruff check` clean, `ruff format --check`
clean, `python -m pytest -q` **1339 passed, 45 skipped** (the same 45 environment skips as always:
Docker, `STORICO_TEST_LIVE_QDRANT`, `STORICO_TEST_LIVE_OLLAMA`); frontend `pnpm exec tsc --noEmit`
exit 0 and `npm test` **77 files / 882 tests**.

### Verified in the browser

ego-browser, `/en/kanban` against the dev stack, with the real workspace:

- The payload carries the fields: `project_id: "01a10443…"`, `project_name: "Version Test"` on every
  task, next to `version_number: 5`.
- Each card's metadata row reads `Version Test` · `01a10dee` · its labels · `v5`, in that order, with
  the context chips visibly dimmer than the labels — the "blend" the owner asked for, confirmed by
  screenshot rather than by reading the classes.

Two honest limits of that verification:

- **The dev data cannot show the chips distinguishing anything.** All seven tasks in this workspace
  belong to one story, so every card carries the same story chip and the same project name. The
  chip's usefulness is argued from the design, not demonstrated by this data.
- **The long-name ellipsis is verified structurally only** (`max-w-[10rem]`, a `min-w-0 truncate`
  span, the `title` attribute), because jsdom does no layout and the only project in the dev
  workspace has a short name. Not pixel-verified; worth one look the next time a long project name
  exists.
