# few-shot-retrieval Specification

> **Change**: `extraction-versioning-prompt`

## MODIFIED Requirements

### Requirement: Unified few-shot prompt section

The prompt has a single `## Few-Shot Examples` section from Qdrant. The similarity search that
feeds it MUST NOT return a point belonging to the story being extracted, in **any** of its
versions, and MUST NOT return a point whose extraction carries at least one invalid mark. Both
exclusions MUST be enforced in the search filter itself — never by the caller filtering results
afterwards — and MUST hold regardless of the workspace's few-shot configuration. The search
continues to exclude points that carry no `workspace_id`, as the vector-store-isolation
capability already requires.
(Previously: the section was fed by a workspace-keyed similarity search with no exclusions, so
re-extracting a story could return its own previous run as an example.)

#### Scenario: Examples injected

- **WHEN** similar extractions exist and retrieval is enabled
- **THEN** the prompt contains the section with those examples

#### Scenario: Cold start omits section

- **WHEN** there are no results or retrieval is disabled
- **THEN** the section is omitted

#### Scenario: A story never retrieves its own previous run

- **GIVEN** a story whose completed v1 has its point stored in the vector store
- **WHEN** a second run searches for few-shot examples while extracting that story
- **THEN** the search returns no point belonging to that story, in any of its versions
- **AND** the section, if filled, is filled only with points of other stories

#### Scenario: An extraction with an invalid mark is never an example

- **GIVEN** an extraction of another story that carries at least one task with an active invalid
  mark, and whose point is the most similar above the threshold
- **WHEN** any story searches for few-shot examples
- **THEN** that point is not returned
- **AND** the human's mark improves the next prompt instead of being re-injected as a good
  example

#### Scenario: The most similar contaminated point does not crowd the section

- **GIVEN** a search where the same story's previous run and an invalid-marked extraction both
  score above the threshold, and one valid example of another story also scores above it
- **WHEN** the search runs with `limit = 1`
- **THEN** the returned example is the valid one
- **AND** neither excluded point consumed the limit

## ADDED Requirements

### Requirement: A Point Without the Validity Flag Is Not Treated as Valid

The validity exclusion MUST be fail-closed: a point whose payload does not carry the validity
flag MUST NOT be returned as a few-shot example, exactly as if the flag were set. A negative
condition on the flag would admit points that merely lack the key, so the exclusion is a
positive requirement that the flag be present and false. The release wipes the collections
before the flag exists, so no legacy point is expected to lack it — the fail-closed form is what
keeps that true if one does.

#### Scenario: A point missing the validity flag is not returned

- **GIVEN** a point above the threshold whose payload carries no validity flag
- **WHEN** a search for few-shot examples runs
- **THEN** that point is not returned

#### Scenario: A valid point is still returned

- **GIVEN** a point above the threshold whose payload carries the validity flag set to false and
  no invalid marks on its extraction
- **WHEN** a search for few-shot examples runs
- **THEN** that point is returned as an example
