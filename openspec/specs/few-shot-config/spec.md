# few-shot-config Specification

## Requirements

### Requirement: Workspace retrieval configuration

Each workspace stores `enabled`, `limit`, and `threshold` with defaults.

#### Scenario: Defaults applied

- **WHEN** a workspace has no prompt row
- **THEN** `enabled=true`, `limit=3`, `threshold=0.85`

#### Scenario: Config updated

- **WHEN** an admin saves `{enabled:false, limit:5, threshold:0.9}`
- **THEN** a subsequent read returns those values

#### Scenario: Out-of-range rejected

- **WHEN** `limit=0` or `threshold=1.5`
- **THEN** the API returns 422 and persists nothing

### Requirement: Admin-only config write

Only workspace admins may change retrieval config.

#### Scenario: Non-admin rejected

- **WHEN** a non-admin updates the config
- **THEN** the API returns 403 and nothing changes

### Requirement: Legacy manual examples removed

The API no longer accepts `few_shot_examples`.

#### Scenario: Legacy input rejected

- **WHEN** a member posts `few_shot_examples`
- **THEN** the API returns 422
