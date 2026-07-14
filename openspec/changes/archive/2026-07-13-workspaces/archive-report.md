# Archive Report: Workspaces

**Change**: workspaces
**Archived**: 2026-07-13
**Artifact store**: openspec (file-based) + Engram (verify report + apply progress)

---

## Change Summary

Replaced the flat `User → Project` model with a multi-tenant **Workspace** organizational entity. Workspaces group projects, members, LLM configuration, and prompt templates into fully isolated tenants, enabling role-based access control and per-team LLM/prompt configuration.

34 tasks implemented across 8 phases, estimated ~2,800-3,200 total changed lines.

---

## What Was Built

### Phase 1 — Data Model (6 tasks)
- **Domain entities**: `Workspace`, `WorkspaceMember`, `WorkspaceLLMConfig`, `WorkspacePrompt` with frozen dataclass pattern
- **WorkspaceRole** StrEnum (admin/member)
- **Exceptions**: `NotWorkspaceMember`, `InsufficientRole`, `OwnerTransferError`, `LastAdminError`, `CannotRemoveOwnerError`
- **Repository ports** (4 new ABCs): `WorkspaceRepository`, `WorkspaceMemberRepository`, `WorkspaceLLMConfigRepository`, `WorkspacePromptRepository`
- **Modified ports**: `ProjectRepository` (list_by_workspace), `UserStoryRepository`, `TaskRepository`, `ExtractionRepository` (added list_by_workspace)
- **ORM models**: `WorkspaceModel`, `WorkspaceMemberModel`, `WorkspaceLLMConfigModel`, `WorkspacePromptModel`
- **Modified**: `ProjectModel` — replaced `owner_id` with `workspace_id` + `created_by`
- **Alembic migration #0007**: creates 4 new tables, alters projects table

### Phase 2 — Infrastructure (3 tasks)
- **SQLAlchemy repos**: `SQLAlchemyWorkspaceRepository`, `SQLAlchemyWorkspaceMemberRepository` (with atomic transfer_ownership), `SQLAlchemyWorkspaceLLMConfigRepository`, `SQLAlchemyWorkspacePromptRepository`
- **Modified**: `SQLAlchemyProjectRepository` (list_by_workspace, count_by_workspace)
- **Added** list_by_workspace to story/task/extraction repos

### Phase 3 — API Schemas + Auth (4 tasks)
- **Pydantic schemas**: Workspace CRUD, member management, LLM config, prompts
- **Modified project schemas**: owner_id → workspace_id, added created_by
- **JWT auth migration**: Replaced proxy header auth (X-Storico-Internal-Token + X-Storico-User-Id) with `Authorization: Bearer <JWT>`
- **Membership dependencies**: `get_workspace_for_user`, `require_admin`, `require_owner` (4-layer FastAPI dep chain)

### Phase 4 — API Routes (8 tasks)
- **Workspace CRUD + members**: `/api/v1/workspaces/*` with create, list, get, update, delete, member management, transfer ownership
- **Workspace settings**: `/api/v1/workspaces/{id}/settings/llm` and `/settings/prompts` with read-time fallback resolution
- **Use cases**: `CreateWorkspaceUseCase`, `AddMemberUseCase`, `RemoveMemberUseCase`, `TransferOwnershipUseCase`, `generate_slug` helper
- **Modified routes**: Projects, stories, tasks, extractions — workspace-scoped with 410 deprecation on old prefixes

### Phase 5 — App Wiring (3 tasks)
- Router registration, error handlers for workspace exceptions, model/repo exports

### Phase 6 — Frontend Core (5 tasks)
- TypeScript interfaces, Zod schemas, API clients (workspace, LLM config, prompts)
- Zustand `workspaceStore` with persist middleware, workspace-scoped project store updates

### Phase 7 — Frontend UI (3 tasks)
- React sidebar island replacing Astro sidebar, with shadcn TeamSwitcher-style `WorkspaceSwitcher`
- Workspace-aware nav links, Settings link conditionally shown for admins
- MainLayout updated to embed React sidebar

### Phase 8 — Frontend Settings (2 tasks)
- Workspace settings page: LLM config editor (provider, model, temperature, max_tokens, base_url) and prompt editors
- Member management UI: member list, add/remove/role-change, transfer ownership with confirmation dialogs

---

## Fixes Applied (Post-Verification)

| Issue | Status | Fix |
|-------|--------|-----|
| AC-001 (CRITICAL): Auto-create personal workspace on registration | ✅ Resolved | `sync_user` in auth.py now calls `CreateWorkspaceUseCase` to auto-create `<user.name>'s Workspace` |
| WARNING-1: setCurrentWorkspace doesn't trigger projectStore.fetchProjects | ✅ Resolved | `setCurrentWorkspace` now calls `projectStore.fetchProjects()` after selection |
| WARNING-2: GET /api/v1/users/me doesn't return workspaces | ✅ Resolved | Added `UserProfileResponse` schema with workspace list and roles |
| WARNING-3: Route path naming mismatch | 🔶 Acknowledged | Pre-existing naming convention — no change made |
| WARNING-4: No Zustand persist middleware on workspaceStore | ✅ Resolved | Added `persist` middleware to preserve workspace selection across page reloads |

---

## Verification Result

**Status**: PASS WITH WARNINGS → All critical issues resolved
**Source**: Engram observation #378 (`sdd/workspaces/verify-report`)

- 34/34 tasks implemented across 8 phases
- 1 critical issue → resolved (AC-001)
- 4 warnings → 3 resolved, 1 acknowledged (WARNING-3 is pre-existing)
- No pending critical or blocking issues

---

## Artifact Inventory

| Artifact | Location | Status |
|----------|----------|--------|
| Spec | `openspec/changes/workspaces/spec.md` | ✅ |
| Design | `openspec/changes/workspaces/design.md` | ✅ |
| Tasks | `openspec/changes/workspaces/tasks.md` | ✅ (all 34 marked complete) |
| Apply Progress | Engram obs #374 (`sdd/workspaces/apply-progress`) | ✅ |
| Verify Report | Engram obs #378 (`sdd/workspaces/verify-report`) | ✅ |
| Archive Report | `openspec/changes/workspaces/archive-report.md` + Engram | ✅ |

---

## Key Learnings

1. **Auth migration complexity**: The JWT auth migration (T-012) was the most cross-cutting change — touching every route file, the frontend proxy, and auth config. Doing it as part of the workspace change was necessary for workspace auth but introduced more risk than anticipated.

2. **Workspace resolution patterns**: Stories, tasks, and extractions don't have a direct workspace_id in the URL — they resolve through the chain `story → project → workspace`. This required careful `get_workspace_for_user` dependency design to avoid N+1 lookups.

3. **Read-time fallback for config/prompts**: The LLM config and prompt resolution use read-time fallback (no DB writes when returning defaults). This was the right call — simpler to implement and avoids stale default rows.

4. **Auto-creation on registration**: The AC-001 auto-creation was easy to miss because it lives in the auth sync flow, not in the workspace feature itself. Adding it required careful integration with the existing `sync_user` endpoint.

5. **WorkspaceStore persist**: Zustand's `persist` middleware was needed to survive page reloads since View Transitions only keep in-memory state across SPA-like navigations, not full page reloads.

6. **410 Deprecation strategy**: Old route paths (`/api/v1/projects/`) return 410 Gone with a helpful message about the new workspace-prefixed URLs. This gives clients time to migrate without breaking silently.

---

## SDD Cycle Complete

The Workspaces change has been fully planned, specified, designed, implemented, verified, and archived. Ready for the next change.
