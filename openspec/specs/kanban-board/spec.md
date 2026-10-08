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

The island MUST distinguish four levels of read feedback, and the level MUST be the message.

**Entering the board** — the first task read for the current workspace, a switch to another
workspace, and the retry from the error card after a failed first read — MUST raise a blocking
full-viewport veil carrying a single `aria-live="polite"` status region with a localized label. A
workspace switch counts as entering because every filter is cleared and every card replaced; a
failed first read counts as never having entered, because the user has seen only the error card.

**Every other task read** — a filter change, and a retry once a board has been seen — MUST show an
internal loader inside the board area, in place of the columns, and MUST NOT raise the veil. The
internal loader MUST NOT cover or disable the filter bar: changing filters while a read is in
flight is supported, and an out-of-order answer MUST be discarded rather than applied. It MUST
replace the columns rather than float over them, so the previous filter's cards are never
presented as the answer to the filter now in the bar.

**While a select's own options are being read**, that select MUST carry its own loader and MUST
set `aria-busy` on its trigger, so that a pending read is attributable to the control that caused
it and an empty select is never indistinguishable from a loading one. Each select MUST reflect
only its own read.

**A task status change from a card move** MUST raise none of the above: that path is optimistic
and MUST show only its own card-level in-flight state.

In every level the feedback MUST be raised by the island's own read state and MUST NOT be raised
through the mutation-only global loading store, so that a board read never signals a write in
flight. A read that fails MUST win over any loader and replace the board with its error state. An
empty board MUST NOT be reported as empty until a read has settled for the filters the bar
currently shows.

#### Scenario: Entering the board raises the full veil

- **GIVEN** a workspace is selected and no board has been read yet
- **WHEN** the user opens `/[locale]/kanban`
- **THEN** the full-viewport veil covers the page until the first task read settles
- **AND** it does not return for that workspace afterwards

#### Scenario: A filter change shows the internal loader, not the veil

- **GIVEN** a board that has already been read
- **WHEN** the user picks a project and the task read is still in flight
- **THEN** the internal loader shows in place of the columns
- **AND** no full-viewport veil is raised
- **AND** the filter bar stays rendered and usable

#### Scenario: A workspace switch is a new entry

- **GIVEN** a board read for workspace A
- **WHEN** the user switches the selected workspace to workspace B
- **THEN** the full-viewport veil covers the page until B's first task read settles

#### Scenario: The retry after a failed first read still enters the board

- **GIVEN** a first board read that failed, with the error card on screen
- **WHEN** the user retries
- **THEN** the full-viewport veil covers the page until the retry settles

#### Scenario: A select shows its own loader while its read is pending

- **GIVEN** a board that has already been read and a project picked
- **WHEN** the stories read for the story select has not answered yet
- **THEN** the story select shows its own loader and reports `aria-busy`
- **AND** the other selects are quiet, because each reflects only its own read
- **AND** no full-viewport veil is raised

#### Scenario: A card move raises no board-level loading

- **GIVEN** a loaded board with a task in a column
- **WHEN** the user drags the card to another column and the status update is in flight
- **THEN** neither the veil nor the internal loader is raised
- **AND** the card keeps its own in-flight indicator and the optimistic move stands

#### Scenario: No workspace selected is not covered by the veil

- **GIVEN** no workspace is selected
- **WHEN** the user opens `/[locale]/kanban`
- **THEN** the localized "Select a workspace" prompt renders
- **AND** no loading veil covers it, because no read is in flight

#### Scenario: An empty board is not called empty before an answer arrives

- **GIVEN** a workspace selected and a first board read that has not settled yet
- **WHEN** the board renders
- **THEN** the localized "No tasks yet" copy is absent
- **AND** it appears only once a read has settled with no tasks for the filters the bar shows

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
