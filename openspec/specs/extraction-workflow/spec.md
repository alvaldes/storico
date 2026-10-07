# extraction-workflow Specification

## Requirements

### Requirement: Workspace-Scoped Extraction Client

The frontend extraction API client MUST target the workspace-scoped endpoint
`POST /api/v1/workspaces/{workspace_id}/extract/` and MUST NOT call the
deprecated `/api/v1/extract/` (410 Gone). `workspace_id` MUST be a required
parameter on every extraction call, and the store MUST NOT derive it from a
default. Extracting MUST be restricted to the workspace owner or an `ADMIN`: when
the backend refuses a `MEMBER` with HTTP 403 `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`,
the client MUST surface that code's localized authorization error. Clicking
"Extract" MUST first open a confirmation dialog that states a new version is
created and the current one is frozen — naming the version being frozen and the
new one — and cancelling MUST perform no HTTP request. A successful 202 response
MUST carry the new run's `version_number`, which the store MUST keep with the
extraction.

#### Scenario: Happy path — extraction succeeds after confirmation

- **GIVEN** a user who is the workspace owner or an `ADMIN` is on
  `/[locale]/stories/{storyId}` and a workspace is selected
- **WHEN** the user clicks "Extract", the dialog states that a new version is created and the
  current one freezes, and the user confirms
- **THEN** the frontend calls `POST /api/v1/workspaces/{workspace_id}/extract/`
- **AND** the response carries the new run's `version_number`
- **AND** when the response `status === "completed"` the store stores the tasks under `tasks[storyId]`

#### Scenario: Cancelling the confirmation performs no request

- **GIVEN** the user clicked "Extract" and the confirmation dialog is open
- **WHEN** the user cancels
- **THEN** no HTTP request is issued and no version is created

#### Scenario: The confirmation dialog names the frozen and the new version

- **GIVEN** the story's current version is v2
- **WHEN** the extract confirmation dialog renders
- **THEN** the dialog says that extracting creates v3 and freezes v2
- **AND** it does not show a generic "are you sure?" without the version facts

#### Scenario: No workspace selected

- **GIVEN** `useWorkspaceStore.currentWorkspace?.id` is `undefined` when the user clicks Extract
- **WHEN** the extract handler runs
- **THEN** it MUST short-circuit with a localized "Select a workspace" toast and MUST NOT issue any HTTP request

#### Scenario: A MEMBER is refused extraction with a localized authorization error

- **GIVEN** a workspace `MEMBER` on a story page
- **WHEN** the member confirms "Extract"
- **THEN** the backend answers HTTP 403 with `error_code`
  `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`
- **AND** the client surfaces the code's localized authorization error
- **AND** no extraction is created

### Requirement: Extraction Error Surfacing

The frontend MUST surface extraction failure with a clear, localized error
message and MUST distinguish between HTTP/network errors, an extraction status
`failed` from a successful HTTP response, unauthorized access (HTTP 401), a
permission refusal (HTTP 403 `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`), and the
version-allocation conflict (HTTP 409 `VERSION_ALLOCATION_CONFLICT`). The store
MUST set `error` and clear the extracting flag in every case, the UI MUST render a
toast on failure, and the previous task list MUST be left intact.

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

#### Scenario: Version allocation conflict — HTTP 409 with a retry hint

- **GIVEN** the backend answers HTTP 409 with `error_code` `VERSION_ALLOCATION_CONFLICT` and a
  detail saying the run may be retried
- **WHEN** the store processes the response
- **THEN** the store surfaces the code's localized conflict message with the retry hint and clears
  the extracting flag
- **AND** the failure is never presented as a generic 500 error nor as a success
- **AND** the existing `tasks[storyId]` is left intact

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
