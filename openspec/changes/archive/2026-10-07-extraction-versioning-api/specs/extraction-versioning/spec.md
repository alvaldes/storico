# extraction-versioning Specification

> **Change**: `extraction-versioning-api`

## ADDED Requirements

### Requirement: Task Reads Return the Current Version Only

Every task read — `GET /api/v1/tasks/?user_story_id={story_id}` and
`GET /api/v1/tasks/?workspace_id={workspace_id}` — MUST return only the tasks of each story's
current version (the highest `completed` one), filtered in the SQL statement so the page and its
`total` come from the same filtered query. A story with two completed runs MUST NOT show two task
sets at once. The story-scoped read MUST accept an optional `extraction_id` query parameter that
reads one specific version of that story, and MUST refuse an `extraction_id` that does not belong
to the requested story. A story with no `completed` version MUST answer an empty list, not an
error.

#### Scenario: A second completed run does not double the story's task list

- **GIVEN** a story whose v1 and v2 are both `completed`, v1 with 3 tasks and v2 with 4 tasks
- **WHEN** the client calls `GET /api/v1/tasks/?user_story_id={story_id}`
- **THEN** the response contains only the 4 tasks of v2
- **AND** the response's `total` is 4, not 7

#### Scenario: The workspace task page and its total agree on the filtered set

- **GIVEN** a workspace with one story whose current version has 5 tasks and another story whose
  earlier version holds 10 tasks that a newer run replaced
- **WHEN** the client calls `GET /api/v1/tasks/?workspace_id={workspace_id}`
- **THEN** the returned page contains only tasks that are the highest-`completed` version of their
  story
- **AND** the page's `total` counts the same filtered rows the page returns

#### Scenario: A specific version can be read through extraction_id

- **GIVEN** a story whose v1 is `completed` and holds tasks
- **WHEN** the client calls `GET /api/v1/tasks/?user_story_id={story_id}&extraction_id={v1_id}`
- **THEN** the response contains v1's tasks

#### Scenario: An extraction_id from another story is refused

- **GIVEN** two stories in the same workspace, each with a completed version
- **WHEN** the client calls `GET /api/v1/tasks/?user_story_id={story_a}&extraction_id={story_b_version}`
- **THEN** the backend answers HTTP 422 with `error_code` `REQUEST_VALIDATION_FAILED`
- **AND** no task of story B is returned in any case

#### Scenario: A story with no completed version reads as empty, not broken

- **GIVEN** a story whose only run is `failed`
- **WHEN** the client calls `GET /api/v1/tasks/?user_story_id={story_id}`
- **THEN** the backend answers HTTP 200 with an empty task list

### Requirement: The Story's Versions Are Readable Through One Selector Endpoint

The backend MUST expose `GET /api/v1/stories/{story_id}/versions` returning every version of the
story ordered by `version_number` descending, deliberately unpaginated. Each entry MUST carry `id`,
`version_number`, `status`, `model_used`, `provider`, `temperature`, `created_at`, `completed_at`,
`error_info`, `is_current` and `has_output`. `is_current` MUST be true for exactly the
highest-`completed` version, so a `pending` top version never displaces the current one. Requesting
versions of a story the user cannot access MUST be a visible error, never a silent empty list.

#### Scenario: The selector lists every version and marks the current one

- **GIVEN** a story with three `completed` versions
- **WHEN** the client calls `GET /api/v1/stories/{story_id}/versions`
- **THEN** the response lists all three versions in descending version-number order
- **AND** exactly the entry with `version_number = 3` carries `is_current = true`

#### Scenario: A pending top version does not displace the current one

- **GIVEN** a story with v2 `completed` and v3 `pending`
- **WHEN** the client calls `GET /api/v1/stories/{story_id}/versions`
- **THEN** the entry for v3 appears with `status = "pending"` and `is_current = false`
- **AND** the entry for v2 carries `is_current = true`

#### Scenario: The read is unpaginated by design

- **GIVEN** a story with more versions than the API's standard page size of 20
- **WHEN** the client calls `GET /api/v1/stories/{story_id}/versions`
- **THEN** the response contains every version of the story in one payload
- **AND** no entry is silently truncated

#### Scenario: An inaccessible story is a visible error

- **GIVEN** a story that does not exist or one the requesting user has no access to
- **WHEN** the client calls `GET /api/v1/stories/{story_id}/versions`
- **THEN** the backend answers HTTP 404 with an error detail
- **AND** the response is never a silent HTTP 200 with an empty list

### Requirement: A Failed Version Is Surfaced Honestly

The selector MUST offer a `failed` version with its `error_info`, its model, its provider, its
temperature and its date, and with `has_output = false`. The story view MUST render that absence of
output as an explicit "no output" state, never as an empty board that reads like a successful run
of zero tasks.

#### Scenario: The selector offers the failed version with its error

- **GIVEN** a story whose v1 is `completed` and whose v2 run failed with a recorded error
- **WHEN** the client calls `GET /api/v1/stories/{story_id}/versions`
- **THEN** the v2 entry carries `status = "failed"`, `has_output = false`, and its `error_info`
- **AND** the entry still carries `model_used`, `provider`, `temperature` and `completed_at`

#### Scenario: The failed version's absence of output is rendered, not implied

- **GIVEN** the story view is showing a failed version through the selector
- **WHEN** the page renders the version's tasks
- **THEN** the UI shows a localized "no output" state for that version
- **AND** it does not render an empty task board that could be mistaken for a successful run

### Requirement: Task Creation and Single-Task Deletion Are Retired with 410 Gone

A task MUST be neither created nor deleted by any product path: `POST /api/v1/tasks/` and
`DELETE /api/v1/tasks/{task_id}` MUST both answer HTTP 410 with a `detail` naming the rule (tasks
are only ever born from a run and are never deleted) and an `error_code` —
`TASK_CREATION_ENDPOINT_REMOVED` and `TASK_DELETE_ENDPOINT_REMOVED` respectively — and neither
MUST write or delete anything. Both handlers MUST keep the refusal shape of the walk they run today
(404 `EntityNotFound` for a resource the caller cannot address, 403 `NOT_A_WORKSPACE_MEMBER` for a
non-member), so neither retirement teaches a caller anything about a workspace they are not in.

#### Scenario: Manual task creation is gone and writes nothing

- **GIVEN** a member of a workspace and a story in it
- **WHEN** the client calls `POST /api/v1/tasks/` with any body
- **THEN** the backend answers HTTP 410 with `error_code` `TASK_CREATION_ENDPOINT_REMOVED`
- **AND** the `detail` names the rule that tasks are only born from an extraction run
- **AND** no task row exists after the call

#### Scenario: Single-task deletion is gone and deletes nothing

- **GIVEN** a task that belongs to a completed version
- **WHEN** the client calls `DELETE /api/v1/tasks/{task_id}`
- **THEN** the backend answers HTTP 410 with `error_code` `TASK_DELETE_ENDPOINT_REMOVED`
- **AND** the `detail` names the rule that no product path deletes a single task
- **AND** the task row still exists, still linked to its version

#### Scenario: A non-member learns nothing new from the retired doors

- **GIVEN** a user who is not a member of the workspace that owns a task
- **WHEN** the client calls `DELETE /api/v1/tasks/{task_id}` for that task
- **THEN** the backend answers the refusal the existing membership walk gives today — 403
  `NOT_A_WORKSPACE_MEMBER`, or 404 for a task that does not exist — before the 410 is ever reached
- **AND** the retired door does not disclose whether the task exists to a caller who could not
  address it today

### Requirement: The Task Write Contract Enforces the Field Matrix

`PUT /api/v1/tasks/{task_id}` MUST accept `status` and `labels` in every version state, and
MUST accept `dependencies` only while the task's version is the current one — a `dependencies`
write on a non-current version MUST be rejected with HTTP 409 and `error_code`
`TASK_VERSION_FROZEN`, whose detail names the current version number. The request MUST reject
`title`, `description` and `priority` with HTTP 422 and `error_code`
`REQUEST_VALIDATION_FAILED` in every case and in every version state — the observable failure of
the `extra="forbid"` schema, not a silent ignore. The presence of `dependencies` in the request
body is what counts as a write: an explicit `[]` on a frozen version MUST be refused exactly like
any other dependency write, while a body without the key MUST keep working.

#### Scenario: Status stays editable on a frozen version

- **GIVEN** a task whose version is not the story's current version
- **WHEN** the client calls `PUT /api/v1/tasks/{task_id}` with body `{"status": "done"}`
- **THEN** the backend answers HTTP 200
- **AND** the task's status is persisted as `done`

#### Scenario: Labels stay editable on a frozen version

- **GIVEN** a task whose version is frozen
- **WHEN** the client calls `PUT /api/v1/tasks/{task_id}` with a new `labels` array
- **THEN** the backend answers HTTP 200 and the labels are persisted

#### Scenario: Dependencies are refused once the version is frozen

- **GIVEN** a task whose version is not current
- **WHEN** the client calls `PUT /api/v1/tasks/{task_id}` with body `{"dependencies": ["T1"]}`
- **THEN** the backend answers HTTP 409 with `error_code` `TASK_VERSION_FROZEN`
- **AND** the detail names the story's current version number
- **AND** the task's dependencies are unchanged

#### Scenario: An explicit empty dependencies array is still a write

- **GIVEN** a task whose version is frozen
- **WHEN** the client calls `PUT /api/v1/tasks/{task_id}` with body `{"dependencies": []}`
- **THEN** the backend answers HTTP 409 with `error_code` `TASK_VERSION_FROZEN`
- **AND** no dependency is cleared

#### Scenario: A body without the dependencies key keeps working on a frozen version

- **GIVEN** a task whose version is frozen
- **WHEN** the client calls `PUT /api/v1/tasks/{task_id}` with body `{"status": "review"}`
- **THEN** the backend answers HTTP 200 and does not raise the frozen-version refusal

#### Scenario: Title, description and priority are refused in every case

- **GIVEN** a task on a frozen version and a task on the current version
- **WHEN** the client calls `PUT /api/v1/tasks/{task_id}` with a body containing `title`,
  `description` or `priority` — on either task
- **THEN** the backend answers HTTP 422 with `error_code` `REQUEST_VALIDATION_FAILED`
- **AND** no field of either task changed

#### Scenario: Dependencies remain editable on the current version

- **GIVEN** a task whose version is the story's current version
- **WHEN** the client calls `PUT /api/v1/tasks/{task_id}` with a new `dependencies` array
- **THEN** the backend answers HTTP 200 and the dependencies are persisted

### Requirement: An Exhausted Version Allocation Surfaces as an Explicit Conflict

When a run exhausts its bounded version-number allocation retries, the extraction request MUST
answer HTTP 409 with `error_code` `VERSION_ALLOCATION_CONFLICT` and a detail naming the story and
stating that the run may be retried. The outcome MUST never be an HTTP 500 and MUST never be a
silent success, and no extraction row MUST be written for the failed allocation.

#### Scenario: An exhausted allocation retry is a 409 with a retry hint

- **GIVEN** concurrent allocation attempts on the same story that exhaust the bounded retries
- **WHEN** the extraction request is answered
- **THEN** the backend answers HTTP 409 with `error_code` `VERSION_ALLOCATION_CONFLICT`
- **AND** the detail names the story and says the run may be retried

#### Scenario: The exhausted allocation never degrades to 500 or silent success

- **GIVEN** the same exhausted-allocation condition
- **WHEN** the extraction request is answered
- **THEN** the response status is 409, not 500 and not 202
- **AND** no extraction row exists for the failed allocation

### Requirement: Story Deletion Is the Only Sanctioned Deletion of Versions

`DELETE /api/v1/stories/{story_id}` MUST require the workspace owner or an `ADMIN` (per the
owner-or-`ADMIN` gate), an explicit confirmation whose dialog names the versions it takes, and a
durable deletion record stating who deleted, when, and which version numbers were destroyed. The
deletion MUST remove that story's points from the vector store as part of the same operation, not a
later step: the cleanup MUST run before the relational delete, and a vector-store failure MUST
abort the operation with an explicit error, leaving the story and its versions intact for a retry.
A record of a deletion MUST survive the story it records, and a `MEMBER` MUST be refused. When no
vector store is configured, the cleanup is skipped because no points exist to clean.

#### Scenario: The owner deletes a story with versions and leaves a durable record

- **GIVEN** a story with completed versions v1 and v2, confirmed for deletion by the workspace owner
- **WHEN** `DELETE /api/v1/stories/{story_id}` completes
- **THEN** the story, its versions and their tasks are gone
- **AND** a deletion record exists carrying the acting user, the timestamp and the destroyed
  version numbers 1 and 2
- **AND** no points of that story remain retrievable from the vector store

#### Scenario: The vector cleanup is part of the same operation, not a later step

- **GIVEN** a story with extraction points in the vector store
- **WHEN** the deletion runs
- **THEN** the story's points are removed by the deletion operation itself
- **AND** no later or manual step is required for the points to disappear

#### Scenario: A vector-store failure aborts the delete and preserves the story

- **GIVEN** a story with versions and points in the vector store
- **WHEN** the vector-store cleanup fails during `DELETE /api/v1/stories/{story_id}`
- **THEN** the backend answers an explicit HTTP 5xx error
- **AND** the story, its versions, its tasks and its points all still exist for a retry
- **AND** no deletion record was written

#### Scenario: The deletion record survives the story it records

- **GIVEN** a completed story deletion with its record
- **WHEN** the database is inspected afterwards
- **THEN** the record still exists with actor, timestamp and destroyed version numbers
- **AND** the record holds the story identity as values, not a foreign key the cascade destroyed

#### Scenario: A MEMBER cannot delete a story that has versions

- **GIVEN** a workspace `MEMBER` and a story with completed versions
- **WHEN** the member calls `DELETE /api/v1/stories/{story_id}`
- **THEN** the backend answers HTTP 403 with `error_code`
  `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`
- **AND** the story, its versions and their tasks all still exist

#### Scenario: The confirmation dialog names the versions it takes

- **GIVEN** a story with two versions and its delete dialog opened by the owner or an `ADMIN`
- **WHEN** the confirmation renders
- **THEN** the dialog says the story's 2 versions are destroyed with it
- **AND** cancelling the dialog performs no HTTP request and deletes nothing

#### Scenario: A workspace without a vector store still deletes cleanly

- **GIVEN** an environment where no vector store is configured
- **WHEN** the owner deletes a story with versions
- **THEN** the deletion completes with the record written
- **AND** no vector cleanup is attempted, because no points exist to clean
