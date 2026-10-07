# extraction-versioning Specification

## Requirements

### Requirement: One Version Per Run, Numbered Per Story

Every extraction run on a user story MUST create exactly one extraction version, numbered
monotonically per story (v1, v2, v3, …). The pair `(user_story_id, version_number)` MUST be unique
in `extractions`, and a version number, once consumed, MUST never be reused for another run.

#### Scenario: Three runs produce three versions

- **GIVEN** a user story with no extractions
- **WHEN** extraction runs three times over that story, each run completing
- **THEN** three extraction rows exist for the story, numbered 1, 2 and 3
- **AND** the third version is the current one

#### Scenario: Duplicate version number is impossible

- **GIVEN** an extraction row with `version_number = 2` for a story
- **WHEN** an insert attempts a second row with `(user_story_id, version_number) = (that story, 2)`
- **THEN** the database rejects the insert through the unique constraint on
  `(user_story_id, version_number)`
- **AND** no duplicate pair exists after the failed insert

#### Scenario: A number is never reused after a story gains versions

- **GIVEN** a story whose highest consumed version number is 4
- **WHEN** a new run is created for that story
- **THEN** it receives version number 5, not a number below 4

### Requirement: Every Run Consumes a Number, Including a Failed One

Every run that reaches row creation MUST consume a version number at the moment the row is born in
`pending`, regardless of the run's eventual outcome. A retry MUST reuse the same extraction row and
MUST NOT mint a second number. The run that fails MUST keep its number and its row.

#### Scenario: A failed run consumes a number and never becomes current

- **GIVEN** a story whose current version is v1 (`status = completed`)
- **WHEN** a new run is created for that story and the LLM call fails
- **THEN** the failed row exists with `version_number = 2` and `status = failed`
- **AND** the current version of the story is still v1
- **AND** the board keeps showing the tasks of v1

#### Scenario: Retry of the same row never mints a second number

- **GIVEN** an extraction row in `pending` with `version_number = 3`
- **WHEN** the runner re-persists that row (retry or terminal write), reusing its id
- **THEN** the row still has `version_number = 3`
- **AND** no second extraction row was created for the run

#### Scenario: A number burned by failures stays burned

- **GIVEN** a story where five consecutive runs failed after consuming numbers 2 through 6, and v1
  is the only completed version
- **WHEN** the next run for that story is created
- **THEN** it receives version number 7

### Requirement: Current Version Is Derived, Never Stored

The current version of a story MUST be derived as the highest `version_number` whose `status` is
`completed`. No stored flag, materialized view or trigger MUST exist to designate it. While a run
is `pending`, the previous current version remains current; a `failed` top version never becomes
current.

#### Scenario: No stored current flag exists after the migration

- **GIVEN** migration `0028` has been applied
- **WHEN** the `extractions` schema is inspected
- **THEN** no `is_current` column, no materialized view and no trigger exists for the current version

#### Scenario: A pending run leaves the previous current version current

- **GIVEN** a story whose current version is v2 (`status = completed`)
- **WHEN** a new run is created and is `pending`
- **THEN** the derived current version of the story is still v2

#### Scenario: Failed top version is never current

- **GIVEN** a story where v3 is the highest version and its `status` is `failed`, with v2
  `completed`
- **WHEN** the current version is derived
- **THEN** the result is v2
- **AND** the v3 row still exists, keeping its number, status and error information

### Requirement: Concurrent Runs Receive Distinct Numbers

Two runs created concurrently for the same story MUST receive two different version numbers. The
unique constraint on `(user_story_id, version_number)` MUST be the collision mechanism, and the
losing allocation MUST recompute and retry a bounded number of times before failing. The failure
MUST be observable — it MUST never be silent.

#### Scenario: Concurrent runs do not collide

- **GIVEN** a story with no extractions
- **WHEN** two runs are created concurrently for that story
- **THEN** one row receives version number 1 and the other version number 2
- **AND** no allocation failed after exhausting the bounded retries

#### Scenario: Collision is retried with a bound and then fails loudly

- **GIVEN** repeated concurrent allocation attempts on the same story
- **WHEN** an allocation loses the race more times than the bounded retry allows
- **THEN** the run fails with an explicit error
- **AND** no extraction row was written with a duplicated `(user_story_id, version_number)` pair

### Requirement: Every Extracted Task Belongs to Its Extraction

Every task created by an extraction run MUST carry a non-null `extraction_id` referencing the
extraction that produced it, persisted at task creation. The existing story-level link
(`tasks.user_story_id`) MUST remain for access by story. Tasks of different versions of the same
story are disjoint rows.

#### Scenario: Task carries its producing run

- **GIVEN** an extraction run completes and generates N tasks
- **WHEN** those tasks are persisted
- **THEN** each task row has a non-null `extraction_id` pointing at that extraction row

#### Scenario: Versions do not share task rows

- **GIVEN** a story with a completed v1 and a completed v2
- **WHEN** the tasks of each version are listed through `extraction_id`
- **THEN** the two task sets have no row in common

#### Scenario: Story-level access link remains

- **GIVEN** a story with tasks across several completed versions
- **WHEN** tasks are listed by `user_story_id`
- **THEN** tasks from all versions of that story are returned

### Requirement: Each Version Freezes Its Run Snapshot at Render Time

Every extraction row MUST store its run identity: provider, model, temperature, and the prompt as
rendered and sent to the provider. This snapshot MUST be written after the prompt is rendered and
before the provider call, so that a run that fails still has a complete input snapshot. The only
legitimately missing snapshot fact is provider token usage, which a call that never answered has
no value for. `prompt_rendered` MUST be null only when the run died before rendering, and it MUST
never be backfilled.

#### Scenario: A failed version has a complete input snapshot and absent output

- **GIVEN** a run whose prompt rendered successfully but whose provider call raised an error
- **WHEN** the failed row is read
- **THEN** `provider`, `model_used`, `temperature` and `prompt_rendered` are all populated
- **AND** the run produced no confidence score and no token usage
- **AND** the raw response holds no generated content

#### Scenario: Prompt rendered is null only when never rendered

- **GIVEN** a run that failed before the render step completed
- **WHEN** the row is read
- **THEN** `prompt_rendered` is null
- **AND** it remains null through any later retry, status change or terminal write

#### Scenario: Terminal writes preserve the snapshot

- **GIVEN** a `pending` row already carrying `version_number`, `provider`, `temperature` and
  `prompt_rendered`
- **WHEN** the run terminates as `completed` or `failed` and the row is persisted
- **THEN** none of the snapshot fields is overwritten with null or a different value

#### Scenario: Declared temperature equals the temperature used

- **GIVEN** an extraction request without an explicit temperature
- **WHEN** the run is created and the LLM call is made
- **THEN** the stored `temperature` equals the temperature passed to the provider call
- **AND** the same holds when the request did carry an explicit temperature

### Requirement: Nothing Inside a Version Is Ever Deleted

No product code path MUST delete an extraction version or a task inside a version. The repository
MUST NOT expose a delete operation for extractions. The only deletion that removes versions is the
story-delete cascade, whose access rules are specified in a later slice.

#### Scenario: No product path deletes a loose version

- **GIVEN** the deployed backend
- **WHEN** the extraction repository and its port are inspected
- **THEN** no delete method exists for extractions
- **AND** no service, route or background task removes an `extractions` row

#### Scenario: Tasks inside a version are never removed

- **GIVEN** a completed version with its task set
- **WHEN** any product operation runs against that story or version
- **THEN** no task row of that version is deleted

#### Scenario: The only deletion is the story cascade

- **GIVEN** a story with several versions and their tasks
- **WHEN** the story row itself is deleted
- **THEN** the versions and tasks are removed only as the database cascade of the story delete
- **AND** no other operation removes them

### Requirement: The Migration Refuses Legacy Data and Never Backfills

Migration `0028` MUST refuse to run — before executing any schema change — when either `extractions`
or `tasks` contains rows, and MUST never assign a default version to legacy rows. It MUST apply
cleanly when both tables are empty.

#### Scenario: Migration refuses a populated database

- **GIVEN** a database where `extractions` or `tasks` holds at least one row
- **WHEN** migration `0028` runs
- **THEN** it fails with an explicit error naming the no-backfill decision
- **AND** no column, table or constraint of `0028` was created

#### Scenario: Migration applies on an empty database

- **GIVEN** a database where both `extractions` and `tasks` are empty
- **WHEN** migration `0028` runs
- **THEN** all of `0028`'s columns, constraints, indexes and the `task_invalidations` table are
  created
- **AND** no existing row was assigned a version number, because none existed

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

### Requirement: The Snapshot Carries the Few-Shot Examples With Their Text

Every extraction row's snapshot MUST include a `few_shots` entry listing each few-shot example
the run actually used, carrying the example's **text** (its story text and task summary) together
with the model that produced it and its similarity score — a point id in the vector store does
not say what the model saw. The entry MUST record what was passed to the render, and MUST agree
with the few-shot section of the stored rendered prompt.

#### Scenario: A completed run's few-shots are readable with their text

- **GIVEN** a run whose search returned two similar extractions and whose prompt was rendered
  with both
- **WHEN** the completed row's snapshot is read
- **THEN** `few_shots` lists both examples, each with its story text and task summary
- **AND** each entry's text matches what the stored rendered prompt shows in its few-shot section

#### Scenario: A failed run keeps its few-shots

- **GIVEN** a run whose prompt rendered with few-shot examples but whose provider call failed
- **WHEN** the failed row's snapshot is read
- **THEN** `few_shots` is present and complete
- **AND** the only legitimately missing snapshot key is the provider's token usage

### Requirement: The Snapshot Carries the Project Context and the Story Text Exactly as Sent

Every extraction row's snapshot MUST include a `project_context` entry describing what was
composed and injected for the run — the project's name and description as they were, the other
stories' text and the existing tasks — and a `story_text` entry holding the story's text exactly
as it was sent. Editing the story afterwards MUST NOT change a stored version's `story_text`.
The snapshot MUST NOT duplicate facts the row already stores elsewhere: the system prompt stays
`prompt_config.system_prompt`, and provider, model, temperature and the rendered prompt stay in
their own columns.

#### Scenario: The project context agrees with the rendered prompt

- **GIVEN** a run whose prompt was rendered with the project's context
- **WHEN** the completed row's snapshot is read
- **THEN** `project_context` records the project name, the description, the other stories and
  the existing tasks that were injected
- **AND** its content matches what the stored rendered prompt shows in its context block

#### Scenario: The story text is frozen as sent

- **GIVEN** a completed version whose `story_text` reads "As a user, I want to log in so that I
  can access my account"
- **WHEN** the story's text is edited afterwards
- **THEN** the version's stored `story_text` is unchanged
- **AND** a subsequent run stores the new text as its own `story_text`

#### Scenario: Nothing is stored twice

- **GIVEN** a completed run
- **WHEN** the row's snapshot is inspected
- **THEN** the system prompt appears only as `prompt_config.system_prompt`
- **AND** provider, model, temperature and the rendered prompt appear only in their own columns,
  not restated as new snapshot keys

### Requirement: The Snapshot Records the Omitted Negative-Example Count

Every extraction row's snapshot MUST include `negative_examples_omitted` as an integer count of
the marks the negative-example block cut — `0` when nothing was cut. The count MUST reflect the
composition of this run's block, so a snapshot with a non-zero count belongs to a prompt whose
negative-example block announced the omission.

#### Scenario: A run with fewer marks than the cap records zero

- **GIVEN** a story with 5 marks across its previous versions
- **WHEN** the next run's snapshot is read
- **THEN** `negative_examples_omitted` is 0

#### Scenario: A run over the cap records the omitted count

- **GIVEN** a story with 21 distinct marks across its previous versions
- **WHEN** the next run's snapshot is read
- **THEN** `negative_examples_omitted` is 1
- **AND** the stored rendered prompt's block announces that 1 older mark was omitted

### Requirement: Token Usage Is Stored Only When the Provider Returned It

When the provider answers with token usage, the run's snapshot MUST record that usage verbatim —
the provider's own mapping, written after the provider answers — so entered and generated tokens
can be separated per run. When a provider returns no usage, the key MUST be absent and the
absence MUST be recorded in the change's verification notes — never zero-filled, never
estimated. The provider's field name MUST be confirmed against a real response of each provider
before its adapter is wired; naming the field is not a requirement of this specification.

#### Scenario: A provider that returns usage has it stored verbatim

- **GIVEN** a provider whose response carries its own usage mapping
- **WHEN** the run completes
- **THEN** the snapshot's `usage` holds that mapping as the provider returned it
- **AND** it was written after the provider answered, in the same snapshot

#### Scenario: A provider that returns no usage leaves the key absent

- **GIVEN** a provider whose response carries no usage information
- **WHEN** the run completes
- **THEN** the snapshot carries no `usage` key
- **AND** nothing fabricates a zero or an estimate in its place
- **AND** the omission is annotated in the change's verification notes

#### Scenario: A failed run has no usage and that is complete honesty

- **GIVEN** a run whose prompt rendered but whose provider call failed
- **WHEN** the failed row's snapshot is read
- **THEN** the snapshot carries no `usage` key
- **AND** every other snapshot key is present

### Requirement: Measurement Derives From Stored Facts, With No New Instrument

A run's duration MUST be derivable as `completed_at - created_at` from the columns the row
already has, its prompt size MUST be measurable offline from the stored rendered prompt, and its
token usage MUST come from the snapshot's `usage` — no timing middleware, no metrics view and no
other new measurement instrument MUST be added.

#### Scenario: Duration and prompt size are derivable from the row alone

- **GIVEN** a completed extraction row
- **WHEN** the run is measured afterwards
- **THEN** the duration comes from the row's own `created_at` and `completed_at`
- **AND** the prompt size comes from the row's stored rendered prompt
- **AND** no middleware or metrics endpoint was added to obtain either

### Requirement: Reproducibility Is the Stored Prompt, Not a Re-Execution Promise

Two runs of the same story with identical provider, model and temperature MAY render **different**
prompts when the project changed in between, and each version MUST keep the text it actually
sent. Comparing two versions MUST be done over their stored prompts and snapshots — stored
facts — and no behaviour MAY promise that re-running a configuration reproduces an earlier
prompt.

#### Scenario: Identical configuration, changed project, different prompts

- **GIVEN** a first run of a story with provider, model and temperature P, and a project change
  — a new story, new tasks or an edited description — completed before a second run of the same
  story with the same P
- **WHEN** the two versions' stored prompts are compared
- **THEN** the prompts differ, because the project context they injected differs
- **AND** each version's stored prompt is exactly the text its own run sent

#### Scenario: The comparison never re-executes

- **GIVEN** two completed versions of the same story
- **WHEN** a reader wants to know why their outputs differ
- **THEN** the answer is read from the two versions' stored prompts and snapshots
- **AND** no step requires or assumes that re-running either configuration would reproduce the
  other's prompt

### Requirement: Both Bench Outcomes Are Honest and Both Are Recorded

The change's verification MUST run both bench obligations and record which outcome each landed
in: the **1 / 50 / 200**-story ladder against a Neon-like database — never the dev pooler —
measuring prompt size, duration and usage when present; and the mandatory **1000**-story project
built through the CSV import, proving the unpaginated context read does not truncate where the
API's page cap would. For either run, exactly two outcomes are legitimate: the measured size and
duration are recorded, **or** the provider rejects the prompt and that run consumes a version
number while producing nothing — recorded as a measured outcome, never retried until it passes.
1000 stories MUST be stated as a **floor**, because the CSV import cap is per uploaded file and
a second import crosses it. No input cap, truncation or input-side pagination MAY be introduced
to make either run pass.

#### Scenario: The ladder is recorded per project

- **GIVEN** three projects of 1, 50 and 200 stories on a Neon-like database
- **WHEN** the bench runs against each of them
- **THEN** the verification records, per project, the prompt size, the run duration and the
  token usage when the provider returned it
- **AND** no measurement was taken against the dev pooler

#### Scenario: The 1000-story bench runs and names its bound

- **GIVEN** a project with 1000 stories created through the CSV import
- **WHEN** the bench runs against it
- **THEN** the verification records the outcome — measured size and duration, or provider
  rejection
- **AND** the record states that 1000 stories came from one import and that a second import
  crosses the count, so 1000 is a floor, not a project maximum

#### Scenario: A provider rejection is a measured outcome, not a failure to retry

- **GIVEN** a project whose composed prompt exceeds the provider's context window
- **WHEN** the bench run attempts extraction on it
- **THEN** the run consumes a version number and produces no tasks
- **AND** the verification records that outcome with the real numbers as the annotated known
  limitation, rather than retrying the run until it passes

#### Scenario: Nothing was added to make a run pass

- **GIVEN** both benches completed
- **WHEN** the extraction path is inspected
- **THEN** no input token cap, no truncation and no input-side pagination were introduced
  anywhere between the story text and the provider call
