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

`KanbanBoard.tsx` MUST fetch tasks via the existing
`GET /api/v1/tasks/?workspace_id={workspaceId}` endpoint and MUST read
`workspaceId` from `useWorkspaceStore.currentWorkspace?.id`. The endpoint MUST
return only the tasks of each story's current version, so a story with two
completed runs MUST NOT put two task sets on the board. If no workspace is
selected the island MUST show a localized empty-state prompting the user to
select one and MUST NOT issue a request. `taskStore.ts` MUST expose a
`fetchTasksForWorkspace(workspaceId)` action that stores results under a
top-level `workspaceTasks: Task[]` slot, separate from the per-story `tasks`
map.

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

The island MUST handle two distinct empty states: a workspace selected with no
tasks MUST show a localized "No tasks yet" empty state with a hint to extract
tasks from a story, and no workspace selected MUST show a localized "Select a
workspace" prompt.

#### Scenario: Workspace selected with zero tasks

- **GIVEN** a workspace is selected and the task fetch returns `[]`
- **WHEN** the board renders
- **THEN** the island shows the localized "No tasks yet" empty state with copy directing the user to extract tasks from a story
