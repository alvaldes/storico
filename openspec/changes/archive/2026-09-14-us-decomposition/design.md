# Design: User Story → Tasks Decomposition Workflow

## Technical Approach

Fix workspace-scoped extraction (bugfix blocking the demo flow), then build Kanban board, task editor, and export page as independent workstreams. Backend already has the needed endpoints (`POST /api/v1/workspaces/{id}/extract/`, `PUT /api/v1/tasks/{id}`, `GET /api/v1/tasks/`) — this is primarily frontend work plus a thin backend export router.

## Architecture Decisions

### Decision: Workspace ID Propagation

| Option | Tradeoff | Decision |
|--------|----------|----------|
| A: Pass `workspaceId` through every call | Explicit, traceable, testable; more params | ✅ **Chosen** |
| B: Read from global store inside API client | Fewer param changes; implicit coupling, stale-store bugs hard to debug | ❌ Rejected |

**Rationale**: `workspaceId` is a runtime value from context, not a config constant. Passing it explicitly makes the data flow visible and prevents silent failures when the store is stale.

### Decision: Kanban Component Architecture

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Monolithic `KanbanBoard.tsx` | Fewer files, simpler wires; hard to test/reuse | ❌ Rejected |
| Decomposed: `Board → Column → Card` | Testable, extensible; more boilerplate | ✅ **Chosen** |

### Decision: Kanban State Location

| Option | Tradeoff | Decision |
|--------|----------|----------|
| New `kanbanStore.ts` | Clean separation; duplicates task fetching logic | ❌ Rejected |
| Extend `taskStore.ts` with `workspaceTasks` | Single store, reuses `updateTask` for rollback | ✅ **Chosen** |

**Rationale**: Kanban shares the same `updateTask`/rollback logic. A separate store would duplicate error handling and optimistic-update patterns.

### Decision: Task Editor State

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Local state in `StoryDetail` | Simple; resets on nav | ✅ **Chosen** |
| Store-backed edit buffer | Survives navigation; adds complexity for no UX need | ❌ Rejected |

## Data Flow

```
Bugfix path (extraction):
  StoryDetail ─→ useWorkspaceStore.currentWorkspace.id
       │
       ├ → taskStore.extractTasks(workspaceId, storyId)
       │         └ → tasks-api.extractTasks(workspaceId, storyId, options?)
       │                    └ → POST /api/v1/workspaces/{wsId}/extract/
       │
       └ → taskStore sets tasks[storyId] on "completed" status

Kanban:
  KanbanBoard ─→ useWorkspaceStore.currentWorkspace.id
       │
       ├ → taskStore.fetchTasksForWorkspace(workspaceId)
       │         └ → GET /api/v1/tasks/?workspace_id={wsId}
       │
       └ → onDrop(taskId, newStatus)
             └ → taskStore.updateTask(taskId, { status }) (optimistic)
                    └ → PUT /api/v1/tasks/{taskId} { status }
                           ├ → 200: keep
                           └ → error: rollback + toast

Export:
  ExportPanel ─→ useWorkspaceStore.currentWorkspace.id
       │
       └ → GET /api/v1/workspaces/{wsId}/export/tasks/?format=json|markdown
              └ → backend streams response with Content-Disposition
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `frontend/src/lib/tasks-api.ts` | Modify | `extractTasks(workspaceId, storyId, options?)` — URL becomes workspace-scoped |
| `frontend/src/stores/taskStore.ts` | Modify | Add `extractTasks(workspaceId, storyId)`, add `workspaceTasks` + `fetchTasksForWorkspace(workspaceId)`, add per-task loading state, 401 handling |
| `frontend/src/components/react/StoryDetail.tsx` | Modify | Pass `workspaceId` to `extractTasks`, add Edit button per task card, add `editingTaskId` local state |
| `frontend/src/pages/[locale]/kanban.astro` | New | Astro page shell, `MainLayout`, hydrates `KanbanBoard` island |
| `frontend/src/pages/[locale]/export.astro` | New | Astro page shell, `MainLayout`, hydrates `ExportPanel` island |
| `frontend/src/components/react/KanbanBoard.tsx` | New | Board → Column → Card decomposition, `@hello-pangea/dnd` drag-and-drop, optimistic rollback |
| `frontend/src/components/react/TaskEditor.tsx` | New | shadcn `Dialog`, edits title/description/labels/dependencies, calls `PUT /api/v1/tasks/{id}`, optimistic rollback |
| `frontend/src/components/react/ExportPanel.tsx` | New | Format selector (JSON/Markdown), Download button, triggers browser download |
| `frontend/src/i18n/en.json` | Modify | Add `kanban.*`, `taskEditor.*`, `exportPage.*`, extraction 401 key |
| `frontend/src/i18n/es.json` | Modify | Same keys in Spanish |
| `backend/src/storico/api/routes/export.py` | New | Export router with `GET /tasks/` endpoint |
| `backend/src/storico/api/app.py` | Modify | Register `export_router` |

## Interfaces / Contracts

```python
# New export.py endpoint
GET /api/v1/workspaces/{workspace_id}/export/tasks/?format=json|markdown

# Response: 200 with Content-Disposition attachment
# Headers:
#   Content-Type: application/json | text/markdown
#   Content-Disposition: attachment; filename="storico-tasks-{id}.{ext}"
# Body: in-memory serialized content (no server file writes)
```

```typescript
// Modified API client signature
extractTasks(
  workspaceId: string,
  storyId: string,
  options?: { model?: string; temperature?: number }
): Promise<{
  extractionId: string;
  status: string;
  tasks: Task[];
  modelUsed: string;
  errorInfo?: string;
}>;

// Extended store
interface TaskState {
  tasks: Record<string, Task[]>;       // per-story
  workspaceTasks: Task[];              // all tasks in workspace (kanban)
  loading: boolean;
  extracting: boolean;
  error: string | null;
  updatingTaskId: string | null;       // drag-in-flight lock

  fetchTasksForWorkspace(workspaceId: string): Promise<void>;
  extractTasks(workspaceId: string, storyId: string): Promise<void>;
  updateTask(taskId: string, updates: Partial<Task>): Promise<void>; // now async with rollback
}
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `tasks-api.ts` URL construction | Jest — assert correct workspace-scoped path |
| Unit | `taskStore.ts` extract/error/401 paths | Zustand store tests — mock API, assert state transitions |
| Unit | `TaskEditor.tsx` label dedup, self-dep rejection | React Testing Library — form interactions |
| Integration | Backend `GET /export/tasks/` format json/markdown | pytest with test client — assert Content-Type, body shape |
| Integration | Drag-and-drop `PUT /api/v1/tasks/{id}` rollback | Mock 4xx response, assert card returns to original column |
| E2E (manual) | Full flow: create story → extract → edit → kanban → export | Manual QA checklist |

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Migration / Rollout

No migration required. The backend endpoint `POST /api/v1/workspaces/{workspace_id}/extract/` already exists — the bugfix is purely frontend. Existing tasks persist across the change.

## Open Questions

None — all designs are scoped to existing backend infrastructure.
