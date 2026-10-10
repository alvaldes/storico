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
MUST present one section with four format dispositions — the file formats
`CSV`, `JSON` and `Markdown`, plus `Trello`, which is specified by the
`trello-export` capability and sends no file. The panel MUST scope the export
with a cascade — project, then story, then version — where the version selector
is disabled until a story is chosen and at most one target is ever sent: the
panel MUST resolve the scope through one resolver, so a request carrying two
targets is unreachable by construction, with the API's `422` as a backstop.
When the user selects a format and clicks Download, the panel MUST call the
backend export endpoint and trigger a browser download of the returned content.
The panel MUST present the preview returned with `preview=true` read-only, with
a copy button — the text is shown and copied, never submitted back (E2). The
panel MUST NOT write any files to disk itself — the backend is the single
source of serialized bytes.

#### Scenario: The version selector waits for its story

- **GIVEN** a workspace with projects and stories and no story selected
- **WHEN** the user opens the export toolbar
- **THEN** the version selector is disabled
- **AND** when a story and one of its versions are chosen, the export request
  carries that story's `user_story_id` with the version's `extraction_id`, and
  never a second target

### Requirement: Backend Export Endpoint

The backend MUST add a router `export_router` at
`backend/src/storico/api/routes/export.py` with prefix
`/api/v1/workspaces/{workspace_id}/export`, exposing
`GET /api/v1/workspaces/{workspace_id}/export/tasks/` with a `format` query
parameter of `csv`, `json` or `markdown`, the scope query parameters
`project_id`, `user_story_id` and `extraction_id`, and a `preview` flag. The
endpoint MUST authenticate the user, verify workspace access via
`get_workspace_for_user`, aggregate the scoped tasks — by default only the
tasks of each story's current version, filtered in the same SQL statement that
produces the serialization so no superseded version leaks into the file — and
return the serialized content with a `Content-Disposition` attachment header
and the matching `Content-Type`, except when `preview=true` (see the scope,
version and preview requirement). It MUST NOT write to the server filesystem.
The router MUST be registered on the app.

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
- **WHEN** the user downloads the export in any file format
- **THEN** the file contains exactly the 4 tasks of v2 for that story
- **AND** no task of v1 appears in the file

#### Scenario: A story whose only run failed contributes nothing and breaks nothing

- **GIVEN** a workspace with a story whose only run is `failed`
- **WHEN** the user downloads the export in any file format
- **THEN** the download succeeds and that story contributes no tasks
- **AND** the file remains valid for its format

### Requirement: Export Scope, Version and Preview

The export MUST resolve exactly one scope (E1): no target exports the whole
workspace; `project_id` exports one project; `user_story_id` exports one story.
A request carrying both `project_id` and `user_story_id` MUST be refused with
`422 REQUEST_VALIDATION_FAILED` — the same rule `resolve_export_scope` applies
to the Trello trigger and preview. A target that exists but does not belong to
the path workspace MUST be refused with `403`; a missing one with `404`.

A version MUST be identified by its `extraction_id`, never by a version
number, which is a position in a history the next run moves. `extraction_id`
MUST be accepted only beside its `user_story_id`: a version asked without its
story — at project or workspace level — MUST be refused with `422`. With both,
the endpoint MUST export that version's tasks exactly as that run left them,
even when a newer run has superseded it; without `extraction_id`, each story's
current version is exported.

`preview=true` MUST return the same body the download returns — the same
endpoint, the same parameters, one code path — without the
`Content-Disposition` attachment header. One serialization, two dispositions:
what the preview shows cannot differ from what the download saves, because
they are the same bytes.

#### Scenario: Two targets in one request are refused

- **GIVEN** a selected workspace
- **WHEN** the export request carries both `project_id` and `user_story_id`
- **THEN** the backend answers `422 REQUEST_VALIDATION_FAILED` and serializes nothing

#### Scenario: A chosen version is exported as it was

- **GIVEN** a story whose v1 and v2 are both `completed`, v1 with 3 tasks and
  v2 with 4 tasks
- **WHEN** the export request carries that story's `user_story_id` and the
  `extraction_id` of v1
- **THEN** the file contains exactly the 3 tasks of v1
- **AND** no task of v2 appears in the file

#### Scenario: A version without its story is refused

- **GIVEN** a selected workspace
- **WHEN** the export request carries an `extraction_id` and no `user_story_id`
- **THEN** the backend answers `422 REQUEST_VALIDATION_FAILED`

#### Scenario: The preview is the download without the attachment header

- **GIVEN** a workspace with tasks
- **WHEN** the same endpoint is called twice with the same format and scope,
  once with `preview=true` and once without
- **THEN** the two bodies are identical
- **AND** only the download response carries `Content-Disposition`

### Requirement: Export Format Schemas

**JSON format** MUST return a top-level array of task objects matching the shape
used by the existing `GET /api/v1/tasks/` endpoint — no envelope. **Markdown
format** MUST produce a document with one section per story, grouped under
`## {story raw text}`, each task as a `- **{title}** — {description}` bullet.
Labels render inline as `#label`; dependencies render as `→ {title}` references.
**CSV format** MUST produce one row per task, written through the `csv` module
so a description containing a newline or a comma travels quoted and survives
the round trip. The first row is the header, and the columns are a contract in
this exact order: `story, version, title, description, status, priority,
labels, dependencies` — `story` is the story's raw text, `version` the version
number of the run that produced the task, and the multi-value cells (`labels`,
`dependencies`) are joined with `;`. Adding a column later is compatible;
renaming or reordering one is not.

#### Scenario: The CSV file parses back to its tasks

- **GIVEN** a workspace with tasks carrying labels and dependencies, and a
  description containing a comma and a newline
- **WHEN** the user downloads the CSV export
- **THEN** the file has the header row in contract order and one row per task
- **AND** labels and dependencies are `;`-joined inside their cells, and the
  multi-line description stays inside its quoted cell

#### Scenario: Empty workspace — no tasks

- **GIVEN** a workspace is selected but has zero tasks
- **WHEN** the user downloads any format
- **THEN** the backend returns valid but empty content (`[]` for JSON, an empty
  Markdown header for Markdown, a header-only CSV for CSV)
- **AND** the browser downloads the file with no error toast

### Requirement: Export Error Handling

The endpoint MUST return HTTP 400 for an unknown `format` value and HTTP 401 for
unauthenticated requests. The frontend panel MUST show a localized error toast
on any non-2xx and MUST offer to retry.

#### Scenario: Unknown format — HTTP 400

- **GIVEN** the panel requests a `format` other than `csv`, `json` or `markdown`
- **WHEN** the request reaches the backend
- **THEN** the backend returns HTTP 400 with an error detail
- **AND** the panel shows a localized error toast and offers retry

#### Scenario: Unauthorized — HTTP 401

- **GIVEN** the user's session has expired
- **WHEN** the panel calls the export endpoint
- **THEN** the backend returns HTTP 401
- **AND** the panel shows a localized auth error toast
