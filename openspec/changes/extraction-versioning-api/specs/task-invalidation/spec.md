# task-invalidation Specification

> **Change**: `extraction-versioning-api`

## ADDED Requirements

### Requirement: Creating a Mark Requires a Reason, the Current Version and the Gate

`POST /api/v1/tasks/{task_id}/invalidations` MUST create the invalidation mark. The body MUST
carry a non-empty `reason` — an empty or whitespace-only reason MUST be refused with HTTP 422 and
`error_code` `REQUEST_VALIDATION_FAILED`, persisting nothing. A valid mark MUST answer HTTP 201
with the mark's record, including its reason, its acting user and its timestamp. Marking a task
that already holds an active mark MUST be refused with HTTP 409 and `error_code`
`TASK_ALREADY_MARKED`, whose detail carries the active reason, and no second row MUST be written.
Marking a task on a version that is not the story's current version MUST be refused with HTTP 409
and `error_code` `TASK_VERSION_FROZEN`. Marking MUST be available only to the workspace owner or
an `ADMIN`: a `MEMBER` MUST receive HTTP 403 with `error_code`
`WORKSPACE_OWNER_OR_ADMIN_REQUIRED`, which the client renders as an explicit localized refusal
rather than a raw 403.

#### Scenario: A valid mark round-trips with reason, actor and timestamp

- **GIVEN** a task on the current version, no active mark, and the workspace owner as requester
- **WHEN** the client calls `POST /api/v1/tasks/{task_id}/invalidations` with body
  `{"reason": "Duplicates the login task from v1"}`
- **THEN** the backend answers HTTP 201 with the mark record
- **AND** the record carries the given reason, the owner as actor and a marking timestamp
- **AND** exactly one mark row was persisted

#### Scenario: A blank reason persists nothing

- **GIVEN** a task on the current version with no active mark
- **WHEN** the client calls `POST /api/v1/tasks/{task_id}/invalidations` with a reason that is
  empty or whitespace only
- **THEN** the backend answers HTTP 422 with `error_code` `REQUEST_VALIDATION_FAILED`
- **AND** no mark row exists after the call

#### Scenario: A second active mark is refused with the live reason in the detail

- **GIVEN** a task with an active mark whose reason is "Duplicates the login task from v1"
- **WHEN** a second mark is attempted on the same task
- **THEN** the backend answers HTTP 409 with `error_code` `TASK_ALREADY_MARKED`
- **AND** the detail carries the active reason
- **AND** no second mark row was written

#### Scenario: Marking a task on a frozen version is refused

- **GIVEN** a task whose version is not the story's current version
- **WHEN** the owner or an `ADMIN` calls `POST /api/v1/tasks/{task_id}/invalidations` with a valid
  reason
- **THEN** the backend answers HTTP 409 with `error_code` `TASK_VERSION_FROZEN`
- **AND** no mark row exists after the call

#### Scenario: A MEMBER is refused with an explicit localized message

- **GIVEN** a workspace `MEMBER` and a task on the current version
- **WHEN** the member calls `POST /api/v1/tasks/{task_id}/invalidations` with a valid reason
- **THEN** the backend answers HTTP 403 with `error_code`
  `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`
- **AND** the client renders the code's localized refusal instead of a raw 403
- **AND** no mark row exists after the call

### Requirement: The Mark Record Is Readable With Its Full History

`GET /api/v1/tasks/{task_id}/invalidations` MUST return the task's mark rows ordered by `marked_at`
descending with the active mark first, each row carrying `id`, `reason`, `marked_by`, `marked_at`,
`revoked_by` and `revoked_at`. The read MUST be open to every workspace member.

#### Scenario: The record lists history with the active mark first

- **GIVEN** a task with one revoked mark from an earlier date and one active mark
- **WHEN** a workspace member calls `GET /api/v1/tasks/{task_id}/invalidations`
- **THEN** the response lists the active mark first
- **AND** every row carries `id`, `reason`, `marked_by`, `marked_at`, `revoked_by` and
  `revoked_at`

#### Scenario: A task with no marks reads as empty

- **GIVEN** a task that has never been marked
- **WHEN** a workspace member calls `GET /api/v1/tasks/{task_id}/invalidations`
- **THEN** the backend answers HTTP 200 with an empty list

### Requirement: Revoking Updates the Row and Never Deletes It

`DELETE /api/v1/tasks/{task_id}/invalidations/current` MUST revoke the task's active mark by
updating its row with who revoked it and when, answering HTTP 204. The mark row MUST never be
deleted by revocation. Revoking MUST be allowed only on the story's current version — a frozen
version's active mark MUST be refused with HTTP 409 and `error_code` `TASK_VERSION_FROZEN` — and
only for the workspace owner or an `ADMIN`, with a `MEMBER` refused as above. A task with no
active mark MUST answer HTTP 404. Marking again after a revoke MUST create a new row, so both
events stay readable.

#### Scenario: Revoking records who and when on the surviving row

- **GIVEN** a task with an active mark, on the current version
- **WHEN** the owner or an `ADMIN` calls
  `DELETE /api/v1/tasks/{task_id}/invalidations/current`
- **THEN** the backend answers HTTP 204
- **AND** the same mark row now records the revoking user and the revocation timestamp
- **AND** the row still exists with its original reason, `marked_by` and `marked_at` unchanged

#### Scenario: Unmarking is blocked on a frozen version

- **GIVEN** a task with an active mark whose version is not the story's current version
- **WHEN** the owner or an `ADMIN` calls
  `DELETE /api/v1/tasks/{task_id}/invalidations/current`
- **THEN** the backend answers HTTP 409 with `error_code` `TASK_VERSION_FROZEN`
- **AND** the mark row is unchanged and still active

#### Scenario: Revoking without an active mark is a 404

- **GIVEN** a task with no active mark
- **WHEN** the owner or an `ADMIN` calls
  `DELETE /api/v1/tasks/{task_id}/invalidations/current`
- **THEN** the backend answers HTTP 404

#### Scenario: Re-marking after a revoke keeps both events readable

- **GIVEN** a task whose mark was revoked, on the current version
- **WHEN** the task is marked invalid again with a valid reason
- **THEN** the backend answers HTTP 201 and a second mark row exists
- **AND** the first row still records the first marking and its revocation

### Requirement: The Repetition Read Warns on an Exact Normalized-Title Match

The backend MUST expose
`GET /api/v1/tasks/{task_id}/invalidations/repetition` returning the marks recorded on other
versions of the same story whose normalized task title equals this task's, where normalization is
`casefold` plus whitespace collapse. The match MUST be exact on the normalized titles only — a
fuzzy or vector similarity match MUST NOT be computed, by decision. Each match MUST carry
`version_number`, `reason` and `marked_at`. The title MUST be resolved server-side from the task
id, so the normalizer lives in one place and the read accepts no arbitrary text. The read MUST
write nothing and propagate nothing.

#### Scenario: A matching mark from another version is offered

- **GIVEN** a task titled "Implement login retry" in v3 and an active mark in v1 on a task titled
  "Implement  Login Retry", with reason "Already covered by the auth refactor"
- **WHEN** the editor requests `GET /api/v1/tasks/{task_id}/invalidations/repetition`
- **THEN** the response's `matches` contains `{"version_number": 1, "reason": "Already covered by
  the auth refactor", "marked_at": <its timestamp>}`

#### Scenario: Nothing similar means no match

- **GIVEN** a task in v3 whose normalized title matches no mark on any other version of its story
- **WHEN** the repetition read is requested
- **THEN** the response is `{"matches": []}`

#### Scenario: Marks on the task's own version do not match

- **GIVEN** another task of the same version as the edited task, carrying an active mark with the
  same normalized title
- **WHEN** the repetition read is requested for the edited task
- **THEN** the response is `{"matches": []}`
- **AND** the same-version mark is not offered

#### Scenario: Marks from other stories never match

- **GIVEN** the edited task in v3 of its story, and a marked task of the same normalized title in
  another story of the same workspace
- **WHEN** the repetition read is requested for the edited task
- **THEN** the response is `{"matches": []}`
- **AND** the other story's mark is not offered

#### Scenario: The read writes nothing

- **GIVEN** a task whose normalized title matches a mark from another version
- **WHEN** the repetition read is requested
- **THEN** the backend answers HTTP 200 with the match
- **AND** no mark row was created, updated or revoked by the read
- **AND** the mark of the other version is unchanged and stays on its own version's task
