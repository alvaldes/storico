# export-download Specification

> **Change**: `extraction-versioning-api`

## MODIFIED Requirements

### Requirement: Backend Export Endpoint

The backend MUST add a router `export_router` at
`backend/src/storico/api/routes/export.py` with prefix
`/api/v1/workspaces/{workspace_id}/export`, exposing
`GET /api/v1/workspaces/{workspace_id}/export/tasks/` with a `format` query
parameter of `json` or `markdown`. The endpoint MUST authenticate the user,
verify workspace access via `get_workspace_for_user`, aggregate the workspace's
tasks — only the tasks of each story's current version, filtered in the same
SQL statement that produces the serialization so no superseded version leaks
into the file — and return the serialized content with a `Content-Disposition`
attachment header and the matching `Content-Type`. It MUST NOT write to the
server filesystem. The router MUST be registered on the app.

#### Scenario: Happy path — JSON download

- **GIVEN** a workspace is selected and contains tasks
- **WHEN** the user selects JSON and clicks Download
- **THEN** the panel calls `GET /api/v1/workspaces/{workspace_id}/export/tasks/?format=json`
- **AND** the backend returns `Content-Type: application/json` with an attachment filename
- **AND** the browser downloads the file with valid JSON array contents

#### Scenario: Happy path — Markdown download

- **GIVEN** a workspace is selected and contains tasks
- **WHEN** the user selects Markdown and clicks Download
- **THEN** the panel calls the same endpoint with `?format=markdown`
- **AND** the backend returns `Content-Type: text/markdown` with an attachment filename
- **AND** the downloaded file groups tasks under per-story `## {story}` sections with the specified bullet format

#### Scenario: The export contains only the current version's tasks

- **GIVEN** a workspace with a story whose v1 and v2 are both `completed`, v1 with 3 tasks and
  v2 with 4 tasks
- **WHEN** the user downloads the export in either format
- **THEN** the file contains exactly the 4 tasks of v2 for that story
- **AND** no task of v1 appears in the file

#### Scenario: A story whose only run failed contributes nothing and breaks nothing

- **GIVEN** a workspace with a story whose only run is `failed`
- **WHEN** the user downloads the export in either format
- **THEN** the download succeeds and that story contributes no tasks
- **AND** the file remains valid for its format
