# extraction-workflow Specification

## Requirements

### Requirement: Workspace-Scoped Extraction Client

The frontend extraction API client MUST target the workspace-scoped endpoint
`POST /api/v1/workspaces/{workspace_id}/extract/` and MUST NOT call the
deprecated `/api/v1/extract/` (410 Gone). `workspace_id` MUST be a required
parameter on every extraction call, and the store MUST NOT derive it from a
default.

#### Scenario: Happy path — extraction succeeds

- **GIVEN** a user is on `/[locale]/stories/{storyId}` and a workspace is selected
- **WHEN** the user clicks "Extract"
- **THEN** the frontend calls `POST /api/v1/workspaces/{workspace_id}/extract/`
- **AND** when the response `status === "completed"` the store stores the tasks under `tasks[storyId]`

#### Scenario: No workspace selected

- **GIVEN** `useWorkspaceStore.currentWorkspace?.id` is `undefined` when the user clicks Extract
- **WHEN** the extract handler runs
- **THEN** it MUST short-circuit with a localized "Select a workspace" toast and MUST NOT issue any HTTP request

### Requirement: Extraction Error Surfacing

The frontend MUST surface extraction failure with a clear, localized error
message and MUST distinguish between HTTP/network errors, an extraction status
`failed` from a successful HTTP response, and unauthorized access (HTTP 401).
The store MUST set `error` and clear the extracting flag in every case, the UI
MUST render a toast on failure, and the previous task list MUST be left intact.

#### Scenario: LLM offline — extraction status `failed`

- **GIVEN** the backend returns HTTP 200 with body `{ status: "failed", error_info: "Ollama unreachable" }`
- **WHEN** the store processes the response
- **THEN** the store sets the localized extraction-failure error and clears the extracting flag
- **AND** it does NOT replace the existing `tasks[storyId]`

#### Scenario: HTTP error — backend unreachable

- **GIVEN** the LLM service or backend is unreachable (network error / HTTP 5xx)
- **WHEN** `extractTasks()` throws
- **THEN** the store catches the error, sets the error from the exception, and clears the extracting flag
- **AND** the UI shows the error toast with the raw message

### Requirement: Unauthorized Access Handling

When the extraction endpoint returns HTTP 401 the frontend MUST treat it as an
auth failure, not a generic extraction failure, and SHOULD prompt
re-authentication. The store MUST NOT mark the extraction status as `failed`
for a 401 — it MUST surface an auth-specific error.

#### Scenario: Unauthorized — HTTP 401

- **GIVEN** the user's session has expired
- **WHEN** `extractTasks()` receives HTTP 401
- **THEN** the store surfaces the auth-specific error key and clears the extracting flag
- **AND** the UI shows an auth-themed toast; extraction status is NOT marked `failed`
