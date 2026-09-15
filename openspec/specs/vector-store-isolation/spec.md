# vector-store-isolation Specification

## Requirements

### Requirement: Workspace-scoped retrieval

Retrieval returns only examples from the same workspace.

#### Scenario: Cross-workspace isolated

- **WHEN** a search runs in workspace A
- **THEN** only workspace A examples are returned

#### Scenario: Payload carries workspace_id

- **WHEN** an extraction is stored
- **THEN** the point payload includes `workspace_id`

### Requirement: Legacy points excluded

Points without `workspace_id` are excluded from filtered searches.

#### Scenario: Untagged point hidden

- **WHEN** a filtered search runs
- **THEN** legacy untagged points are not returned

### Requirement: Seed migration

Legacy manual examples migrate into Qdrant as workspace seeds.

#### Scenario: Idempotent seed

- **WHEN** the seed job runs twice
- **THEN** each example exists exactly once

### Requirement: Payload index

A keyword payload index on `workspace_id` keeps filtered search fast.

#### Scenario: Index created

- **WHEN** the collection is ensured
- **THEN** a `workspace_id` payload index exists
