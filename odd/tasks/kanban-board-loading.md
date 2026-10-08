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
| D3 | What the overlay covers | **Superseded in part by D6 (2026-10-08).** As first written: initial load, every filter-driven task refetch, the retry, and the cascade's own option reads (stories, versions). D6 keeps the first entry on the full veil and moves the other two cases to a per-select loader and a board-internal loader. |
| D4 | What the overlay does not cover | The no-workspace prompt (there is no read to wait for, and covering it would hide the instruction the user needs), and drag-and-drop status updates (that path is optimistic, shows a card-level spinner and reports failure by toast — a full-screen veil would fight the interaction it is meant to confirm). |
| D5 | Delay or debounce | **None.** The owner asked to see that it is loading; an artificial delay would hide it exactly when the response is fast. If the overlay turns out to flash on quick responses, adding a delay is a follow-up, not a part of this increment. |
| D6 | How many loading levels | **Owner's choice (2026-10-08): three, not one.** The full-viewport veil belongs to **entering the board** — the first read — and nothing else. Each select carries **its own loader** while its options are being read. The board shows an **internal loader** while the task read is in flight. A card moved inside the board raises **none** of them: it shows only its own in-flight state and must not interrupt the flow. |
| D7 | Whether a workspace switch is a first entry | **Yes.** The whole board context changes — every filter is cleared and every card is replaced — and the user has not seen this board yet, so it gets the full veil like an arrival. One line to reverse if it reads as too heavy; it is recorded as a decision rather than left to be inferred from the code. |
| D8 | Whether the internal loader covers the columns | **It replaces them, not floats over them.** Leaving the previous filter's cards on screen during a read presents stale data as the answer to the filter now in the bar — the same lie the version-badge rule and the empty-copy gate exist to prevent. The filter bar itself is never covered and never disabled: changing filters while a read is in flight is a supported interaction, and the store's staleness token already discards the answer that arrives out of order. |
| D9 | Which read each select loader reflects | One per select, from that select's own read: the project select from `projectStore.loading`, the story select from the stories read, the version select from the versions read. The point is that a pending read is attributable to the control that caused it, instead of all three sharing one global signal. |

## Non-goals

- No `board-index` endpoint and no other reduction in the number of requests (D1).
- No skeleton columns: the internal loader replaces the columns' content, it does not restructure the
  board.
- No change to what a select shows once loaded, and no change to the filter resolution.
- **No board-level loading for a card moved inside the board** (D6). That path is optimistic and
  local; the only thing it may show is the card's own in-flight state.

## Tasks

- [x] **WU7 — Board loading overlay (frontend)** → `702533f`. The veil moved to
  `LoadingVeil.tsx` (one accessible region, one z-index rationale, two consumers); `FullPageLoader`
  became the mutation-driven wrapper over it and its test passed unmodified. The board raises the
  same veil for all three of its reads — tasks, stories, versions — and `common.loading` supplies
  the copy, so no i18n key was added.
- [x] **WU8 — Spec delta and closure** → `1b15dd0`. `openspec/specs/kanban-board/spec.md` gained
  the read-feedback requirement (7 requirements and 18 scenarios → 8 and 24) and this document
  closed with the gate evidence below.
- [x] **WU9 — Three loading levels (frontend)** → `a67bb67`. Four levels in code and in comments:
  `seenWorkspace !== workspaceId` for the veil, per-select loaders from each read's own flag, an
  internal loader in place of the columns, and a card move raising none of it. Each select trigger
  also carries `aria-busy`. The three superseded WU7 tests were rewritten, and the review added the
  `aria-busy` assertions.
- [x] **WU10 — Spec delta and closure** → `a8578d7`. The read-feedback requirement now states the
  four levels (8 requirements, 6 → 8 scenarios, replacing rather than adding) and this document
  closed with the new evidence.

## Verified facts (with evidence)

| Fact | Evidence |
|------|----------|
| The inline spinner cannot fire on a refetch | `KanbanBoard.tsx:392` guards on `initialLoad && loading`, and only `reload()` raises `initialLoad` again |
| A mutation-driven full-page veil already exists and is deliberately mutation-only | `FullPageLoader.tsx:19-33`; `blocking-requests.ts` (reads never raise the store) |
| The cascade's reads are story and version lists with no loading state | `KanbanBoard.tsx:110-146` — both effects set options to `[]` first, then either fill or leave them empty on failure |
| The board's task read already exposes `loading` | `taskStore.ts` — `fetchTasksForWorkspace` claims `loading` for its own request and releases it guarded by the staleness token |
| **A card move already raises no board-level loading** | `taskStore.ts`'s `updateTaskStatus` never touches `loading`: it awaits the PUT, then patches `tasks`/`workspaceTasks` in place, and the board's `handleDragEnd` reverts with a local `setLocalTasks` on failure rather than a refetch. So D6's fourth level is a rule to preserve and pin, not a bug to fix. |
| **A loader fits inside the select control** | `ui/select.tsx:29-52` — `SelectTrigger` renders `{children}` and then its chevron, so a spinner can sit inside the trigger beside the value |
| **The project list already has its own loading flag** | `projectStore.ts:69,75,78` — `fetchProjects` claims and releases `loading`, so the project select needs no new state |

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
- **Two levels, two ARIA roles, and that is my call, not a measured fact.** The full veil is a
  `role="status"` live region (inherited from `LoadingVeil`); the internal loader is a
  `role="progressbar"` with an `aria-label`. Keeping them distinct lets assistive tech announce the
  two states differently, and it also lets every test tell them apart by role. If one role for both
  is preferred, aligning the internal loader to `role="status"` is a small follow-up — it would
  cost the tests that distinction.
- **The select spinners report `aria-busy` on the trigger**, added on review: an `aria-label` on a
  bare `<svg>` is ignored by several screen readers, and "this control is still loading" is a
  property of the control. The test pins `aria-busy="true"` while the read is pending and
  `"false"` after, which is also what proves React renders the attribute rather than dropping it.
- **The D7 test pins the behavior, not the mechanism.** A workspace switch would show a veil
  whether or not `seenWorkspace` had been set first, so the test cannot prove the flag did the
  work; the "never again for that workspace" test pins the flag's effect from the other side. The
  pair is what makes the mechanism credible, and neither alone would.
- **`seenWorkspace` resets per mount, not per session.** Navigating away from the board and back
  re-enters with the full veil. That matches "entering the board", and it is worth knowing before
  someone reads a remount's veil as a bug.
- **The `settled` gate now reads `!loading` alone**, because the cascade's reads no longer hide the
  board: while the stories or versions read is pending, the last settled board stays visible and
  the pending state lives in the select. The `loadedFiltersKey` half is unchanged and still pinned.

## Closure

Branch `feat/versioning-visibility`, on top of the `versioning-visibility` slice's nine commits.
Five commits for this increment:

| Commit | Unit |
|--------|------|
| `702533f` | WU7 — board loading veil, the first model |
| `1b15dd0` | WU8 — the spec delta for that model |
| `bfa6415` | WU8 — closure of the first model |
| `a67bb67` | WU9 — the three levels that replaced it (D6–D9) |
| `a8578d7` | WU10 — the spec rewritten for the three levels |

The closing commit for this document follows the five above and adds no behavior.

Gates, run by the orchestrator on the full tree after WU9 and after the review fix: `pnpm exec
tsc --noEmit` exit 0 and `npm test` **77 files / 874 tests** passing. `FullPageLoader`'s own test is
still unchanged and passing, which is what proves the veil extraction preserved the mutation veil's
rendering. No backend file was touched in this increment, so no backend gate was re-run for it.

### What the owner changed, and what that cost

WU7 shipped one model and WU9 shipped another, one day apart, and the honest accounting is that the
first model was over-broad rather than wrong: it answered "the board says nothing" and ignored that
a filter change is a refresh of one region, not an arrival. The rewrite was cheap in code and not
cheap in tests — three WU7 tests asserted the superseded contract and had to be rewritten, which is
the visible price of deciding a contract in code before deciding it with the person who lives in it.
They were rewritten rather than deleted so the change stays readable in the diff.
