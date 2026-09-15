# Proposal: User Story → Tasks Decomposition Workflow

## Intent

Complete the end-to-end User Story → Tasks workflow in Storico. Extraction works on the backend but the frontend has a critical endpoint bug blocking it, and three sidebar-navigation pages (Kanban, Export, Task Editor) are missing or 404.

## Scope

### In Scope
- Fix `tasks-api.ts` calling legacy `/api/v1/extract/` (returns 410 Gone) — must use workspace-scoped endpoint
- Add Kanban Board page (`/kanban`) with drag-and-drop column view
- Add task editor component (inline edit title, description, labels, dependencies)
- Add Export page (`/export`) with JSON and Markdown download
- Add model selector UI in workspace settings (already partially scaffolded)
- i18n keys in `en.json` / `es.json` for new pages

### Out of Scope
- Trello/Jira/GitHub live export (uses existing connector infra but no UI wiring)
- CSV/XML export formats
- Batch extraction UI (`POST /batch`)
- Full custom prompt editor UI (already exists in workspace settings)

## Capabilities

### New Capabilities
- `kanban-board`: Drag-and-drop Kanban board showing tasks grouped by status across projects in a workspace
- `task-editor`: Inline editing of extracted task title, description, labels, and dependencies
- `export-download`: Download extracted tasks as JSON or Markdown

### Modified Capabilities
- `extraction-workflow`: Frontend API client signature changes (workspace-scoped endpoint, workspace_id required)

## Approach

Four parallel workstreams after the critical bugfix:

1. **Bugfix** — change `tasks-api.ts:extractTasks()` to call `POST /api/v1/workspaces/{workspace_id}/extract/`, add `workspace_id` parameter, propagate through `taskStore` and `StoryDetail`
2. **Kanban** — new Astro page `[locale]/kanban.astro` with React island `KanbanBoard.tsx` (uses `@hello-pangea/dnd` for drag-and-drop, fetches all tasks via existing API)
3. **Task editor** — new `TaskEditor.tsx` dialog/modal component, wire into `StoryDetail.tsx` task list
4. **Export** — new Astro page `[locale]/export.astro` with React island `ExportPanel.tsx`; new backend endpoint `GET /api/v1/workspaces/{workspace_id}/export/tasks/` returning JSON

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `frontend/src/lib/tasks-api.ts` | Modified | Fix workspace-scoped endpoint |
| `frontend/src/stores/taskStore.ts` | Modified | Pass workspace_id through extract |
| `frontend/src/components/react/StoryDetail.tsx` | Modified | Wire workspace_id, link task editor |
| `frontend/src/pages/[locale]/kanban.astro` | New | Kanban page shell |
| `frontend/src/pages/[locale]/export.astro` | New | Export page shell |
| `frontend/src/components/react/KanbanBoard.tsx` | New | Kanban React island |
| `frontend/src/components/react/TaskEditor.tsx` | New | Edit modal |
| `frontend/src/components/react/ExportPanel.tsx` | New | Export controls |
| `frontend/src/i18n/en.json` | Modified | Add kanban/export/edit keys |
| `frontend/src/i18n/es.json` | Modified | Add kanban/export/edit keys |
| `backend/src/storico/api/routes/export.py` | New | Export endpoint |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Broken extraction blocks all demo flow | High | Bugfix is first deliverable, testable in isolation |
| `@hello-pangea/dnd` compatibility with Astro/React | Low | Wrapped as standard React island — sandbox test before full build |
| Export endpoint overlaps with existing extraction listing | Low | Separate concern: export serializes tasks, listing returns extractions |

## Rollback Plan

- Bugfix: revert `tasks-api.ts` + `taskStore.ts` + `StoryDetail.tsx` changes
- New pages: remove `kanban.astro`, `export.astro`, and their React islands
- Backend: remove `export.py` router from app

## Dependencies

- Astro routing handles `[locale]/kanban.astro` and `[locale]/export.astro` automatically
- `@hello-pangea/dnd` npm package (or chakra-ui drag-and-drop alternative)
- Backend must be running for all pages to function

## Success Criteria

- [ ] Extraction succeeds from StoryDetail page (critical bugfix verified)
- [ ] `/kanban` renders tasks in draggable columns
- [ ] Task editor modal opens, edits save via API
- [ ] Export page downloads JSON and Markdown
