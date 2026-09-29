# extraction-versioning Specification

> **Change**: `extraction-versioning-schema`

## ADDED Requirements

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
