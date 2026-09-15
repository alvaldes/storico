# task-editor Specification

## Requirements

### Requirement: Task Editor Component

The frontend MUST add `TaskEditor.tsx` as a modal built on the existing shadcn
`Dialog` primitive. It MUST edit four fields: `title` (text input),
`description` (textarea), `labels` (tag input — each label a removable chip,
Enter to add), and `dependencies` (multi-select of sibling tasks within the same
story, by `task.id`).

### Requirement: Task Editor Trigger

`StoryDetail.tsx` MUST render an inline "Edit" button on each task card.
Clicking it MUST open `TaskEditor` pre-populated with the task's current values.
The button MUST be disabled while the story is extracting tasks.

#### Scenario: Edit disabled during extraction

- **GIVEN** an extraction is in progress for the story
- **WHEN** the task card renders
- **THEN** the Edit button is disabled with a tooltip explaining extraction is in progress

### Requirement: Task Editor Persistence

On submit, `TaskEditor` MUST call `PUT /api/v1/tasks/{taskId}` with the edited
fields. The component MUST optimistically update `taskStore` and MUST roll back
on HTTP failure. Success MUST show a localized toast and close the dialog;
failure MUST show a localized error toast and keep the dialog open with the
user's edits intact.

#### Scenario: Happy path — edits persist

- **GIVEN** a user is on a story page and at least one task card is rendered
- **WHEN** the user edits `title` and adds a label, then saves
- **THEN** `TaskEditor` calls `PUT /api/v1/tasks/{taskId}` with the new payload
- **AND** on HTTP 200 the store updates the task and the card re-renders
- **AND** a success toast appears and the dialog closes

#### Scenario: Save failure — rollback without data loss

- **GIVEN** the user has edited fields in `TaskEditor`
- **WHEN** `PUT /api/v1/tasks/{taskId}` returns HTTP 4xx/5xx
- **THEN** the store rolls back to the original task values
- **AND** the dialog stays open with the user's unsaved edits intact
- **AND** a localized error toast appears

### Requirement: Labels and Dependencies Validation

The component MUST reject empty labels and MUST deduplicate label input
case-insensitively. Dependencies MUST be limited to tasks from the same story
and the editor MUST NOT allow a task to depend on itself.

#### Scenario: Label deduplication and empty rejection

- **GIVEN** the user types `Frontend` and the task already has `frontend` as a label
- **WHEN** the user presses Enter
- **THEN** no duplicate label is added (case-insensitive match)
- **AND** a whitespace-only input adds no label

#### Scenario: Self-dependency rejected

- **GIVEN** `TaskEditor` is editing task `T1`
- **WHEN** the user attempts to add `T1` itself as a dependency
- **THEN** the dependency is rejected and a localized warning toast appears
