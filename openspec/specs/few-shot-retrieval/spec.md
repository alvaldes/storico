# few-shot-retrieval Specification

## Requirements

### Requirement: Unified few-shot prompt section

The prompt has a single `## Few-Shot Examples` section from Qdrant.

#### Scenario: Examples injected

- **WHEN** similar extractions exist and retrieval is enabled
- **THEN** the prompt contains the section with those examples

#### Scenario: Cold start omits section

- **WHEN** there are no results or retrieval is disabled
- **THEN** the section is omitted

### Requirement: Retrieval respects config

Retrieval uses the workspace `enabled`/`limit`/`threshold`.

#### Scenario: Limit respected

- **WHEN** `limit=2` and five similar examples exist
- **THEN** at most two are injected

#### Scenario: Search failure is safe

- **WHEN** Qdrant is unreachable
- **THEN** extraction succeeds with no examples
