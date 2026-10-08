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
| D6 | How many loading levels | **Owner's choice (2026-10-08): three, not one.** The full-viewport veil belongs to **entering the board** — the first read — and nothing else. Each select carries **its own loader** while its options are being read. The board shows an **internal loader** while the task read is in flight. A card moved inside the board raises **none** of them: it shows only its own in-flight state and must not interrupt the flow. **Its first level and D7 are superseded the same day by D10:** the board never raises the veil, not even on entry. The other three levels stand and are what shipped. |
| D7 | Whether a workspace switch is a first entry | **Superseded by D10.** As decided: yes, the full veil. Once the board stopped raising the veil at all, the question dissolved — a workspace switch is now an internal-loader read like any other. Kept here because the owner reversed it deliberately, and a reader deserves to know the reversal was considered rather than never asked. |
| D8 | Whether the internal loader covers the columns | **It replaces them, not floats over them.** Leaving the previous filter's cards on screen during a read presents stale data as the answer to the filter now in the bar — the same lie the version-badge rule and the empty-copy gate exist to prevent. The filter bar itself is never covered and never disabled: changing filters while a read is in flight is a supported interaction, and the store's staleness token already discards the answer that arrives out of order. |
| D9 | Which read each select loader reflects | One per select, from that select's own read: the project select from `projectStore.loading`, the story select from the stories read, the version select from the versions read. The point is that a pending read is attributable to the control that caused it, instead of all three sharing one global signal. |
| D10 | Whether the board ever raises the full veil | **Owner's choice (2026-10-08), reversing D6's first level and D7: no.** Opening `/kanban` shows the internal loader in the columns area, exactly like every other board read. The full-viewport veil belongs to mutations, which is the only thing it ever meant. `seenWorkspace` and the failed-first-read exception went with it: a board read is a board read, and the retry is no longer special. |
| D11 | Whether a card move raises the mutation veil | **Owner's report (2026-10-08), reproduced and fixed: it must not.** `PUT /api/v1/tasks/{id}` joins `BLOCKING_EXCLUSIONS` in `blocking-requests.ts`. The drop is optimistic, the card already carries its own in-flight indicator, and a page-wide overlay interrupts the very gesture it is meant to confirm — the same reasoning the extraction exclusion already uses (the surface owns its pending UI). |

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
  the copy, so no i18n key was added. **(Superseded by WU11: the board raises no veil at all.)**
- [x] **WU8 — Spec delta and closure** → `1b15dd0`. `openspec/specs/kanban-board/spec.md` gained
  the read-feedback requirement (7 requirements and 18 scenarios → 8 and 24) and this document
  closed with the gate evidence below.
- [x] **WU9 — Three loading levels (frontend)** → `a67bb67`. Four levels in code and in comments:
  `seenWorkspace !== workspaceId` for the veil, per-select loaders from each read's own flag, an
  internal loader in place of the columns, and a card move raising none of it. Each select trigger
  also carries `aria-busy`. The three superseded WU7 tests were rewritten, and the review added the
  `aria-busy` assertions. **(Its veil level is superseded by WU11; the per-select loaders and the
  internal loader are what shipped.)**
- [x] **WU10 — Spec delta and closure** → `a8578d7`. The read-feedback requirement now states the
  four levels (8 requirements, 6 → 8 scenarios, replacing rather than adding) and this document
  closed with the new evidence.
- [x] **WU11 — The board never veils, and a card move never blocks (frontend)** → `129c382`
  (D10) and `16fc6f3` (D11). The board's loader condition is `loading` alone, `seenWorkspace` and
  the failed-first-read exception are gone, and `PUT /api/v1/tasks/{id}` is the fourth
  `BLOCKING_EXCLUSIONS` entry with its `why`. Two disjoint file sets, committed separately.
- [x] **WU12 — Spec delta and closure** → `e61e2f9` plus the closing commit of this document. The
  read-feedback requirement lost its entry level and gained the exemption rule with its bound
  (8 requirements, 24 → 26 scenarios across the two rewrites of this block).

## Verified facts (with evidence)

| Fact | Evidence |
|------|----------|
| The inline spinner could not fire on a refetch | **Historical —** the guard was `initialLoad && loading` and only `reload()` raised `initialLoad`. WU11 deleted both the spinner branch and `initialLoad`: that guard is what made a refetch silent, and it is gone rather than fixed. |
| A mutation-driven full-page veil exists and is deliberately mutation-only | `FullPageLoader.tsx`; `blocking-requests.ts` (reads never raise the store); `FullPageLoader`'s own test passes unchanged after the `LoadingVeil` extraction |
| The cascade's reads carry their own pending flags | `KanbanBoard.tsx` — the stories effect holds `storiesLoading` and the versions effect `versionsLoading` for the duration of their reads; each select renders its own spinner from its own flag |
| The board's task read already exposes `loading` | `taskStore.ts` — `fetchTasksForWorkspace` claims `loading` for its own request and releases it guarded by the staleness token |
| **A card move already raises no board-level loading** | `taskStore.ts`'s `updateTaskStatus` never touches `loading`: it awaits the PUT, then patches `tasks`/`workspaceTasks` in place, and the board's `handleDragEnd` reverts with a local `setLocalTasks` on failure rather than a refetch. So D6's fourth level is a rule to preserve and pin, not a bug to fix. |
| **A loader fits inside the select control** | `ui/select.tsx:29-52` — `SelectTrigger` renders `{children}` and then its chevron, so a spinner can sit inside the trigger beside the value |
| **The project list already has its own loading flag** | `projectStore.ts:69,75,78` — `fetchProjects` claims and releases `loading`, so the project select needs no new state |
| **The board's entry veil was a real, visible behavior** | ego-browser, `http://localhost:4321/en/kanban`, dev stack on `:4321` + `:8000`: `waitForSelector('div[role="status"]')` catches `Loading...` with class `fixed inset-0 z-[60] …` while the first read is in flight |
| **A card move does take the blocking path (D11)** | ego-browser, in the running app: `import('/src/lib/blocking-requests.ts')` → `shouldBlockRequest('PUT', '/api/v1/tasks/<uuid>') === true`, while `shouldBlockRequest('GET', '/api/v1/tasks/?…') === false`; and a `MutationObserver` recorded the `Processing...` veil appearing during a real card drag |
| **A local backend hides that veil, and why** | The same drag on `localhost` sometimes rose the veil and sometimes did not: the loader only appears after `BLOCKING_LOADER_DELAY_MS` (250 ms, `loadingStore.ts`) and a local PUT often beats it. Against Supabase's pooler (seconds) it is reliably visible, which is the latency the owner sees. Recorded so a future reviewer on a fast stack does not conclude the bug is gone. |

## Limits and follow-ups

- **The internal loader can flash.** Accepted by D5. If it proves annoying in use, a delay of a few
  hundred milliseconds before showing it (immediate after that) is the standard fix and a small
  follow-up. The mutation veil already has that delay and a minimum-visible floor; the board's
  loader deliberately has neither.
- **The number of requests per level change is unchanged**: selecting a project costs the stories
  read plus the tasks read, selecting a story costs the versions read plus the tasks read. That is
  the accepted cost of D1 — the owner weighed a preload endpoint against it and chose the reads.
- **The empty-copy gate has two halves and only one of them is pinned by a test.** The suite pins
  the in-flight half ("does not paint the empty-board copy while a read is in flight"). The other
  half — the frame between a filter change and the effect that starts the read, where nothing is in
  flight yet and `workspaceTasks` is still the previous answer — is closed by `loadedFiltersKey` (an
  empty board is only called empty once a read has settled *for the filters the bar shows*). That
  frame cannot be observed from a test: React flushes effects inside `act` before an assertion can
  see it. The flag is therefore reasoned rather than pinned, and it is four lines with its rationale
  next to it. Stated here so nobody reads the suite as covering it.
- **The never-veil tests are absence assertions, and they carry a positive control.** "No
  `role="status"`" would also pass on a board that rendered nothing at all, so each of them also
  asserts the internal loader appears and settles. Worth knowing before someone simplifies those
  tests by dropping the control.
- **The board's loader and the mutation veil now differ in kind, not only in size.** The board's is a
  `role="progressbar"` in the columns area with `common.loading`; the mutation veil is a
  `role="status"` live region covering the viewport with `common.processing`. Two roles rather than
  one is my call, not a measured fact: it lets assistive tech announce an in-page refresh and a
  blocked page differently, and it is what lets every test tell them apart. Unifying them is a small
  follow-up that would cost the tests that distinction.
- **The select spinners report `aria-busy` on the trigger**, added on review: an `aria-label` on a
  bare `<svg>` is ignored by several screen readers, and "this control is still loading" is a
  property of the control. The test pins `aria-busy="true"` while the read is pending and `"false"`
  after, which is also what proves React renders the attribute rather than dropping it.
- **The `settled` gate reads `!loading` alone**, because the cascade's reads no longer hide the
  board: while the stories or versions read is pending, the last settled board stays visible and the
  pending state lives in the select. The `loadedFiltersKey` half is unchanged and still pinned.
- **The task exemption is path-scoped and method-agnostic**, like the three entries before it. Any
  hypothetical non-PUT write to `/api/v1/tasks/{id}` would also be exempt. That is the convention
  the onboarding entry already documents (`lib/user-api.ts` calls its path with PATCH), and it is
  recorded here so a future reader does not read the exemption as PUT-specific.

## Closure

Branch `feat/versioning-visibility`, on top of the `versioning-visibility` slice's nine commits.
Nine commits for this increment:

| Commit | Unit |
|--------|------|
| `702533f` | WU7 — board loading veil, the first model |
| `1b15dd0` | WU8 — the spec delta for that model |
| `bfa6415` | WU8 — closure of the first model |
| `a67bb67` | WU9 — the three levels that replaced it (D6–D9) |
| `a8578d7` | WU10 — the spec rewritten for the three levels |
| `c757f36` | WU10 — closure of the three levels |
| `129c382` | WU11 — D10: the board never veils |
| `16fc6f3` | WU11 — D11: a card move never blocks |
| `e61e2f9` | WU12 — the spec rewritten a third time |

The closing commit for this document follows the nine above and adds no behavior.

Gates, run by the orchestrator on the full tree after WU11: `pnpm exec tsc --noEmit` exit 0 and
`npm test` **77 files / 877 tests** passing. `FullPageLoader`'s own test is still unchanged and
passing, which is what proves the veil extraction preserved the mutation veil's rendering. No
backend file was touched in this increment, so no backend gate was re-run for it.

### Verified in a real browser, not only in tests

ego-browser against the dev stack (`:4321` + `:8000`, real data: 7 tasks in a workspace):

- **The entry veil was real.** `waitForSelector('div[role="status"]')` on `/en/kanban` caught
  `Loading...` with class `fixed inset-0 z-[60] …`. After WU11 the board renders its cards with no
  `div[role="status"]` present at all.
- **The card-move overlay was real, and its cause was measurable.** In the running app,
  `import('/src/lib/blocking-requests.ts')` returned
  `shouldBlockRequest('PUT', '/api/v1/tasks/<uuid>') === true`, and a `MutationObserver` recorded the
  `Processing...` veil appearing during a real drag. After WU11 the same call returns `false`, a
  query string cannot flip it back (`false`), a task sub-resource still blocks (`true`), and a
  **committed** drag — the board went `backlog=0, todo=3` and the server agreed — produced **no veil
  sighting of any kind**.

Three things that cost time and are worth inheriting:

- **`hello-pangea/dnd` ignores ordinary synthetic drags.** `dragAndDrop()` and the high-level mouse
  sequence both did nothing, and the keyboard sensor never lifted either. Raw CDP works, and the
  piece that was missing is `buttons: 1` on the `mouseMoved` events. The gesture is still
  probabilistic — the same sequence committed on one run and silently did nothing on the next — so
  the verification retries and checks the outcome instead of trusting the gesture.
- **A GET read through the page can answer from cache.** One read said the moved card was back in
  `backlog` while the server had it in `todo`; a cache-busting parameter settled it. Any check that
  decides whether a write landed must bust the cache first, or it reports the opposite of the truth.
- **Importing an app store from the page can create a second instance.** Vite serves a distinct
  module for the app after HMR, so `import('/src/stores/taskStore.ts')` in a probe saw an empty
  store while the board on screen was full. Mechanism-level probes survive that (`blocking-requests.ts`
  is pure); state probes do not.

### What the owner changed, and what that cost

This increment shipped three loading models in two days: WU7 veiled every board read, WU9 veiled
only the entry, WU11 veils nothing. The honest accounting is that each earlier model was over-broad
rather than wrong — WU7 answered "the board says nothing" without asking whether a filter change is
an arrival, and WU9 answered "the entry is an arrival" without asking whether the user wants an
arrival announced that way. Each reversal was cheap in code and expensive in tests: **six test
rewrites across two reversals**, all done in place rather than by deletion, so the history of the
contract stays readable in the diffs.

The other half, D11, was never a design question at all: the drag had been raising the mutation veil
since before this increment and nothing about the feature touched it. It surfaced because the owner
used the board, not because anyone reasoned about it — which is the argument for having driven the
browser during this slice at all.

The lesson this document keeps instead of an apology: a loading state is a claim about what the user
is waiting for, and the only reliable way to find which claims are wrong is to watch someone use it.
