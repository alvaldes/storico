# kanban-board Specification

## Requirements

### Requirement: Kanban Page Route

The frontend MUST expose a route at `/[locale]/kanban` rendered by
`frontend/src/pages/[locale]/kanban.astro`. The page MUST be wired into the
existing sidebar navigation, MUST use the existing `MainLayout.astro`, and MUST
pass `locale` to the React island.

### Requirement: Kanban Board Component

The page MUST render a single React island `KanbanBoard.tsx`. The island MUST
use `@hello-pangea/dnd` for drag-and-drop and MUST display exactly five columns
in this fixed order: `Backlog → To Do → In Progress → Review → Done`. The
column a task belongs to MUST be derived from `task.status`.

#### Scenario: Happy path — board loads tasks

- **GIVEN** a workspace is selected
- **WHEN** the user navigates to `/[locale]/kanban`
- **THEN** the board fetches the workspace's tasks and groups them into the five columns by `task.status`
- **AND** every status value (`backlog`, `todo`, `in_progress`, `review`, `done`) maps to exactly one column

### Requirement: Kanban Task Fetching

`KanbanBoard.tsx` MUST fetch tasks via `GET /api/v1/tasks/` and MUST read
`workspaceId` from `useWorkspaceStore.currentWorkspace?.id`. The board's read
is not tied to the workspace scope: the island resolves its filter cascade
(see "Kanban Filter Cascade") to exactly one server-side scope — `project_id`,
`user_story_id` (with an optional `extraction_id`) or `workspace_id` — before
any request leaves the client, and `taskStore.ts` MUST expose a
`fetchTasksForWorkspace(workspaceId, filters?)` action that stores results
under a top-level `workspaceTasks: Task[]` slot, separate from the per-story
`tasks` map. The current-version contract holds for every scope the board can
issue: the unfiltered workspace read, the project-scoped read and the
story-scoped read each return only the tasks of each story's current version,
so a story with two completed runs MUST NOT put two task sets on the board;
only the version-filtered read, which names an explicit `extraction_id`,
answers a frozen version's tasks. If no workspace is selected the island MUST
show a localized empty-state prompting the user to select one and MUST NOT
issue a request.

#### Scenario: No workspace selected

- **GIVEN** `useWorkspaceStore.currentWorkspace` is null
- **WHEN** the user navigates to `/[locale]/kanban`
- **THEN** the island shows the localized "Select a workspace" prompt and issues NO HTTP request

#### Scenario: A story with two completed runs shows only the current version's tasks

- **GIVEN** a workspace containing a story whose v1 and v2 are both `completed`, with 3 tasks in
  v1 and 4 tasks in v2
- **WHEN** the board fetches the workspace's tasks
- **THEN** the board shows exactly the 4 tasks of v2 for that story
- **AND** no task of v1 is rendered in any column

#### Scenario: A story with no completed version contributes no board tasks and no error

- **GIVEN** a workspace containing a story whose only run is `failed`
- **WHEN** the board fetches the workspace's tasks
- **THEN** the fetch succeeds and that story contributes no cards
- **AND** the board does not treat the story as an error

#### Scenario: A project-filtered board still shows only current versions

- **GIVEN** a project containing a story whose v1 and v2 are both `completed`
- **WHEN** the user filters the board to that project
- **THEN** the board shows exactly the tasks of v2 for that story
- **AND** no task of v1 is rendered in any column

### Requirement: Kanban Filter Cascade

The board MUST offer a filter bar of three cascading selects — Project → Story → Version — where
an "All …" option at each level means "not filtered at this level". The story select MUST be
unusable until a project is chosen, and the version select until a story is chosen. The cascade
MUST resolve to exactly one server-side scope before any request leaves the client, by most
specific wins: story plus version → `user_story_id` + `extraction_id`; story alone →
`user_story_id`; project alone → `project_id`; nothing → `workspace_id` — because the backend
refuses a read that names two scopes with 422 `REQUEST_VALIDATION_FAILED`. The version scope
MUST read that version's tasks, including a frozen one's. Moving up the cascade MUST clear
everything below it, so no request ever carries a scope orphaned from its parent. A retried load
after a failure MUST carry the active filters — never silently reload the whole workspace while
the bar still names a filter — and switching workspaces MUST clear the filters, so a project
chosen in one workspace is never applied to another.

#### Scenario: A version pick reads that version through user_story_id and extraction_id

- **GIVEN** a project chosen, one of its stories chosen, and one of that story's versions chosen
  in the cascade
- **WHEN** the board loads
- **THEN** the client issues `GET /api/v1/tasks/?user_story_id={story_id}&extraction_id={version_id}`
- **AND** a frozen version's own tasks are shown, not its story's current ones

#### Scenario: A story pick reads the story's current version through user_story_id

- **GIVEN** a project chosen and one of its stories chosen in the cascade, with no version picked
- **WHEN** the board loads
- **THEN** the client issues `GET /api/v1/tasks/?user_story_id={story_id}`
- **AND** the board shows that story's current version's tasks

#### Scenario: A project pick reads through project_id

- **GIVEN** a project chosen in the cascade, with no story picked
- **WHEN** the board loads
- **THEN** the client issues `GET /api/v1/tasks/?project_id={project_id}`
- **AND** the board shows each of the project's stories' current-version tasks

#### Scenario: An empty cascade reads the whole workspace

- **GIVEN** every select at "All …" — nothing filtered at any level
- **WHEN** the board loads
- **THEN** the client issues `GET /api/v1/tasks/?workspace_id={workspaceId}`
- **AND** the query names no other scope

#### Scenario: A retried load carries the active filters

- **GIVEN** a filtered board whose load failed, with the bar still naming the filter
- **WHEN** the user retries the load
- **THEN** the retry issues the same scoped query the bar names, not the workspace's unfiltered
  one

#### Scenario: A workspace switch clears the filters

- **GIVEN** a board filtered to a project of workspace A
- **WHEN** the user switches the selected workspace to workspace B
- **THEN** the filters are cleared and the board fetches workspace B unfiltered
- **AND** no project of workspace A is ever applied to a request scoped to workspace B

### Requirement: Kanban Board Read Feedback

The board MUST distinguish its reads from a mutation, and the distinction MUST be visible.

**Every board read** — the first read when the board opens, a workspace switch, a filter change and
a retry — MUST show an internal loader inside the board area, in place of the columns. The board
MUST NOT raise the full-viewport veil: that veil means a mutation is in flight, and opening a board
is not one. A workspace switch counts as a board read like any other, and a retry after a failed
read is likewise a board read rather than a special case.

The internal loader MUST NOT cover or disable the filter bar: changing filters while a read is in
flight is supported, and an out-of-order answer MUST be discarded rather than applied. It MUST
replace the columns rather than float over them, so the previous filter's cards are never presented
as the answer to the filter now in the bar.

**While a select's own options are being read**, that select MUST carry its own loader and MUST set
`aria-busy` on its trigger, so that a pending read is attributable to the control that caused it and
an empty select is never indistinguishable from a loading one. Each select MUST reflect only its own
read.

**A task status change from a card move** MUST raise neither the internal loader nor the
full-viewport veil. The request it sends — `PUT /api/v1/tasks/{task_id}` — MUST be exempt from the
blocking set, because the drop is optimistic and the card carries its own in-flight indicator, so a
page-wide overlay would interrupt the gesture it is meant to confirm. The exemption MUST cover
exactly that one task resource: a task sub-resource or a prefix-sharing sibling path MUST still
block.

In every case the feedback MUST be raised by the island's own read state and MUST NOT be raised
through the mutation-only global loading store, so that a board read never signals a write in
flight. A read that fails MUST win over any loader and replace the board with its error state. An
empty board MUST NOT be reported as empty until a read has settled for the filters the bar currently
shows.

#### Scenario: Opening the board shows the internal loader, never the full veil

- **GIVEN** a workspace is selected and no board has been read yet
- **WHEN** the user opens `/[locale]/kanban`
- **THEN** the internal loader shows in place of the columns while the first task read is in flight
- **AND** no full-viewport veil is raised at any point

#### Scenario: A filter change shows the internal loader, not the veil

- **GIVEN** a board that has already been read
- **WHEN** the user picks a project and the task read is still in flight
- **THEN** the internal loader shows in place of the columns
- **AND** no full-viewport veil is raised
- **AND** the filter bar stays rendered and usable

#### Scenario: A workspace switch is a board read like any other

- **GIVEN** a board read for workspace A
- **WHEN** the user switches the selected workspace to workspace B
- **THEN** the internal loader shows in place of the columns while B's first read is in flight
- **AND** no full-viewport veil is raised

#### Scenario: A card move raises no board-level loading and no overlay

- **GIVEN** a loaded board with a task in a column
- **WHEN** the user drags the card to another column and the status update is in flight
- **THEN** neither the internal loader nor the full-viewport veil is raised
- **AND** the `PUT /api/v1/tasks/{task_id}` it sends does not hold the blocking loader open
- **AND** the card keeps its own in-flight indicator and the optimistic move stands

#### Scenario: The task exemption does not widen to lookalike paths

- **GIVEN** the blocking decision for a mutating request
- **WHEN** the request targets a task sub-resource such as `/api/v1/tasks/{task_id}/comments`, or a
  path that merely shares the prefix such as `/api/v1/tasks-bulk/x`
- **THEN** the request still holds the blocking loader open

#### Scenario: A select shows its own loader while its read is pending

- **GIVEN** a board that has already been read and a project picked
- **WHEN** the stories read for the story select has not answered yet
- **THEN** the story select shows its own loader and reports `aria-busy`
- **AND** the other selects are quiet, because each reflects only its own read
- **AND** no full-viewport veil is raised

#### Scenario: No workspace selected is not covered by a loader

- **GIVEN** no workspace is selected
- **WHEN** the user opens `/[locale]/kanban`
- **THEN** the localized "Select a workspace" prompt renders
- **AND** no loader covers it, because no read is in flight

#### Scenario: An empty board is not called empty before an answer arrives

- **GIVEN** a workspace selected and a first board read that has not settled yet
- **WHEN** the board renders
- **THEN** the localized "No tasks yet" copy is absent
- **AND** it appears only once a read has settled with no tasks for the filters the bar shows

### Requirement: Kanban Cards and Selects Name Their Context

Every board card MUST name the project and the story its task belongs to, as chips in the card's
metadata row, ordered **project → story → version → the task's own labels**: the three context chips
lead and the task's own attributes trail. The context chips MUST use the same badge variant and
sizing as the version chip and MUST be visually muted relative to the task's own labels.

The cascade's project and story selects MUST name the same two things under the same rules, so that
one surface is not a second, differing answer to where a card came from. The icon for each kind, the
label rule and the tooltip text MUST come from **one shared definition** both surfaces consume,
rather than from two implementations that happen to agree today.

The icon each surface draws MUST be the project's **own** icon when it has one, resolved through
the application's own icon renderer, with that renderer's default standing in when it does not — the
same default the project form seeds, so an icon-less project agrees with the rest of the application
instead of getting a second opinion. A story has no icon and MUST NOT be made to share the project's:
the story keeps its own fixed mark.

The label rules are:

- the **project** shows its name, truncated by **one character cap shared by both surfaces**. A
  surface MUST NOT apply a wider cap of its own: the same project reading `Version Test...` on a card
  and `Version Test LongTitle` in the dropdown reads as two different projects. What the cap hides
  stays reachable on hover, which is what makes the shorter text safe.
- the **story** shows its short identifier — the same one the story list and the story detail surface
  show, reused from that one implementation — followed in the select by its human label
  `${actor}: ${feature}`, itself shortened by the shared cap. A list of identifier prefixes alone is
  not something a person can choose from, and a label alone loses the one field that ties the row to
  the card. The identifier MUST NOT be truncated: it is already short, and shortening it would cost
  the characters that separate two stories of the same actor.

Every one of those chips and rows MUST reveal its full value on hover: the project's **full name**,
the story's **full sentence**. The tooltip MUST open as the pointer settles on the chip, with no
hover pause a user would notice, because a delay long enough to be perceived reads as a chip that has
no tooltip at all. The value MUST come from the same shared definition as the label, so
the truncated text and the tooltip cannot disagree. A hover MUST NOT raise an empty popup, and a chip
or row whose data the response does not carry MUST NOT render at all — no empty badge, no
placeholder.

On the board's card the tooltip MUST be the application's own tooltip, and the chips MUST NOT also
carry a native `title`: one hover must not raise two tooltips. Inside a select's listbox the options
MUST keep a native `title` instead, because a tooltip per option competes with the listbox's focus
and keyboard navigation; the select's trigger carries the real tooltip with its full selected value.

A card being dragged MUST NOT show a tooltip: the drag preview is a copy of the card, so an open
popup would travel with the pointer.

#### Scenario: A card shows its context, then its version, then its labels

- **GIVEN** a task whose response carries a project label, a story id, labels and a version number
- **WHEN** its card renders on the board
- **THEN** its metadata row shows the project name, the story's short identifier, the version and its labels, in that order

#### Scenario: A project's own icon is what the chips and rows draw

- **GIVEN** a project whose stored icon differs from the renderer's default
- **WHEN** a card of that project and the project's row in the select render
- **THEN** both draw that project's icon, not the default
- **AND** changing the project's stored icon changes both

#### Scenario: A project without an icon, and a story, keep their own marks

- **GIVEN** a project whose stored icon is empty, and any story
- **WHEN** their chips and rows render
- **THEN** the project draws the renderer's default rather than nothing
- **AND** the project's label and tooltip are unaffected
- **AND** the story draws its own mark, never the project's

#### Scenario: A hover reveals the value without a perceptible pause

- **GIVEN** a card whose chips carry tooltips and a pointer resting elsewhere
- **WHEN** the user moves the pointer onto a chip
- **THEN** the tooltip is open, not scheduled for a later moment
- **AND** a hover that moves on within a fraction of a second still sees it

#### Scenario: A hover reveals the full value the chip had to shorten

- **GIVEN** a card whose project name is longer than the card's cap and whose story carries a sentence
- **WHEN** the user hovers the project chip and then the story chip
- **THEN** the project's tooltip shows the name in full
- **AND** the story's tooltip shows the story's full sentence

#### Scenario: A long project name does not break the row

- **GIVEN** a task whose project name is long enough to overflow a card column
- **WHEN** its card renders
- **THEN** the project chip is bounded and its visible text is truncated
- **AND** the labels and the version chip remain in the row

#### Scenario: A missing label renders no chip and no empty popup

- **GIVEN** a task whose response carries no project label, or a story with no sentence
- **WHEN** its card renders and the user hovers what is there
- **THEN** no project chip is rendered in the first case
- **AND** no tooltip is empty in the second: the story's tooltip falls back to what the card has

#### Scenario: The select names a story the way a person can choose it

- **GIVEN** a project whose stories have actor and feature text
- **WHEN** the user opens the story select
- **THEN** each option shows the story's short identifier followed by its `${actor}: ${feature}` label, with its icon
- **AND** the label is shortened by the same cap the card chip uses
- **AND** the identifier itself is shown whole
- **AND** each option reveals the story's full sentence on hover

#### Scenario: One project reads the same on both surfaces

- **GIVEN** a project whose name is longer than the shared cap
- **WHEN** its card chip and its row in the select render
- **THEN** both show the same shortened text, not one at full length
- **AND** both reveal the full name on hover

#### Scenario: The card and the select consume one definition

- **GIVEN** the rules for the icon, the label and the tooltip text of each kind
- **WHEN** the card's chips and the select's rows render
- **THEN** both take those rules from the same shared definition
- **AND** a change to it changes both surfaces

#### Scenario: A dragged card carries no popup

- **GIVEN** a card whose chip tooltip is open
- **WHEN** the user starts dragging that card
- **THEN** the tooltip closes and no popup travels with the drag


### Requirement: Kanban Drag-and-Drop Status Update

When a task is dragged from one column to another and dropped, the island MUST
call `PUT /api/v1/tasks/{taskId}` with the new status. The UI MUST optimistically
move the card and MUST roll back on HTTP failure with an error toast. While the
PUT is in flight the card MUST show a subtle loading indicator and MUST NOT be
re-draggable. The five status values MUST match the backend enum: `backlog`,
`todo`, `in_progress`, `review`, `done`. Status MUST stay editable regardless of
version state: a status change issued for a task on a frozen version MUST succeed
on the server, and the UI MUST NOT block or warn against the drag because the
version is frozen.

#### Scenario: Drag-and-drop updates task status

- **GIVEN** the board is loaded with at least one task in the `Backlog` column
- **WHEN** the user drags the card from `Backlog` to `To Do` and drops it
- **THEN** the island optimistically updates the column and calls `PUT /api/v1/tasks/{taskId}` with `{ status: "todo" }`
- **AND** on HTTP 200 the card stays and the store updates the task
- **AND** on HTTP failure the card rolls back and a localized error toast appears

#### Scenario: Drag in flight blocks re-drag

- **GIVEN** a drag-and-drop PUT is in flight
- **WHEN** the user attempts to drag the same card again
- **THEN** the card is locked (not draggable) and shows a loading indicator until the PUT completes

#### Scenario: A status change on a frozen version's task succeeds

- **GIVEN** the story view is showing a frozen version's task with `status = "in_progress"`
- **WHEN** the user changes that task's status to `done`
- **THEN** the backend accepts the status change and persists it with HTTP 200
- **AND** no `TASK_VERSION_FROZEN` refusal is raised, because `status` is always editable

### Requirement: Kanban Empty States

The island MUST handle three distinct empty states: a workspace selected with no tasks and no
active filter MUST show a localized "No tasks yet" empty state with a hint to extract tasks from
a story; no workspace selected MUST show a localized "Select a workspace" prompt; and an active
filter that empties the board MUST show its own filter-emptied state, which MUST NOT borrow the
"No tasks yet" copy, because the workspace may well have tasks. The filter bar MUST render on
every workspace-selected state — both empty ones and a populated board — so an empty workspace
can gain its first filter and a filtered board can always be cleared.

#### Scenario: Workspace selected with zero tasks

- **GIVEN** a workspace is selected and the task fetch returns `[]`
- **WHEN** the board renders
- **THEN** the island shows the localized "No tasks yet" empty state with copy directing the user to extract tasks from a story
- **AND** the filter bar is rendered, so the empty workspace can gain its first filter

#### Scenario: An active filter empties the board without borrowing the no-tasks copy

- **GIVEN** a workspace with tasks and a filter that matches none of them
- **WHEN** the board renders
- **THEN** the island shows the localized filter-emptied state
- **AND** the copy does not claim there are no tasks yet or direct the user to extract tasks from a story
- **AND** the filter bar is rendered, so the filter can be cleared or narrowed

### Requirement: Kanban Cards Name Their Version

A board card whose task carries a version number MUST show a bare `v{n}` badge naming it. A task
with no version number MUST show no version badge at all — never a degraded `vnull` or an empty
badge. The card MUST NOT carry a currency marker such as "· current": a version-filtered board
renders frozen versions, and a task does not carry the fact that would let the card tell a
current read from a frozen one, so any currency claim on a card would be a lie. This is the
never-lie-about-currency rule the story card's badge obeys, applied to the one surface that
cannot know — no further decision about the card is recorded here.

#### Scenario: A task with a version number shows its bare v badge

- **GIVEN** a task whose response carries `version_number = 3`
- **WHEN** its card renders on the board
- **THEN** the card shows the badge `v3`
- **AND** the badge carries no currency marker

#### Scenario: A task with no version number shows no badge

- **GIVEN** a task whose `version_number` is `null`
- **WHEN** its card renders on the board
- **THEN** no version badge is rendered — not `vnull`, not an empty badge
