# Delta Spec: User Story → Tasks Decomposition Workflow

Change: `us-decomposition`
Mode: openspec
Status: All workstreams are NEW or MODIFY behavior; no prior main specs exist for these domains except `extraction-workflow` (none tracked).

This delta covers four workstreams described in `openspec/changes/us-decomposition/proposal.md`:

1. **Bugfix — Workspace-Scoped Extraction** (modifies `extraction-workflow`)
2. **Kanban Board Page** (adds `kanban-board`)
3. **Task Editor** (adds `task-editor`)
4. **Export Page** (adds `export-download`)

File-impact conventions: "New" = created file; "Modified" = existing file edited in place. All new Astro pages live at `frontend/src/pages/[locale]/<page>.astro`. All new React islands live at `frontend/src/components/react/<Island>.tsx`.

---

## Domain: extraction-workflow

### ADDED Requirements

#### Requirement: Workspace-Scoped Extraction Client

The frontend extraction API client MUST target the workspace-scoped endpoint `POST /api/v1/workspaces/{workspace_id}/extract/` and MUST NOT call the deprecated `/api/v1/extract/` (410 Gone). The `workspace_id` MUST be a required parameter on every extraction call.

Rationale: the backend router at `backend/src/storico/api/routes/extraction.py` only accepts the workspace-scoped path; the legacy router returns 410.

**Files**:
- Modified: `frontend/src/lib/tasks-api.ts` — `extractTasks()` signature: `(workspaceId: string, storyId: string, options?)` and URL `POST /api/v1/workspaces/${workspaceId}/extract/`.
- Modified: `frontend/src/stores/taskStore.ts` — `extractTasks` action accepts `workspaceId`, forwards to API client; store MUST NOT derive workspace_id from a default.
- Modified: `frontend/src/components/react/StoryDetail.tsx` — reads `workspaceId` from `useWorkspaceStore` and passes it to `extractTasks(workspaceId, storyId)`.
- Modified: `frontend/src/components/react/StoriesList.tsx` — no direct extraction call; MUST provide workspace context (already present via `useWorkspaceStore`) so children can read it.

#### Requirement: Extraction Error Surfacing

The frontend MUST surface extraction failure with a clear, localized error message and MUST distinguish between: (a) HTTP/network errors, (b) extraction status `failed` from a successful HTTP response, (c) unauthorized access (HTTP 401).

The store MUST set `error` and `extracting: false` on any of these states. The UI MUST render a toast on failure and MUST leave the previous task list intact (no destructive clear).

#### Requirement: Unauthorized Access Handling

When the extraction endpoint returns HTTP 401, the frontend MUST treat it as an auth failure (not a generic extraction failure) and SHOULD prompt re-authentication. The store MUST NOT mark extraction status as `failed` for 401s — it MUST mark `error` with an auth-specific message key.

### Scenarios

#### Scenario: Happy path — extraction succeeds

- GIVEN a user is on `/[locale]/stories/{storyId}` and a workspace is selected in `useWorkspaceStore`
- WHEN the user clicks the "Extract" button in `StoryDetail.tsx`
- THEN the frontend calls `POST /api/v1/workspaces/{workspace_id}/extract/` with `{ user_story_id, model, temperature, run_validation: false }`
- AND the store sets `extracting: true` during the request, then `extracting: false` on response
- AND when the response `status === "completed"`, the store stores `result.tasks` under `tasks[storyId]` and the UI renders them inside the story's task list

#### Scenario: LLM offline — extraction status `failed`

- GIVEN the backend returns HTTP 200 with body `{ status: "failed", error_info: "Ollama unreachable" }`
- WHEN the store processes the response
- THEN the store sets `error` to the localized extraction-failure message, `extracting: false`
- AND does NOT replace the existing `tasks[storyId]` (preserves prior tasks if any)
- AND `StoryDetail.tsx` renders an error toast via `sonner`

#### Scenario: HTTP error — backend unreachable

- GIVEN the LLM service or backend is unreachable (network error/HTTP 5xx)
- WHEN `extractTasks()` throws
- THEN the store catches the error, sets `error` from `err.message`, sets `extracting: false`
- AND the UI shows the error toast with the raw message

#### Scenario: Unauthorized — HTTP 401

- GIVEN the user's session has expired
- WHEN `extractTasks()` receives HTTP 401
- THEN the store sets `error` to `t.stories.extraction_unauthorized` (auth-specific key) and `extracting: false`
- AND the UI shows an auth-themed toast; extraction status is NOT marked `failed`

#### Scenario: No workspace selected

- GIVEN `useWorkspaceStore.currentWorkspace?.id` is `undefined` when the user clicks Extract
- WHEN `StoryDetail.handleExtract` runs
- THEN the handler MUST short-circuit with a localized "Select a workspace" toast and MUST NOT issue any HTTP request

### Acceptance Criteria

- [ ] `tasks-api.ts:extractTasks()` first parameter is `workspaceId: string`; URL is `/api/v1/workspaces/${workspaceId}/extract/`
- [ ] No remaining call to `/api/v1/extract/` in the frontend codebase
- [ ] `taskStore.extractTasks(workspaceId, storyId)` signature; missing `workspaceId` triggers the "No workspace" toast, not an HTTP call
- [ ] `StoryDetail.tsx` reads `workspaceId` from `useWorkspaceStore` and passes it through
- [ ] Error states (failed/network/401) produce distinct toast messages
- [ ] On any error, prior `tasks[storyId]` is preserved

---

## Domain: kanban-board

### ADDED Requirements

#### Requirement: Kanban Page Route

The frontend MUST expose a route at `/[locale]/kanban` rendered by `frontend/src/pages/[locale]/kanban.astro`. The page MUST be wired into the existing sidebar navigation and MUST use the existing `MainLayout.astro`. The page MUST pass `locale` to the React island.

**Files**:
- New: `frontend/src/pages/[locale]/kanban.astro`
- Modified: `frontend/src/i18n/en.json`, `es.json` (new `kanban` section — see i18n keys below)

#### Requirement: Kanban Board Component

The page MUST render a single React island `KanbanBoard.tsx` at `frontend/src/components/react/KanbanBoard.tsx`. The island MUST use `@hello-pangea/dnd` for drag-and-drop. The board MUST display exactly five columns in this fixed order: `Backlog → To Do → In Progress → Review → Done`.

The column a task belongs to MUST be derived from `task.status`.

#### Requirement: Kanban Task Fetching

`KanbanBoard.tsx` MUST fetch tasks via the existing `GET /api/v1/tasks/?workspace_id={workspaceId}` endpoint (already implemented in backend `tasks.py`). The island MUST read `workspaceId` from `useWorkspaceStore.currentWorkspace?.id`. If no workspace is selected, the island MUST show a localized empty-state prompting the user to select a workspace; it MUST NOT issue a request.

The existing `taskStore.ts` MUST be extended with a `fetchTasksForWorkspace(workspaceId)` action that calls the same endpoint and stores results under a top-level `workspaceTasks: Task[]` slot (separate from the per-story `tasks` map, to avoid mixing scopes).

#### Requirement: Kanban Drag-and-Drop Status Update

When a task is dragged from one column to another and dropped, the island MUST call `PUT /api/v1/tasks/{taskId}` with `{ status: <new_status> }` (the endpoint already exists). The UI MUST optimistically move the card to the target column and MUST roll back on HTTP failure with an error toast. While the PUT is in flight, the card MUST show a subtle loading indicator and MUST NOT be re-draggable.

The five valid status values MUST match the backend task status enum: `backlog`, `todo`, `in_progress`, `review`, `done`.

#### Requirement: Kanban Empty States

The island MUST handle two distinct empty states:
- Workspace selected, no tasks → localized "No tasks yet" empty state with a hint to extract tasks from a story.
- No workspace selected → localized "Select a workspace" prompt.

### Scenarios

#### Scenario: Happy path — board loads tasks

- GIVEN a workspace is selected in `useWorkspaceStore`
- WHEN the user navigates to `/[locale]/kanban`
- THEN `KanbanBoard.tsx` calls `fetchTasksForWorkspace(workspaceId)` and `GET /api/v1/tasks/?workspace_id=...` returns the workspace's tasks
- AND tasks are grouped into five columns based on `task.status`
- AND every status enum value (`backlog`, `todo`, `in_progress`, `review`, `done`) maps to exactly one column

#### Scenario: Drag-and-drop updates task status

- GIVEN the board is loaded with at least one task in the `Backlog` column
- WHEN the user drags the task card from `Backlog` to `To Do` and drops it
- THEN the island optimistically updates the card's column and calls `PUT /api/v1/tasks/{taskId}` with `{ status: "todo" }`
- AND on HTTP 200, the card stays in `To Do`; `taskStore` updates the task object
- AND on HTTP failure (4xx/5xx), the card rolls back to `Backlog` and a localized error toast appears

#### Scenario: No workspace selected

- GIVEN `useWorkspaceStore.currentWorkspace` is null
- WHEN the user navigates to `/[locale]/kanban`
- THEN the island shows the localized "Select a workspace" prompt and issues NO HTTP request

#### Scenario: Workspace selected with zero tasks

- GIVEN a workspace is selected and `fetchTasksForWorkspace` returns `[]`
- WHEN the board renders
- THEN the island shows the localized "No tasks yet" empty state with the link/copy directing the user to extract tasks from a story

#### Scenario: Drag in flight blocks re-drag

- GIVEN a drag-and-drop PUT is in flight
- WHEN the user attempts to drag the same card again
- THEN the card is locked (not draggable) and shows a loading indicator until the PUT completes

### i18n Keys (NEW)

```
kanban.title                    : "Kanban Board" | "Tablero Kanban"
kanban.description              : "Tasks across all stories, grouped by status."
kanban.column_backlog           : "Backlog"     | "Pendiente"
kanban.column_todo              : "To Do"       | "Por Hacer"
kanban.column_in_progress       : "In Progress" | "En Progreso"
kanban.column_review            : "Review"      | "Revisión"
kanban.column_done              : "Done"        | "Hecho"
kanban.empty_no_workspace       : "Select a workspace to view its Kanban board." | "Selecciona un workspace para ver su tablero Kanban."
kanban.empty_no_tasks           : "No tasks yet. Extract tasks from a user story to populate the board." | "Aún no hay tareas. Extrae tareas de una historia de usuario para poblar el tablero."
kanban.empty_no_tasks_link      : "Go to stories" | "Ir a historias"
kanban.status_update_error      : "Failed to update task status. Moved back." | "No se pudo actualizar el estado de la tarea. Se restauró."
kanban.status_updating          : "Saving..."   | "Guardando..."
```

### Acceptance Criteria

- [ ] Route `/[locale]/kanban` exists and renders `KanbanBoard.tsx` inside `MainLayout.astro`
- [ ] Board has exactly five columns in fixed order `Backlog → To Do → In Progress → Review → Done`
- [ ] Drag-and-drop uses `@hello-pangea/dnd` and triggers `PUT /api/v1/tasks/{id}` with new status
- [ ] Optimistic update with rollback on failure
- [ ] Drag locked during PUT in flight
- [ ] No workspace → empty state, no HTTP request
- [ ] Zero tasks → distinct empty state with link to stories
- [ ] `en.json` and `es.json` both contain the `kanban` section above

---

## Domain: task-editor

### ADDED Requirements

#### Requirement: Task Editor Component

The frontend MUST add `TaskEditor.tsx` at `frontend/src/components/react/TaskEditor.tsx`. The component MUST be a modal/dialog built on the existing shadcn `Dialog` primitive. It MUST edit four fields: `title` (text input), `description` (textarea), `labels` (tag input — each label rendered as a removable chip, Enter key to add), `dependencies` (multi-select of sibling tasks within the same story, by `task.id`).

#### Requirement: Task Editor Trigger

`StoryDetail.tsx` MUST render an inline "Edit" button on each task card. Clicking the button MUST open `TaskEditor` pre-populated with the task's current values. The button MUST be disabled while the story is extracting tasks.

**Files**:
- New: `frontend/src/components/react/TaskEditor.tsx`
- Modified: `frontend/src/components/react/StoryDetail.tsx` — add edit button per task card; lift local `editingTask` state
- Modified: `frontend/src/i18n/en.json`, `es.json` — new `taskEditor` section

#### Requirement: Task Editor Persistence

On submit, `TaskEditor` MUST call `PUT /api/v1/tasks/{taskId}` (existing endpoint) with the edited fields. The component MUST optimistically update `taskStore` and MUST roll back on HTTP failure. Success MUST show a localized toast; failure MUST show a localized error toast and keep the dialog open with the user's edits intact (no data loss).

#### Requirement: Labels and Dependencies Validation

The component MUST reject empty labels and MUST deduplicate label input (case-insensitive). Dependencies MUST be limited to tasks from the same story; the editor MUST NOT allow self-dependency (a task cannot depend on itself).

### Scenarios

#### Scenario: Happy path — edits persist

- GIVEN a user is on `/[locale]/stories/{storyId}` and at least one task card is rendered
- WHEN the user clicks the task's Edit button, modifies `title` and adds the label `frontend`, then clicks Save
- THEN `TaskEditor` calls `PUT /api/v1/tasks/{taskId}` with the new payload
- AND on HTTP 200, `taskStore.updateTask(taskId, updates)` runs and the card re-renders with the new title and labels
- AND a success toast appears and the dialog closes

#### Scenario: Save failure — rollback without data loss

- GIVEN the user has edited fields in `TaskEditor`
- WHEN `PUT /api/v1/tasks/{taskId}` returns HTTP 4xx/5xx
- THEN the store rolls back to the original task values
- AND the dialog stays open with the user's unsaved edits intact
- AND a localized error toast appears

#### Scenario: Label deduplication and empty rejection

- GIVEN the user types `Frontend` and the task already has `frontend` as a label
- WHEN the user presses Enter
- THEN no duplicate label is added (case-insensitive match)
- AND if the input is whitespace-only, no label is added

#### Scenario: Self-dependency rejected

- GIVEN `TaskEditor` is editing task `T1`
- WHEN the user attempts to add `T1` itself as a dependency
- THEN the dependency is rejected and a localized warning toast appears

#### Scenario: Edit disabled during extraction

- GIVEN `taskStore.extracting === true`
- WHEN the task card renders
- THEN the Edit button is disabled with a tooltip explaining extraction is in progress

### i18n Keys (NEW)

```
taskEditor.title                  : "Edit Task"     | "Editar Tarea"
taskEditor.field_title            : "Title"         | "Título"
taskEditor.field_description      : "Description"   | "Descripción"
taskEditor.field_labels           : "Labels"        | "Etiquetas"
taskEditor.field_dependencies     : "Dependencies"  | "Dependencias"
taskEditor.labels_placeholder     : "Type a label and press Enter" | "Escribe una etiqueta y presiona Enter"
taskEditor.dependencies_placeholder: "Select sibling tasks" | "Selecciona tareas hermanas"
taskEditor.save                   : "Save"          | "Guardar"
taskEditor.cancel                 : "Cancel"        | "Cancelar"
taskEditor.saved_toast            : "Task updated"  | "Tarea actualizada"
taskEditor.save_error             : "Failed to save task. Rolling back." | "No se pudo guardar la tarea. Se restauró."
taskEditor.label_empty            : "Labels cannot be empty" | "Las etiquetas no pueden estar vacías"
taskEditor.label_duplicate        : "Label already exists" | "La etiqueta ya existe"
taskEditor.self_dependency        : "A task cannot depend on itself" | "Una tarea no puede depender de sí misma"
taskEditor.edit_blocked_extracting: "Editing disabled while extraction is in progress" | "Edición deshabilitada durante la extracción"
```

### Acceptance Criteria

- [ ] `TaskEditor.tsx` exists, uses shadcn `Dialog`, edits title/description/labels/dependencies
- [ ] Each task card in `StoryDetail.tsx` has an Edit button that opens the dialog with current values
- [ ] Save calls `PUT /api/v1/tasks/{id}` and updates `taskStore` optimistically with rollback
- [ ] Labels: case-insensitive dedupe, empty rejected, removable chips
- [ ] Dependencies limited to sibling tasks, self-dep rejected
- [ ] Edit button disabled while `extracting === true`
- [ ] `en.json` and `es.json` both contain the `taskEditor` section above

---

## Domain: export-download

### ADDED Requirements

#### Requirement: Export Page Route

The frontend MUST expose a route at `/[locale]/export` rendered by `frontend/src/pages/[locale]/export.astro`. The page MUST use the existing `MainLayout.astro` and MUST pass `locale` to the React island.

**Files**:
- New: `frontend/src/pages/[locale]/export.astro`
- New: `frontend/src/components/react/ExportPanel.tsx`
- Modified: `frontend/src/i18n/en.json`, `es.json` — new `exportPage` section

#### Requirement: Export Panel Component

`ExportPanel.tsx` MUST read `workspaceId` from `useWorkspaceStore`. The panel MUST present two format options: `JSON` and `Markdown`. When the user selects a format and clicks Download, the panel MUST call the backend export endpoint and trigger a browser download of the returned content.

The panel MUST NOT write any files to disk itself — the backend is the single source of serialized bytes; the browser downloads the response body.

#### Requirement: Backend Export Endpoint

The backend MUST add a new router `export_router` at `backend/src/storico/api/routes/export.py` with prefix `/api/v1/workspaces/{workspace_id}/export`. It MUST expose `GET /api/v1/workspaces/{workspace_id}/export/tasks/` accepting a `format` query parameter with values `json` or `markdown`.

The endpoint MUST:
- authenticate the user via the existing `get_current_user` dependency
- verify the user has access to `workspace_id` via `get_workspace_for_user`
- aggregate all tasks for the workspace (reusing the existing `list_by_workspace` repository method)
- return the serialized content with `Content-Disposition: attachment; filename="storico-tasks-{workspace_id}.{ext}"` and an appropriate `Content-Type` (`application/json` or `text/markdown`)
- MUST NOT write any files to the server filesystem — content is generated in-memory and streamed in the response

The endpoint MUST be registered in `backend/src/storico/api/app.py` via `app.include_router(export_router)`.

#### Requirement: Export Format Schemas

**JSON format** MUST return an array of task objects matching the `TaskSchema` shape used by the existing `GET /api/v1/tasks/` endpoint (camelCase via frontend `toCamelCase`, snake_case on the wire). Top-level: a JSON array; no envelope.

**Markdown format** MUST produce a document with one section per story, grouped under `## {story raw text or "As a(n) X, I want Y, so that Z"}`, each task as a `- **{title}** — {description}` bullet under its story. Labels render as `#labels` inline; dependencies render as `→ {title}` references.

#### Requirement: Export Error Handling

The endpoint MUST return HTTP 400 for unknown `format` values and HTTP 401 for unauthenticated requests (handled by `get_current_user`). The frontend panel MUST show a localized error toast on any non-2xx and MUST offer to retry.

### Scenarios

#### Scenario: Happy path — JSON download

- GIVEN a workspace is selected and contains tasks
- WHEN the user navigates to `/[locale]/export`, selects JSON, and clicks Download
- THEN the panel calls `GET /api/v1/workspaces/{workspace_id}/export/tasks/?format=json`
- AND the backend returns `Content-Type: application/json`, `Content-Disposition: attachment; filename="storico-tasks-{workspace_id}.json"`
- AND the browser downloads the file with valid JSON array contents

#### Scenario: Happy path — Markdown download

- GIVEN a workspace is selected and contains tasks
- WHEN the user selects Markdown and clicks Download
- THEN the panel calls the same endpoint with `?format=markdown`
- AND the backend returns `Content-Type: text/markdown`, `Content-Disposition: attachment; filename="storico-tasks-{workspace_id}.md"`
- AND the downloaded file groups tasks under per-story `## {story}` sections with the bullet format specified

#### Scenario: Unknown format — HTTP 400

- GIVEN the panel somehow requests `?format=csv` (or any non-`json`/`markdown` value)
- WHEN the request reaches the backend
- THEN the backend returns HTTP 400 with a localized error detail
- AND the panel shows a localized error toast and offers retry

#### Scenario: Unauthorized — HTTP 401

- GIVEN the user's session has expired
- WHEN the panel calls the export endpoint
- THEN the backend returns HTTP 401
- AND the panel shows a localized auth error toast

#### Scenario: No workspace selected

- GIVEN `useWorkspaceStore.currentWorkspace` is null
- WHEN the user navigates to `/[locale]/export`
- THEN the panel shows a localized "Select a workspace" empty state and the Download button is disabled

#### Scenario: Empty workspace — no tasks

- GIVEN a workspace is selected but has zero tasks
- WHEN the user downloads any format
- THEN the backend returns valid but empty content (`[]` for JSON, an empty Markdown header for Markdown)
- AND the browser downloads the file (no error toast)

### i18n Keys (NEW)

```
exportPage.title                       : "Export Tasks"        | "Exportar Tareas"
exportPage.description                 : "Download all tasks in the current workspace in your chosen format." | "Descarga todas las tareas del workspace actual en el formato elegido."
exportPage.format_label                : "Format"              | "Formato"
exportPage.format_json                 : "JSON"                | "JSON"
exportPage.format_markdown             : "Markdown"            | "Markdown"
exportPage.download                    : "Download"            | "Descargar"
exportPage.empty_no_workspace          : "Select a workspace to export its tasks." | "Selecciona un workspace para exportar sus tareas."
exportPage.error_unknown_format        : "Unknown format. Choose JSON or Markdown." | "Formato desconocido. Elige JSON o Markdown."
exportPage.error_unauthorized          : "Your session has expired." | "Tu sesión ha expirado."
exportPage.error_generic               : "Export failed. Try again." | "Exportación fallida. Intenta de nuevo."
exportPage.success_toast               : "Download started"    | "Descarga iniciada"
```

### Acceptance Criteria

- [ ] Route `/[locale]/export` exists, renders `ExportPanel.tsx` inside `MainLayout.astro`
- [ ] `ExportPanel.tsx` reads `workspaceId` from `useWorkspaceStore`
- [ ] Backend router `export_router` exists in `export.py` and is registered in `app.py`
- [ ] `GET /api/v1/workspaces/{workspace_id}/export/tasks/?format=json|markdown` returns content with correct `Content-Type` and `Content-Disposition`
- [ ] Backend never writes to disk; content is streamed in response body
- [ ] JSON returns an array of `TaskSchema`-shaped objects; Markdown groups per-story with specified bullet format
- [ ] Unknown format → HTTP 400; unauthenticated → HTTP 401
- [ ] No workspace → Download disabled with localized empty state
- [ ] Empty workspace → valid empty content downloaded, no error toast
- [ ] `en.json` and `es.json` both contain the `exportPage` section above

---

## Cross-Cutting Acceptance Criteria

- [ ] All four workstreams are independently testable
- [ ] No new dependency added except `@hello-pangea/dnd` (frontend) — backend uses only existing infra
- [ ] All new pages use `MainLayout.astro` and existing `useWorkspaceStore` for workspace context
- [ ] All new user-facing strings appear in BOTH `en.json` and `es.json`
- [ ] No remaining call to `/api/v1/extract/` (legacy) anywhere in the frontend
