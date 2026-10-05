# ODD Feature: invalid-flag-and-version-refresh

> **Status**: complete and verified — T1–T3 implemented, gated and committed on the branch
> (`4d96f03`, `b487ee5`, `1193f1d`, plus `1a52049` for the port pin and the formatter pass,
> `b07b325` for the evidence record, and `a2a9cdc` for the verification's one accepted finding).
> Pushing, the PR and the merge are the owner's decisions.
> **Created**: 2026-10-05
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: stacked on the current `chore/issue-forms` (owner's choice, asked and answered
> before the first write — the working tree also carries the owner's own uncommitted edits to
> `StatusPanel.tsx` / `PublicLayout.astro` / `astro.config.mjs`, which this slice does not touch).
> **Receipt-driven development**: **off** in this clone — `gentle-ai review mode status` read on
> 2026-10-05: `receipt-driven development: off (decided by clone_local)`, global `on`, clone-local
> `off`. No native review lineage was started, and none was expected; the gate is an independent
> verification over the committed range, the same shape `task-control-copy-truth` used.
> **TDD**: `strict_tdd: true` in `openspec/config.yaml`. Both halves are behaviour changes with
> runnable deterministic tests, so every task observed RED before GREEN.

## Problem

Two user-reported defects, both of the same class: **the screen keeps a stale answer because
nothing re-reads it**.

1. **The card's invalid flag never reflects the mark.** A story-detail task card renders a
   `Flag` control (`StoryDetail.tsx`, `t.stories.mark_invalid`) that opens the editor where the
   owner can mark the task invalid. Nothing on the page ever shows that a task *is* marked: the
   card reads `Task` (`types/task.ts`), the task list response carries no mark state
   (`TaskResponse`), and the only mark read is per-task and only happens when the editor opens
   (`listInvalidations(editingTaskId)`). So marking a task invalid changes the record and nothing
   on screen — the owner's words: *"no se está actualizando la flag de invalid task al registrar
   una task como invalid."* The owner confirmed the surface: **the flag on the task card**.

2. **The version selector does not appear or update until a page reload.** `extractTasks`
   POSTs, polls, and on completion refreshes `fetchTasks`, `fetchTasksForWorkspace` and
   `fetchStory` — but never `fetchVersions`. The pending row that the 202 body already names
   (`ExtractResponse.version_number`) is discarded by `startExtraction`, and the selector only
   renders once `versions.length > 0`. Owner's words: *"no se está mostrando la versión de la
   extracción… lo que sí no puede pasar es que yo tenga que refrescar la página para ver la
   versión y el combobox."* Owner's chosen mechanism: **reuse the polling that already exists —
   refresh versions when the run starts and when it settles — no SSE channel.**

## Decisions

| # | Decision | Choice |
|---|----------|--------|
| D1 | Where the card's flag state comes from | **A story-scoped read of the active marks**, not a flag bolted onto every `TaskResponse`. The mark is not a task column; it lives in its own table with its own history. A new `GET /api/v1/stories/{story_id}/invalidations` returns the story's active marks (task id + reason + timestamp), the selector intersects them with the displayed tasks, and the mark endpoints keep their single-writer ownership. Chosen over adding `has_active_invalidation` to `TaskResponse` because that would force every `TaskResponse` construction site (`get_task`, `update_task`, export) to either pay an extra statement on the slow dev pooler or return a default `False` that is a **lie** — and a lie that the store would then merge over a true local flag after a PUT. |
| D2 | Read scope and gate | Story-scoped, **membership-only** — the same `require_story_workspace_access` walk as `GET /{story_id}/versions`, and the same posture the marks reads already have (every member reads marks; only owner/admin mutates). The read is unpaginated like the versions read: the list is an input, not a page. |
| D3 | Immediate update without a refetch | The editor already owns the confirmed mark write; it gains one optional callback prop (`onInvalidationChange`) called **after** the mark write succeeds. The page flips the task's flag from that, so a save needs no re-read. The callback fires even when the following PUT fails: the mark exists server-side regardless of the PUT, and a dialog error must not hide a real mark. |
| D4 | Faithful failure posture | A failed story-marks read leaves the flags unmarked (the read is a courtesy, the server is the authority — same posture as a failed `listInvalidations` today) and never blocks the page. |
| D5 | Version refresh trigger | Inside the store, at the two points that already own the lifecycle: **after the POST succeeds** (the row is born `pending` before the 202 returns, so the version exists) and in the **completed and failed** poll branches (a failed run keeps its consumed number and row and must show up). Both are fire-and-forget: `fetchVersions` already records its own failure and never rejects. |
| D6 | Following the minted version | `ExtractionState` carries the `version_number` the 202 already returns; the page selects the version whose number matches, as soon as it appears in the history. That satisfies "show it even while it is not finished" **and** hands the user the new current version when it settles, with no reload. `getExtractionStatus` is extended with the same scalar so the poll's terminal writes preserve it. |
| D7 | A pending version must not read as "no output" | The tasks area's `selectedVersion && !hasOutput` branch currently renders the failed-version card. A `pending` selected version is not a failed one: the pending panel (already written for `extraction.status === 'pending'`) moves ahead of that branch, so the run in progress reads as progress rather than as an empty result. |
| D8 | Spanish copy | Neutral international Spanish (ADR-008), `tú`, no voseo, in both catalogs with identical key sets. |

## Non-goals

- No SSE/WebSocket channel (owner chose the polling refresh).
- No new backend field on `TaskResponse`, `Task` (domain) or the task list statement.
- No Kanban/export flag rendering; the `Flag` control exists only on the story-detail card.
- No change to who may mark (owner/admin) or to the mark endpoints' contracts.
- No touching the owner's in-flight files (`StatusPanel.tsx`, `PublicLayout.astro`,
  `astro.config.mjs`).

## Tasks

### T1 — Backend: the story's active marks are readable

- **Status**: done — `4d96f03`, pin/format follow-up `1a52049`
- **What**: `TaskInvalidationRepository.list_active_for_story(user_story_id)` (port + SQLAlchemy
  implementation, one join `task_invalidations → tasks` filtered by `tasks.user_story_id` and
  `revoked_at IS NULL`, ordered `marked_at DESC`); `StoryInvalidationResponse` (the mark plus its
  `task_id`); `GET /api/v1/stories/{story_id}/invalidations` under the existing stories router,
  membership-gated, bare unpaginated array.
- **Acceptance**: a membership read returns exactly the story's active marks, revoked marks never
  appear, another story's marks never appear, a non-member is refused, and no write path changed.

### T2 — Frontend: the card flag reflects the mark, live

- **Status**: done — `b487ee5`
- **What**: `listStoryInvalidations(storyId)` in `versioning-api.ts` + types;
  `StoryDetail` reads it once per story into a `Set<taskId>`, renders the card's `Flag`
  as marked (`aria-pressed`, filled/destructive icon; the accessible label stays
  `stories.mark_invalid`, so the toggle's state is what changes, not its name) when the displayed
  task has an active mark, and passes `TaskEditor` the `onInvalidationChange` callback that flips
  the set after a confirmed mark/unmark.
- **Acceptance**: a marked task's card shows the marked flag on load; marking then saving flips
  it with **zero** further reads; unmarking flips it back; a member still sees no mark control;
  a failed story-marks read leaves the card unmarked and does not block.

### T3 — Frontend: the version appears and follows the run

- **Status**: done — `1193f1d`
- **What**: `startExtraction` returns `versionNumber`; `ExtractionState` carries it (and
  `getExtractionStatus` reports it); the store refreshes versions after the POST and in the
  completed/failed poll branches; `StoryDetail` selects the version whose number matches the run
  it started, and a pending selected version renders the in-progress panel instead of the
  "no output" card.
- **Acceptance**: after a first extraction the selector appears and holds the pending version
  while the panel shows progress; on completion the same version becomes current and its tasks
  render, with no reload; a failed run appears in the selector with its error; no version refresh
  is issued on a failed POST.

### T4 — Gate

- **Status**: done — this commit
- **Commands** (from the repo root / the right directory):
  - `cd backend && conda run -n storico python -m ruff check src tests`
  - `cd backend && conda run -n storico python -m pytest -m "not integration" -q`
  - `cd frontend && node_modules/.bin/vitest run`
  - `cd frontend && node_modules/.bin/tsc --noEmit`
  - `cd frontend && node_modules/.bin/astro build`
- **Acceptance**: all green, with the counts recorded. The Docker-gated backend integration
  cases are named as CI-only evidence, never claimed locally (no Docker daemon on this machine).

## Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| The new story read adds a request per page | Slower story page on the dev pooler | One statement, membership-gated, fire-and-forget, and it is the flag's only source; the page already issues several reads |
| The local flip and the server disagree | A card showing a mark that does not exist | The flip only runs after a confirmed write; the next page load re-reads the server's truth |
| Auto-selecting the minted version yanks a manual selection | The user loses the version they were inspecting | Only a versions-refresh re-runs the effect, and the refresh is tied to the run the user started; a manual pick between refreshes sticks |
| Touching the shared `ExtractionState` shape | Compile ripple through fixtures | The field is added once and every construction site is updated; the typecheck is the gate |

## Evidence log

_(no row is written before its command has actually run)_

| Task | Commit | Outcome |
|------|--------|---------|
| T1 | `4d96f03` (follow-up `1a52049`) | `list_active_for_story` on the port + SQLAlchemy; `StoryInvalidationResponse` (mark + `task_id`); `GET /api/v1/stories/{story_id}/invalidations`, membership-gated, bare array. Observed RED first: the repository test failed with `AttributeError: ... has no attribute 'list_active_for_story'` and the three API cases answered 404 (route absent). GREEN: repository scope case + three API cases, 148 passed across `test_stories.py` / `test_task_invalidation.py` / `test_tasks.py`; ruff clean. `1a52049` adds the port-surface pin's eighth method (the pin failed on the full suite — 1 failed, 1285 passed) and the `ruff format` pass over the new test class. |
| T2 | `b487ee5` | `listStoryInvalidations` + types; the story-marks read and the `Set<taskId>` state; the card flag's pressed/filled/destructive state; `TaskEditor.onInvalidationChange` after a confirmed mark write (before the PUT). Observed RED first: 5 new cases failed (the API path/mapping, the card pressed/unpressed, the no-refetch flip, and both editor callbacks). GREEN: the three focused files 60/60; full frontend suite green except the pre-existing `status-probes-mirror` failure named below; `tsc --noEmit` clean. |
| T3 | `1193f1d` | `startExtraction` returns the 202's `version_number`; `ExtractionState.versionNumber` survives every terminal write; the store refreshes the history after the POST and in the completed/failed poll branches; `StoryDetail` selects the minted version and renders the pending panel instead of the no-output card. Observed RED first: 7 new cases failed (two API mappings, four store lifecycle cases, the pending-version case). GREEN: the three focused files 72/72; `tsc --noEmit` clean. |
| T4 | this commit | Gate, run from the right directories. **Backend:** `ruff check src tests` → `All checks passed!`; `ruff format --check src tests` → 272 files already formatted; `pytest -m "not integration" -q` → **1286 passed, 45 deselected** (the only warnings are the pre-existing Starlette 422 deprecation warnings; the count drifts between 5 and 6 across runs). **Frontend:** `vitest run` → **57 files passed, 1 failed; 682 tests passed, 1 failed**; `tsc --noEmit` → no output; `astro build` → `Complete!`. The single failure is named and pre-existing (see below). |

### The one failing test, and why it is not this candidate's

`frontend/src/lib/__tests__/status-probes-mirror.test.ts` → `has copy for every row in both locales`
fails with *"the status panel declares the serviceRows array"*. It reads
`frontend/src/components/react/StatusPanel.tsx` and matches the declared array with
`/const serviceRows: [\s\S]*?= \[([\s\S]*?)\n\];/`. Measured both ways on this machine: the regex
matches the file at `HEAD` and **does not** match the working-tree file, which the owner was
typing during this session (`StatusPanel.tsx`, mtime 13:54; `PublicLayout.astro`, 13:58). It is the
owner's in-flight edit, untouched by this slice — no file this slice writes is involved.

The Docker-gated Postgres integration cases were not run locally: there is no Docker daemon on
this machine (`AGENTS.md` records the same). They are CI-only evidence and are not claimed here.

## Verification

Independent `gentle-ai-verify` run over `7afd020..HEAD` (RDD is off in this clone, so this is
that run and not a native review). It re-derived the gate (**1286 passed / 45 deselected**,
ruf clean, **682 passed / 1 failed** on the frontend, `tsc` clean), independently confirmed the
single frontend failure is the owner's in-flight `StatusPanel.tsx` edit (regex matches `HEAD`,
not the worktree; the range touches neither file), and returned the verdict that **both reported
defects are fixed**. Its findings and their disposition:

- **F1 — the transient window after the POST while the history refreshes.** Recorded with a
  correction rather than accepted: the claim that the in-progress panel "rendered for the whole
  run before this range" is true only when the story had no tasks to show. `git show
  7afd020:…/StoryDetail.tsx` puts the pending panel in the final `else`, reached only when
  `storyTasks.length === 0`; with existing tasks the old code showed **the same stale tasks**
  this range shows. So the window is pre-existing behaviour, not candidate-caused, and no
  behaviour change was smuggled in to "fix" it. It is one version-refresh round-trip, and the
  pending version takes the selector as soon as the read lands. Optimistically inserting the row
  from the 202 would close it and would have to invent `created_at`/`model_used`; declined.
- **F2 — the version refresh could repopulate a discarded workspace's slice.** Accepted and fixed:
  `storyStore.fetchVersions` now samples the scope before its request and compares it after it,
  dropping both the success and failure writes when the scope moved — the only place the guard can
  actually close the post-`await` window (a call-site check cannot). Covered by a new
  `storyStore.unit.test.ts` case.
- **F3 — the ODD doc said "distinct localized label" where no i18n key exists.** Accepted as doc
  drift and corrected: the accessible signal is `aria-pressed` plus the filled/destructive icon,
  with the label deliberately constant so the toggle's name does not change under the user.
- **F4 — a duplicated section comment.** Accepted and removed.
- **L4 — the warning count in this doc.** Corrected; the count drifts run to run.

Its untested-edge list is real and is recorded rather than papered over: PUT-failure-after-mark,
a failed story-marks read, a revoke from the story page, and a first-ever extraction with no prior
version have no test. The behaviour is covered end-to-end only by the cases this slice added; each
named edge is a candidate for a follow-up if it ever regresses.

**Follow-up confirmation (`a2a9cdc`).** The same verifier re-checked the remediation read-only and
confirmed: the F2 guard sits on **both** the success and the failure write and stays fail-open while
no switch has been observed (`workspace-scope.ts`'s comparison holds with two `undefined`s); the new
`storyStore` case has teeth (with the guard removed the write lands and the assertion fails);
`git diff --stat b07b325..a2a9cdc` touches only the four intended files, none of them the owner's;
and **F1 is retracted by its author** — `git show 7afd020:…/StoryDetail.tsx` puts the pending panel
in the final `else`, reachable only when `storyTasks.length === 0`, so the window is pre-existing and
not a regression. Verdict: F2 closed, nothing changes the finding that both reported defects are
fixed.

## Non-goals confirmed, not silently dropped

- The card flag keeps its existing owner/admin and non-frozen gate: a marked task on a **frozen**
  version still shows no flag, because the control that would show it is hidden there. That is the
  pre-existing gate, unchanged; surfacing the mark on frozen cards is a separate decision.
- The Kanban board and the export do not render the flag; the `Flag` control exists only on the
  story-detail card.
