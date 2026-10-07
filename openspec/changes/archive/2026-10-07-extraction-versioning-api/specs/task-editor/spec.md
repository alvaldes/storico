# task-editor Specification

> **Change**: `extraction-versioning-api`

## MODIFIED Requirements

### Requirement: Task Editor Component

The frontend MUST keep `TaskEditor.tsx` as a modal built on the existing shadcn
`Dialog` primitive, and MUST render its fields according to the version's state:
`title` (text input, read-only), `description` (textarea, read-only), `status`
(select, always enabled), `labels` (tag input — each label a removable chip,
Enter to add), and `dependencies` (multi-select of sibling tasks within the same
story, by `task.id`, disabled while the task's version is frozen). The component
MUST NOT render a `priority` control, and MUST render an "Inválida" checkbox with
a mandatory reason textarea that appears when the checkbox is checked.

#### Scenario: Read-only title and description, live status and labels

- **GIVEN** a task on the current version is opened in `TaskEditor`
- **WHEN** the editor renders
- **THEN** `title` and `description` are shown read-only
- **AND** `status` and `labels` are editable
- **AND** `dependencies` are editable
- **AND** no `priority` control is rendered

#### Scenario: A frozen version locks dependencies and keeps status and labels live

- **GIVEN** a task whose version is not the story's current version is opened in `TaskEditor`
- **WHEN** the editor renders
- **THEN** the `dependencies` multi-select is disabled
- **AND** `status` and `labels` remain editable
- **AND** the "Inválida" checkbox is disabled

### Requirement: Task Editor Trigger

`StoryDetail.tsx` MUST render an inline "Edit" button on each task card.
Clicking it MUST open `TaskEditor` pre-populated with the task's current values.
The button MUST be disabled while the story is extracting tasks. Beside it, the
page MUST render a "Marcar como inválida" button that opens the same editor with
the "Inválida" checkbox already checked and the focus on the reason field, ready
to type; nothing is applied until the user saves, and cancelling leaves no mark.
When the task is already marked, the button opens the editor with the reason
populated. The mark button MUST be hidden or disabled on frozen versions, and
MUST be hidden or disabled for a `MEMBER` — the server gate remains the
authority.

#### Scenario: Edit disabled during extraction

- **GIVEN** an extraction is in progress for the story
- **WHEN** the task card renders
- **THEN** the Edit button is disabled with a tooltip explaining extraction is in progress

#### Scenario: The mark button opens the editor with the checkbox set and focus on the reason

- **GIVEN** a task card on the current version of a story
- **WHEN** the user clicks "Marcar como inválida"
- **THEN** `TaskEditor` opens with the "Inválida" checkbox already checked
- **AND** the focus is on the reason field
- **AND** no request has been made and no mark has been written

#### Scenario: Cancelling the mark editor leaves no mark

- **GIVEN** the editor was opened through "Marcar como inválida"
- **WHEN** the user cancels the dialog
- **THEN** no HTTP request is issued and no mark exists for the task

#### Scenario: An already-marked task opens with the reason populated

- **GIVEN** a task with an active mark on the current version
- **WHEN** the user clicks "Marcar como inválida"
- **THEN** `TaskEditor` opens with the checkbox checked and the reason populated

### Requirement: Task Editor Persistence

On submit, `TaskEditor` MUST call `PUT /api/v1/tasks/{taskId}` with only the
fields the write contract accepts — `status`, `labels`, and `dependencies` when
they are editable — and MUST NOT send `title`, `description` or `priority` in any
case. Saving with the "Inválida" checkbox checked and a non-empty reason MUST
persist the mark; saving with the checkbox checked and an empty or whitespace-only
reason MUST persist nothing — the client blocks the save and marks the reason
field as missing, and the server's 422 refusal is the backstop. Saving with the
checkbox unchecked on a marked task MUST revoke the mark. The component MUST
optimistically update `taskStore` and MUST roll back on HTTP failure. Success MUST
show a localized toast and close the dialog; failure MUST show a localized error
toast and keep the dialog open with the user's edits intact.

#### Scenario: Happy path — editable fields persist and the payload carries no removed fields

- **GIVEN** a user is on a story page and at least one task card is rendered
- **WHEN** the user changes `status` and adds a label, then saves
- **THEN** `TaskEditor` calls `PUT /api/v1/tasks/{taskId}` with a payload containing `status` and
  `labels` and no `title`, `description` or `priority`
- **AND** on HTTP 200 the store updates the task and the card re-renders
- **AND** a success toast appears and the dialog closes

#### Scenario: Save with the checkbox checked and an empty reason persists nothing

- **GIVEN** the user opened the editor through "Marcar como inválida" and left the reason empty
- **WHEN** the user saves
- **THEN** the save is blocked client-side, the reason field is marked as missing, and no HTTP
  request is issued
- **AND** if a request reaches the server with an empty reason anyway, the 422 refusal leaves no
  mark persisted and the dialog stays open

#### Scenario: Saving with a reason marks the task

- **GIVEN** the editor is open with the "Inválida" checkbox checked and a non-empty reason
- **WHEN** the user saves
- **THEN** the mark is persisted for the task with that reason
- **AND** the dialog closes with a success toast

#### Scenario: Unchecking the checkbox on a marked task revokes the mark

- **GIVEN** a task with an active mark, opened in the editor with the reason populated
- **WHEN** the user unchecks the "Inválida" checkbox and saves
- **THEN** the mark is revoked — the row records who revoked it and when
- **AND** the mark record itself is not deleted

#### Scenario: Save failure — rollback without data loss

- **GIVEN** the user has edited fields in `TaskEditor`
- **WHEN** `PUT /api/v1/tasks/{taskId}` returns HTTP 4xx/5xx
- **THEN** the store rolls back to the original task values
- **AND** the dialog stays open with the user's unsaved edits intact
- **AND** a localized error toast appears

### Requirement: Labels and Dependencies Validation

The component MUST reject empty labels and MUST deduplicate label input
case-insensitively. Dependencies MUST be limited to tasks from the same story
and the editor MUST NOT allow a task to depend on itself. While the task's
version is frozen, the dependencies multi-select MUST stay disabled so no
dependency change can be sent.

#### Scenario: Label deduplication and empty rejection

- **GIVEN** the user types `Frontend` and the task already has `frontend` as a label
- **WHEN** the user presses Enter
- **THEN** no duplicate label is added (case-insensitive match)
- **AND** a whitespace-only input adds no label

#### Scenario: Self-dependency rejected

- **GIVEN** `TaskEditor` is editing task `T1`
- **WHEN** the user attempts to add `T1` itself as a dependency
- **THEN** the dependency is rejected and a localized warning toast appears

#### Scenario: A frozen version offers no dependency edit to send

- **GIVEN** `TaskEditor` is editing a task whose version is frozen
- **WHEN** the user saves with edited `status` and `labels`
- **THEN** the request payload contains no `dependencies` change
- **AND** no `TASK_VERSION_FROZEN` refusal can be triggered by the editor

## ADDED Requirements

### Requirement: Marking and Unmarking Ask for Confirmation

Marking a task invalid and revoking its mark MUST each ask for explicit
confirmation before being applied, and cancelling MUST perform no request. The
confirmation dialog MUST say what the mark implies: it is the user's judgment, it
travels to the prompt of the next extraction, and it cannot be withdrawn once the
version freezes.

#### Scenario: The mark is confirmed before it is applied

- **GIVEN** the user saves the editor with the "Inválida" checkbox checked and a non-empty reason
- **WHEN** the confirmation dialog appears
- **THEN** the dialog states that the mark travels to the next extraction's prompt and cannot be
  withdrawn once the version freezes
- **AND** confirming applies the mark; cancelling issues no request and no mark exists

#### Scenario: The unmark is confirmed before it is applied

- **GIVEN** the user saves the editor with the checkbox unchecked on a marked task
- **WHEN** the confirmation dialog appears
- **THEN** confirming revokes the mark; cancelling issues no request and the mark stays active

### Requirement: The Editor Warns on a Repetition of a Marked Title

When the normalized title of the task being edited — `casefold` plus whitespace
collapse — exactly equals the normalized title of a task already marked on
another version of the same story, the editor MUST show the localized notice
"Marcaste esta tarea en v{version}: {motivo}" with the earlier mark's version and
reason, and MUST offer one action that copies that reason into the reason field.
The notice MUST NOT write anything by itself: no mark, no update, no propagation.
An exact normalized-title match MUST be the only match — a fuzzy or vector
similarity match is out of scope by decision.

#### Scenario: The notice appears with the earlier version and reason

- **GIVEN** the user is marking a task in v3 whose normalized title matches a task marked in v1
  with reason "Already covered by the auth refactor"
- **WHEN** the editor renders the mark controls
- **THEN** the notice reads "Marcaste esta tarea en v1: Already covered by the auth refactor"
  (localized in both locales)

#### Scenario: One action copies the reason into the field

- **GIVEN** the repetition notice is showing an earlier mark's reason
- **WHEN** the user activates the notice's copy action
- **THEN** the reason field is filled with that reason
- **AND** nothing has been persisted yet — the mark is only written on confirmed save

#### Scenario: The notice writes nothing

- **GIVEN** the repetition notice is showing
- **WHEN** the user reads or dismisses the notice without saving
- **THEN** no mark row was created, updated or revoked by the notice
- **AND** the earlier mark stays on its own version's task

#### Scenario: A near-identical title does not trigger the notice

- **GIVEN** a task whose normalized title differs in any character from every marked task's
  normalized title in the other versions of the same story
- **WHEN** the editor renders the mark controls
- **THEN** no repetition notice appears
- **AND** no fuzzy or similarity comparison is performed
