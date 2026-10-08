# Kanban board loading visibility

> Increment of the `versioning-visibility` branch, 2026-10-08. Closes the visibility gap the
> cascade opened: the board reads data and never says so.

## Problem

WU4 gave the board a Project → Story → Version cascade and each level resolves server-side, which
means **every level change issues a request**. Three consequences, all observed in the code:

1. **The board's spinner only exists for the first load.** The guard is `initialLoad && loading`
   (`KanbanBoard.tsx:392-399`), and a refetch starts with `initialLoad` already false. So the
   filter change — the exact interaction the cascade introduced — shows **nothing** while it is in
   flight: the columns keep the previous filter's cards until the response lands and then swap.
2. **The cascade's own reads have no indicator at all.** Selecting a project starts
   `listStories(projectId, 1, 100, workspaceId)` and selecting a story starts
   `listVersions(storyId)`. Until each lands, its select renders empty — an empty select and a
   loading select look identical.
3. **The retry sets `initialLoad` back to true on purpose** (`reload()`), which is the one path that
   does show the spinner; it is the exception, not the rule.

## Decisions

| #  | Decision | Choice |
|----|----------|--------|
| D1 | A preload endpoint for the selects | **Owner's choice (2026-10-08): no.** A `board-index` endpoint returning projects, stories and every version of the workspace was offered and rejected: "es mucho cuando el proyecto escale". The per-selection reads stay, and the fix is visibility instead. Recorded because the alternative is the obvious next idea and it was declined knowingly, not overlooked. |
| D2 | Which loading mechanism | **A board-scoped overlay, never the global `useLoadingStore`.** `FullPageLoader.tsx` is raised only by mutations, and `blocking-requests.ts` documents that reads never raise it; a board read must not hijack the veil that other surfaces rely on to mean "a write is in flight". The veil's markup is extracted into one presentational component so the two consumers cannot drift. |
| D3 | What the overlay covers | Initial load, every filter-driven task refetch, the retry, **and the cascade's own option reads** (stories, versions). The last one is the point: an empty select with no indicator is the silent state that motivated this increment. |
| D4 | What the overlay does not cover | The no-workspace prompt (there is no read to wait for, and covering it would hide the instruction the user needs), and drag-and-drop status updates (that path is optimistic, shows a card-level spinner and reports failure by toast — a full-screen veil would fight the interaction it is meant to confirm). |
| D5 | Delay or debounce | **None.** The owner asked to see that it is loading; an artificial delay would hide it exactly when the response is fast. If the overlay turns out to flash on quick responses, adding a delay is a follow-up, not a part of this increment. |

## Non-goals

- No `board-index` endpoint and no other reduction in the number of requests (D1).
- No skeleton columns: the overlay replaces the inline spinner, it does not restructure the board.
- No change to what a select shows once loaded, and no change to the filter resolution.

## Tasks

- [x] **WU7 — Board loading overlay (frontend)** → `702533f`. The veil moved to
  `LoadingVeil.tsx` (one accessible region, one z-index rationale, two consumers); `FullPageLoader`
  became the mutation-driven wrapper over it and its test passed unmodified. The board raises the
  same veil for all three of its reads — tasks, stories, versions — and `common.loading` supplies
  the copy, so no i18n key was added.
- [x] **WU8 — Spec delta and closure** → `1b15dd0`. `openspec/specs/kanban-board/spec.md` gained
  the read-feedback requirement (7 requirements and 18 scenarios → 8 and 24) and this document
  closed with the gate evidence below.

## Verified facts (with evidence)

| Fact | Evidence |
|------|----------|
| The inline spinner cannot fire on a refetch | `KanbanBoard.tsx:392` guards on `initialLoad && loading`, and only `reload()` raises `initialLoad` again |
| A mutation-driven full-page veil already exists and is deliberately mutation-only | `FullPageLoader.tsx:19-33`; `blocking-requests.ts` (reads never raise the store) |
| The cascade's reads are story and version lists with no loading state | `KanbanBoard.tsx:110-146` — both effects set options to `[]` first, then either fill or leave them empty on failure |
| The board's task read already exposes `loading` | `taskStore.ts` — `fetchTasksForWorkspace` claims `loading` for its own request and releases it guarded by the staleness token |

## Limits and follow-ups

- **A fast API makes the overlay a flash.** Accepted by decision D5. If it proves annoying in use,
  a delay of a few hundred milliseconds before showing the veil (while keeping it immediate after
  that) is the standard fix and a small follow-up.
- **The number of requests per level change is unchanged**: selecting a project costs the stories
  read plus the tasks read, selecting a story costs the versions read plus the tasks read. That is
  the accepted cost of D1.
- **The empty-copy gate has two halves and only one of them is pinned by a test.** The worker's
  suite pins the in-flight half ("does not paint the empty-board copy while a read is in flight").
  The other half — the frame between a filter change and the effect that starts the read, where
  nothing is in flight yet and `workspaceTasks` is still the previous answer — is closed by
  `loadedFiltersKey` (an empty board is only called empty once a read has settled *for the filters
  the bar shows*). That frame cannot be observed from a test: React flushes effects inside `act`
  before an assertion can see it. The flag is therefore reasoned rather than pinned, and it is
  four lines with its rationale next to it. Stated here so nobody reads the suite as covering it.
- **The board's veil and the mutation veil are two states with one look.** If a read and a write
  are ever in flight together, they render the same markup and the same copy family
  (`common.loading` / `common.processing`), so the pair reads as one indicator. That is intended
  (one visual language) but it does mean the two are indistinguishable on screen.

## Closure

Branch `feat/versioning-visibility`, on top of the `versioning-visibility` slice's nine commits.
Two commits for this increment:

| Commit | Unit |
|--------|------|
| `702533f` | WU7 — board loading veil (and the `loadedFiltersKey` gate) |
| `1b15dd0` | WU8 — the spec delta |

The closing commit for this document follows the two above and adds no behavior.

Gates, run by the orchestrator on the full tree: `pnpm exec tsc --noEmit` exit 0, `npm test`
**77 files / 871 tests** passing (9 of them new), and `FullPageLoader`'s own test unchanged and
passing, which is what proves the extraction preserved the mutation veil's rendering. No backend
file was touched, so no backend gate was re-run for this increment.
