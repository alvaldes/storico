# vector-store-isolation Specification

> **Change**: `extraction-versioning-prompt`

## MODIFIED Requirements

### Requirement: Workspace-scoped retrieval

Retrieval returns only examples from the same workspace, and never a point of the story being
extracted nor a point whose extraction carries at least one invalid mark. The search filter
MUST be a positive/negative expression: the story exclusion is a negative condition on the
excluded story's points, and the validity exclusion is a positive condition on
`has_invalid_tasks = false`, so a point that merely lacks the key is not admitted. The caller
MUST name the story being extracted to the search — the exclusion is not optional configuration.
(Previously: the filter was a single workspace-keyed positive expression with no exclusions, and
the search accepted no story to exclude.)

#### Scenario: Cross-workspace isolated

- **WHEN** a search runs in workspace A
- **THEN** only workspace A examples are returned

#### Scenario: Payload carries workspace_id

- **WHEN** an extraction is stored
- **THEN** the point payload includes `workspace_id`

#### Scenario: Same-story points are excluded by the filter

- **GIVEN** a workspace where the most similar point above the threshold belongs to the story
  being extracted
- **WHEN** the search runs for that story
- **THEN** the search returns no point of that story
- **AND** no caller-side filtering was needed to achieve it

#### Scenario: Invalid-marked extractions are excluded by the filter

- **GIVEN** a workspace where a point above the threshold belongs to an extraction carrying at
  least one active invalid mark
- **WHEN** any search runs in that workspace
- **THEN** that point is not returned

#### Scenario: A point missing the validity flag is not admitted

- **GIVEN** a point above the threshold whose payload does not carry `has_invalid_tasks`
- **WHEN** a search runs
- **THEN** that point is not returned
- **AND** the missing key is never read as "valid"

### Requirement: Legacy points excluded

Points without `workspace_id` are excluded from filtered searches, and the same fail-closed
posture extends to the validity flag: a point that does not carry `has_invalid_tasks` is not
treated as valid and is excluded like a point whose flag is set.
(Previously: the exclusion covered only points without `workspace_id`.)

#### Scenario: Untagged point hidden

- **WHEN** a filtered search runs
- **THEN** legacy untagged points are not returned

#### Scenario: A point without the validity flag is hidden

- **WHEN** a filtered search runs against a point whose payload lacks `has_invalid_tasks`
- **THEN** that point is not returned

### Requirement: Payload index

Keyword payload indexes on `workspace_id`, `project_id` and `has_invalid_tasks` keep every
filtered search — workspace scoping, project filtering and validity exclusion — fast.
(Previously: only `workspace_id` carried a payload index.)

#### Scenario: Indexes created

- **WHEN** the collection is ensured
- **THEN** `workspace_id`, `project_id` and `has_invalid_tasks` payload indexes all exist

## ADDED Requirements

### Requirement: Every Stored Point Carries the Project, Version and Validity Keys

Every point stored for an extraction MUST carry, alongside its existing payload keys,
`project_id` (the owning project), `version_number` (the run's version number) and
`has_invalid_tasks` (a boolean). The validity flag MUST be stored as `false` at store time: a
point is stored after its run's tasks are created, and no task can be marked before it exists.

#### Scenario: The payload carries the three new keys

- **GIVEN** a completed run of version 2 of a story in project P
- **WHEN** the run's point is stored
- **THEN** the payload includes `project_id` = P, `version_number` = 2 and `has_invalid_tasks` =
  false
- **AND** the pre-existing payload keys are unchanged

#### Scenario: The version number is the run's own

- **GIVEN** two completed runs of the same story, versions 1 and 2
- **WHEN** both points are stored
- **THEN** each point's `version_number` matches its own run's version number
- **AND** the two points remain distinct rows

### Requirement: The Validity Flag Tracks the Marks, Not the Write Time

The `has_invalid_tasks` flag of an extraction's point MUST be refreshed when a mark is created
on any task of that extraction — to `true` — and when a mark on it is revoked — recomputed from
the marks still active on that extraction, never assumed `false`. The refresh MUST address the
point whose identity is the extraction's own id, so no search is needed to find it. A refresh
failure MUST leave the mark unpersisted, so a mark is never confirmed over a vector store that
still returns the run it condemns; when no vector store is configured there is nothing to
refresh and the mark proceeds.

#### Scenario: Marking sets the flag

- **GIVEN** an extraction whose point carries `has_invalid_tasks = false`
- **WHEN** a task of that extraction is marked invalid
- **THEN** the point's flag is refreshed to `true`
- **AND** the extraction is excluded from subsequent few-shot searches

#### Scenario: Revoking with another active mark keeps the flag

- **GIVEN** an extraction with two active marks and its flag at `true`
- **WHEN** one of the two marks is revoked
- **THEN** the flag is recomputed and stays `true`
- **AND** the extraction remains excluded

#### Scenario: Revoking the last active mark clears the flag

- **GIVEN** an extraction with exactly one active mark and its flag at `true`
- **WHEN** that mark is revoked
- **THEN** the flag is recomputed as `false`
- **AND** the extraction becomes eligible for few-shot retrieval again

#### Scenario: A refresh failure leaves no mark persisted

- **GIVEN** a vector store that fails the refresh
- **WHEN** a task of the extraction is marked invalid
- **THEN** the refresh failure surfaces before the mark is confirmed
- **AND** no mark row exists afterwards
- **AND** the point's flag and the marks agree: the flagged-out state is never silently lost

#### Scenario: No vector store configured

- **GIVEN** an environment with no vector store configured
- **WHEN** a task is marked invalid and later revoked
- **THEN** both operations proceed
- **AND** no refresh is attempted, because no points exist to refresh
