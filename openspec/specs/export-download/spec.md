# export-download Specification

## Requirements

### Requirement: Export Page Route

The frontend MUST expose a route at `/[locale]/export` rendered by
`frontend/src/pages/[locale]/export.astro`. The page MUST use the existing
`MainLayout.astro` and MUST pass `locale` to the React island.

#### Scenario: No workspace selected

- **GIVEN** `useWorkspaceStore.currentWorkspace` is null
- **WHEN** the user navigates to `/[locale]/export`
- **THEN** the panel shows a localized "Select a workspace" empty state and the Download button is disabled

### Requirement: Export Panel Component

`ExportPanel.tsx` MUST read `workspaceId` from `useWorkspaceStore`. The panel
MUST present two format options, `JSON` and `Markdown`. When the user selects a
format and clicks Download, the panel MUST call the backend export endpoint and
trigger a browser download of the returned content. The panel MUST NOT write any
files to disk itself — the backend is the single source of serialized bytes.

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

### Requirement: Export Format Schemas

**JSON format** MUST return a top-level array of task objects matching the shape
used by the existing `GET /api/v1/tasks/` endpoint — no envelope. **Markdown
format** MUST produce a document with one section per story, grouped under
`## {story raw text}`, each task as a `- **{title}** — {description}` bullet.
Labels render inline as `#label`; dependencies render as `→ {title}` references.

#### Scenario: Empty workspace — no tasks

- **GIVEN** a workspace is selected but has zero tasks
- **WHEN** the user downloads any format
- **THEN** the backend returns valid but empty content (`[]` for JSON, an empty Markdown header for Markdown)
- **AND** the browser downloads the file with no error toast

### Requirement: Export Error Handling

The endpoint MUST return HTTP 400 for an unknown `format` value and HTTP 401 for
unauthenticated requests. The frontend panel MUST show a localized error toast
on any non-2xx and MUST offer to retry.

#### Scenario: Unknown format — HTTP 400

- **GIVEN** the panel requests a `format` other than `json` or `markdown`
- **WHEN** the request reaches the backend
- **THEN** the backend returns HTTP 400 with an error detail
- **AND** the panel shows a localized error toast and offers retry

#### Scenario: Unauthorized — HTTP 401

- **GIVEN** the user's session has expired
- **WHEN** the panel calls the export endpoint
- **THEN** the backend returns HTTP 401
- **AND** the panel shows a localized auth error toast
