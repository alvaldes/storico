# Tasks: User Story → Tasks Decomposition

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 750–850 |
| 400-line budget risk | **High** |
| Chained PRs recommended | **Yes** |
| Suggested split | Bugfix → Kanban → Task Editor → Export |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: Yes
Chained PRs recommended: Yes
Chain strategy: pending
400-line budget risk: High

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test | Runtime harness | Rollback boundary |
|------|------|-----------|-------------|----------------|-------------------|
| 1 | Fix workspace extraction | PR 1 | `vitest run src/lib/__tests__/tasks-api` | N/A (unit) | Revert tasks-api, taskStore, StoryDetail |
| 2 | Kanban drag-and-drop | PR 2 | `vitest run src/components/react/__tests__/KanbanBoard` | Visit /kanban with seeded tasks | Revert KanbanBoard, kanban.astro, taskStore additions |
| 3 | Task editor modal | PR 3 | `vitest run src/components/react/__tests__/TaskEditor` | Visit /stories/{id}, click Edit | Revert TaskEditor.tsx, StoryDetail edits |
| 4 | Export page + endpoint | PR 4 | `pytest backend/tests/test_export -v` | Visit /export, click Download | Revert export.py, app.py, ExportPanel, export.astro |

## Phase 1: Bugfix (PR 1)

- [x] 1.1 `tasks-api.ts` — `extractTasks(workspaceId, storyId, options?)`, URL `POST /api/v1/workspaces/${workspaceId}/extract/`
- [x] 1.2 `taskStore.ts` — propagate `workspaceId`, add 401 auth-specific error key, preserve prior tasks on any failure
- [x] 1.3 `StoryDetail.tsx` — read `workspaceId` from `useWorkspaceStore`, guard if null
- [x] 1.4 i18n: `stories.extraction_unauthorized` in en.json + es.json
- [x] 1.5 Unit: verify URL construction, error/401/network state transitions

## Phase 2: Kanban Board (PR 2)

- [x] 2.1 `npm add @hello-pangea/dnd`
- [x] 2.2 `taskStore.ts` — add `workspaceTasks[]`, `fetchTasksForWorkspace(wsId)`, `updatingTaskId`, async `updateTask` with rollback
- [x] 2.3 `KanbanBoard.tsx` — Board → Column → Card, 5 fixed columns, drag-and-drop via `@hello-pangea/dnd`, optimistic status PUT
- [x] 2.4 Empty states: no workspace vs zero tasks
- [x] 2.5 `kanban.astro` page with MainLayout
- [x] 2.6 i18n: `kanban.*` keys in en.json + es.json

## Phase 3: Task Editor (PR 3)

- [x] 3.1 `TaskEditor.tsx` — shadcn Dialog, edit title/description/labels/dependencies
- [x] 3.2 Label dedup (case-insensitive), empty rejection, no self-dependency
- [x] 3.3 `StoryDetail.tsx` — Edit button per task card, disabled during extraction, local `editingTaskId` state
- [x] 3.4 Optimistic Save via `PUT /api/v1/tasks/{id}`, rollback on failure, keep open on error
- [x] 3.5 i18n: `taskEditor.*` keys in en.json + es.json
- [x] 3.6 Unit: label/dep validation, save/rollback behavior

## Phase 4: Export (PR 4)

- [x] 4.1 `backend/.../routes/export.py` — `GET /workspaces/{id}/export/tasks/?format=json|markdown`, Content-Disposition attachment, in-memory serialization
- [x] 4.2 Register `export_router` in `backend/src/storico/api/app.py`
- [x] 4.3 `ExportPanel.tsx` — format selector, Download trigger, empty/no-workspace states, error + retry
- [x] 4.4 `export.astro` page with MainLayout
- [x] 4.5 i18n: `exportPage.*` keys in en.json + es.json
- [x] 4.6 Integration: pytest for content-type, filename, unknown-format 400
