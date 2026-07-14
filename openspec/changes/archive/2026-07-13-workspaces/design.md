# Design: Workspaces as Central Organizational Entity

**Status**: Draft
**Depends on**: `openspec/changes/workspaces/spec.md`
**Backend stack**: FastAPI + SQLAlchemy async + PostgreSQL + Alembic
**Frontend stack**: Astro + React islands + Zustand + shadcn

## 1. Component Architecture

### Domain Layer — New Entities

All entities follow the existing frozen dataclass pattern (`@dataclass(frozen=True, slots=True)`) established in `project.py`, `user.py`, `task.py`.

#### `Workspace`

```python
@dataclass(frozen=True, slots=True)
class Workspace:
    name: str
    slug: str
    owner_id: UUID
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

Invariants: `name` not empty, `slug` unique across all workspaces, `owner_id` must reference an existing `WorkspaceMember` with role=admin.

#### `WorkspaceMember`

```python
class WorkspaceRole(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"

@dataclass(frozen=True, slots=True)
class WorkspaceMember:
    workspace_id: UUID
    user_id: UUID
    role: WorkspaceRole
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

Invariants: exactly one `ADMIN` who is also the `owner_id` on `Workspace`. Cannot remove `owner_id` from members. `UNIQUE(workspace_id, user_id)` at DB level prevents duplicates.

#### `WorkspaceLLMConfig`

```python
@dataclass(frozen=True, slots=True)
class WorkspaceLLMConfig:
    workspace_id: UUID
    provider: str = "ollama"
    model: str | None = None        # None = use global default
    temperature: float | None = None
    max_tokens: int | None = None
    base_url: str | None = None      # None = use global default
    id: UUID = field(default_factory=uuid4)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

`provider` is required at upsert time; all other fields optional (nullable = fallback to global).

#### `WorkspacePrompt`

```python
@dataclass(frozen=True, slots=True)
class WorkspacePrompt:
    workspace_id: UUID
    system_prompt: str | None = None
    instruction_template: str | None = None
    few_shot_examples: list[dict] | None = None
    id: UUID = field(default_factory=uuid4)
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

All fields optional — None = use global defaults from `PromptManager` / `task_generation.j2`.

### Domain Layer — Modified Entities

#### `Project` — `owner_id` replaced by `workspace_id` + new `created_by`

```python
@dataclass(frozen=True, slots=True)
class Project:
    name: str
    workspace_id: UUID                    # was owner_id
    description: str = ""
    created_by: UUID | None = None        # NEW — audit FK, optional
    id: UUID = field(default_factory=uuid4)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))
```

### Domain Ports — New

Four new ABC repository ports under `domain/ports/`, matching the existing pattern in `project_repository.py`.

| Port | Methods |
|------|---------|
| `WorkspaceRepository` | `save`, `find_by_id`, `list_by_user`, `find_by_slug`, `delete`, `count_members` |
| `WorkspaceMemberRepository` | `add`, `remove`, `update_role`, `find_by_workspace_and_user`, `list_by_workspace`, `list_by_user`, `transfer_ownership`, `count_admins` |
| `WorkspaceLLMConfigRepository` | `get(workspace_id)`, `upsert(config)` |
| `WorkspacePromptRepository` | `get(workspace_id)`, `upsert(prompt)` |

### Domain Ports — Modified

- `ProjectRepository`: `list_by_owner` → `list_by_workspace(workspace_id)`. Keep `list()` for admin-only global view. Add `count_by_workspace(workspace_id)`.
- `UserStoryRepository`: add `list_by_workspace(workspace_id)` — joins through `ProjectModel` to filter by `workspace_id`.
- `TaskRepository`: add `list_by_workspace(workspace_id)` — joins through `UserStoryModel → ProjectModel`.
- `ExtractionRepository`: add `list_by_workspace(workspace_id)` — same join pattern.

### Application Layer — New Use Cases

Each use case is a class in `application/workspaces/`, following the pattern in `application/extraction/extract_from_story.py`.

| Use Case | Logic |
|----------|-------|
| `CreateWorkspaceUseCase` | Validate name, generate slug, check slug uniqueness, create workspace + owner member in one transaction |
| `AddMemberUseCase` | Validate workspace exists, user exists, not already member, insert with role `member` |
| `RemoveMemberUseCase` | Validate not owner, not last admin, delete membership |
| `TransferOwnershipUseCase` | Validate new owner is admin, atomic: update workspace.owner_id + old owner role=admin + new owner role=admin |
| `UpdateLLMConfigUseCase` | Validate workspace exists, check admin role, upsert LLM config |
| `UpdatePromptUseCase` | Same pattern for prompts |

### Infrastructure Layer — New ORM Models

All under `infrastructure/database/models/` following the `ProjectModel` pattern.

- **`WorkspaceModel`** — `__tablename__ = "workspaces"`. Columns: id (UUID PK), name, slug (unique), owner_id (FK→users), created_at, updated_at. Relationship to `workspace_members`.
- **`WorkspaceMemberModel`** — `__tablename__ = "workspace_members"`. Columns: id (UUID PK), workspace_id (FK→workspaces), user_id (FK→users), role (String(20)), created_at. `UniqueConstraint(workspace_id, user_id)`. Relationships to `workspace` and `user`.
- **`WorkspaceLLMConfigModel`** — `__tablename__ = "workspace_llm_configs"`. Columns: id (UUID PK), workspace_id (FK→workspaces, unique), provider, model (nullable), temperature (nullable), max_tokens (nullable), base_url (nullable), updated_at.
- **`WorkspacePromptModel`** — `__tablename__ = "workspace_prompts"`. Columns: id (UUID PK), workspace_id (FK→workspaces, unique), system_prompt (nullable), instruction_template (nullable), few_shot_examples (JSONB nullable), updated_at.

Infrastructure repositories (SQLAlchemy implementations) follow the exact `_to_domain` / `_to_orm_kwargs` dual-method pattern from existing repos. Alembic migration #0007 creates all new tables + alters `projects` (drop owner_id, add workspace_id + created_by).

### API Layer — Schemas

New files under `api/schemas/`:

| File | Schemas |
|------|---------|
| `workspace.py` | `CreateWorkspaceRequest`, `UpdateWorkspaceRequest`, `WorkspaceResponse`, `WorkspaceListResponse` |
| `workspace_member.py` | `AddMemberRequest`, `MemberResponse`, `MemberListResponse`, `TransferOwnershipRequest` |
| `workspace_llm_config.py` | `LLMConfigRequest`, `LLMConfigResponse` |
| `workspace_prompt.py` | `PromptRequest`, `PromptResponse` |

All follow the `model_config = ConfigDict(extra="forbid")` / `from_attributes=True` pattern.

### API Layer — Routes

- `api/routes/workspaces.py` — CRUD workspace, members, transfer. All under `/api/v1/workspaces`.
- `api/routes/workspace_settings.py` — LLM config + prompts under `/api/v1/workspaces/{id}/settings/`.

Modified existing routes — add `get_workspace_for_user` dependency chain, re-prefix or nest:

- **`projects.py`**: routes move from `/api/v1/projects` to `/api/v1/workspaces/{id}/projects` OR keep flat prefix with workspace_id as query param. Decision: **re-prefix under workspace** — all data routes move under `workspaces/{id}/`. Old `/api/v1/projects/` routes return 410 Gone or redirect. Keep a compatibility redirect layer in a separate module.
- **`stories.py`**: add `get_workspace_for_user` dep. Stories always accessed through a project which is scoped to workspace → workspace context resolved from project.
- **`tasks.py`**: same pattern as stories.
- **`extractions.py`**: same pattern.
- **`extraction.py`**: same pattern (already has `get_current_user` but unused).

### Frontend — New Components

- **`WorkspaceSwitcher.tsx`** — shadcn sidebar-07 TeamSwitcher adaptation. Dropdown with workspace list, "Add workspace" action, creates/displays workspaces.
- **`workspaceStore.ts`** — Zustand store: `workspaces`, `currentWorkspace`, `setCurrentWorkspace`, `fetchWorkspaces`, `createWorkspace`.
- **`lib/workspace-api.ts`** — API client for workspace CRUD + members.
- **`lib/llm-config-api.ts`** — LLM config API client.
- **`lib/prompts-api.ts`** — Prompts API client.
- **`types/workspace.ts`** — `Workspace`, `WorkspaceMember`, `WorkspaceLLMConfig`, `WorkspacePrompt` interfaces.
- **`schemas/workspace.ts`** — Zod schemas.

### Frontend — Modified

- **`MainLayout.astro`** — embed Sidebar React island, pass user + locale + currentPath. Sidebar now a `<Sidebar client:load />` island.
- **`components/astro/Sidebar.astro`** — **DELETE**. Replaced by the React island.
- **`types/project.ts`** — `ownerId` → `workspaceId`, add `createdBy`.
- **`stores/projectStore.ts`** — `createProject` accepts `workspaceId` instead of `ownerId`. `fetchProjects` scoped to workspace.
- **`stores/storyStore.ts`** — add workspace scope.
- All page `.astro` files — pass workspace context from store.

---

## 2. Data Flow Diagrams

### Flow 1: Create Workspace

```
Client → POST /api/v1/workspaces { name: "Acme" }
  → get_current_user → User
  → CreateWorkspaceUseCase.execute(name, user)
    → slug = parameterize("Acme") → "acme"
    → repo.find_by_slug("acme") → None (ok)
    → DB transaction:
        ws = repo.save(Workspace(name="Acme", slug="acme", owner_id=user.id))
        member_repo.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=ADMIN))
    → commit
  → 201 WorkspaceResponse
```

### Flow 2: List Projects in Workspace

```
Client → GET /api/v1/workspaces/{id}/projects
  → get_current_user → User
  → get_workspace_for_user(workspace_id=id, user=User)
    → ws = workspace_repo.find_by_id(id) → 404 if missing
    → member = member_repo.find_by_workspace_and_user(id, user.id) → 403 if None
    → return (workspace, member.role)
  → project_repo.list_by_workspace(workspace_id=id)
  → 200 [{ id, name, ... }]
```

### Flow 3: Admin Updates LLM Config

```
Client → PUT /api/v1/workspaces/{id}/settings/llm { model: "mistral" }
  → get_current_user → User
  → get_workspace_for_user(id, user) → (ws, "admin")
  → require_admin(ws_role) → 403 if role != "admin"
  → UpdateLLMConfigUseCase.execute(workspace_id=id, model="mistral")
    → upsert into workspace_llm_configs
  → 200 LLMConfigResponse
```

### Flow 4: Member → Admin Endpoint (403)

```
Client → GET /api/v1/workspaces/{id}/settings/llm
  → get_current_user → User
  → get_workspace_for_user(id, user) → (ws, "member")
  → require_admin(ws_role) → 403 Forbidden
  → {"detail": "Admin access required", "type": "insufficient_role"}
```

### Flow 5: Transfer Ownership

```
Client → POST /api/v1/workspaces/{id}/transfer { new_owner_id: "bob-uuid" }
  → get_current_user → User (Alice)
  → get_workspace_for_user(id, alice) → (ws, "admin")
  → require_admin(ws_role) → ok
  → TransferOwnershipUseCase.execute(workspace_id, current_owner=alice.id, new_owner=bob.id)
    → validate ws.owner_id == alice.id (else 403 — only owner can transfer)
    → validate bob member with role admin (else 400)
    → DB transaction:
        update workspace SET owner_id = bob.id
        update workspace_member SET role='admin' WHERE user_id = alice.id
        (bob already admin, stays admin)
    → commit
  → 200 { message, previous_owner_id, new_owner_id }
```

### Flow 6: Switch Workspace in Frontend

```
User clicks workspace "Acme Project" in TeamSwitcher
  → workspaceStore.setCurrentWorkspace(acmeWorkspace)
  → projectStore.fetchProjects() reads currentWorkspace.id
    → GET /api/v1/workspaces/{acme-id}/projects
  → StoryList / KanbanBoard re-render with new scope
  → URL updates to /workspaces/{acme-id}/projects (via Astro navigation)
```

---

## 3. Dependency Chain (FastAPI)

```python
# Layer 1 — auth (required on ALL routes)
async def get_current_user(
    request: Request,
    repo: UserRepository = Depends(get_repository(SQLAlchemyUserRepository)),
) -> User:
    # Existing: validates X-Storico-Internal-Token + X-Storico-User-Id
    # Returns User or raises 401

# Layer 2 — workspace membership check
async def get_workspace_for_user(
    workspace_id: UUID = Path(...),
    current_user: User = Depends(get_current_user),
    ws_repo: WorkspaceRepository = Depends(get_repository(SQLAlchemyWorkspaceRepository)),
    member_repo: WorkspaceMemberRepository = Depends(get_repository(SQLAlchemyWorkspaceMemberRepository)),
) -> tuple[Workspace, WorkspaceRole]:
    workspace = await ws_repo.find_by_id(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    member = await member_repo.find_by_workspace_and_user(workspace_id, current_user.id)
    if member is None:
        raise HTTPException(status_code=403, detail="Not a member of this workspace")
    return (workspace, member.role)

# Layer 3 — role gate
async def require_admin(
    workspace_ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
) -> tuple[Workspace, WorkspaceRole]:
    workspace, role = workspace_ctx
    if role != WorkspaceRole.ADMIN:
        raise HTTPException(status_code=403, detail="Admin access required")
    return workspace_ctx

# Layer 4 — owner gate (for transfer)
async def require_owner(
    workspace_ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
) -> Workspace:
    workspace, role = workspace_ctx
    current_user = ... # resolved from request context
    if workspace.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Only the workspace owner can perform this action")
    return workspace

# Usage in routes
@router.get("/workspaces/{workspace_id}/settings/llm")
async def get_llm_config(
    ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin),
    config_repo: WorkspaceLLMConfigRepository = Depends(get_repository(SQLAlchemyWorkspaceLLMConfigRepository)),
):
    workspace, _ = ctx
    config = await config_repo.get(workspace.id)
    return resolve_llm_config(config)  # fallback logic
```

### Error Responses

| Layer | Status | Detail |
|-------|--------|--------|
| 401 Unauthenticated | 401 | `{"detail": "Invalid or missing authentication token"}` |
| 404 Workspace not found | 404 | `{"detail": "Workspace with id '...' not found"}` |
| 403 Not a member | 403 | `{"detail": "Not a member of this workspace"}` |
| 403 Insufficient role | 403 | `{"detail": "Admin access required"}` |
| 403 Not owner | 403 | `{"detail": "Only the workspace owner can perform this action"}` |

---

## 4. LLM Config Resolution

Resolution occurs at extraction time (in `ExtractFromStoryUseCase` or in `ExtractionService`):

```python
async def resolve_llm_config(
    workspace_id: UUID,
    config_repo: WorkspaceLLMConfigRepository,
    settings: Settings,
) -> LLMConfig:
    """Resolve LLM config: workspace override → global defaults."""
    ws_config = await config_repo.get(workspace_id)
    if ws_config is None:
        return LLMConfig(
            model=settings.default_llm_model,
            temperature=0.1,
            max_tokens=2048,
            timeout=settings.llm_timeout,
        )
    return LLMConfig(
        model=ws_config.model or settings.default_llm_model,
        temperature=ws_config.temperature if ws_config.temperature is not None else 0.1,
        max_tokens=ws_config.max_tokens or 2048,
        timeout=settings.llm_timeout,
    )
```

Resolution is **read-time only** — no DB writes, no scheduled jobs. The workspace's `LLMConfigResponse` endpoint shows the resolved values to the admin (merged with defaults), so the UI matches what extraction will use.

---

## 5. Prompt Resolution

Same pattern as LLM config — read-time fallback:

```python
async def resolve_prompt(
    workspace_id: UUID,
    prompt_repo: WorkspacePromptRepository,
    prompt_manager: PromptManager,
) -> dict:
    """Resolve prompt: workspace override → global default."""
    ws_prompt = await prompt_repo.get(workspace_id)
    return {
        "system_prompt": (
            ws_prompt.system_prompt
            if ws_prompt and ws_prompt.system_prompt
            else prompt_manager.render_system_prompt()
        ),
        "instruction_template": (
            ws_prompt.instruction_template
            if ws_prompt and ws_prompt.instruction_template
            else prompt_manager.render("task_generation.j2", user_story="", examples="")
        ),
        "few_shot_examples": (
            ws_prompt.few_shot_examples
            if ws_prompt and ws_prompt.few_shot_examples
            else prompt_manager.default_few_shot()  # TODO: add this method
        ),
    }
```

The resolved prompts are injected into the extraction flow alongside the LLM config. If a workspace has a custom `instruction_template`, it replaces `task_generation.j2` entirely. If a custom `system_prompt`, it replaces the hardcoded string in `PromptManager.render_system_prompt()`.

---

## 6. Frontend Component Tree

```
MainLayout.astro
├── ThemeScript (inline)
├── Header.astro (inline — contains UserMenu, LangToggle, ThemeToggle)
├── Sidebar.tsx (React island, client:load)
│   ├── WorkspaceSwitcher (TeamSwitcher variant)
│   │   ├── Current workspace badge [icon + name + chevron]
│   │   ├── Dropdown:
│   │   │   ├── Workspace list (searchable)
│   │   │   │   └── Each item: icon + name + slug
│   │   │   ├── Separator
│   │   │   └── "+ Add workspace" action → modal/page
│   ├── Nav links (shadcn sidebar-menu)
│   │   ├── Dashboard (LayoutDashboard)
│   │   ├── Projects (FolderKanban)
│   │   ├── Stories (FileText)
│   │   ├── Kanban (KanbanSquare)
│   │   ├── Export (Upload)
│   │   └── Settings (Settings) — only shown if admin
│   └── Sidebar footer: collapse toggle, version
├── Main content slot
│   └── Page-specific islands (Dashboard, ProjectsList, etc.)
└── Toaster (client:only)
```

**Workspace context flow:**

1. `WorkspaceSwitcher` selects workspace → calls `workspaceStore.setCurrentWorkspace(w)`
2. `workspaceStore` stores `currentWorkspace` and its `id`
3. `projectStore.fetchProjects()` reads `currentWorkspace.id`, calls API with workspace scope
4. `storyStore.fetchStories()` reads project's workspace context
5. Astro View Transitions preserve the Zustand state across page navigations
6. On page mount, if `currentWorkspace` is null (first load), `workspaceStore` fetches the list and selects the first one

---

## 7. Migration Plan (Implementation Order)

**Phase 1 — Data Model** (~10 files)
1. Workspace, WorkspaceMember, WorkspaceLLMConfig, WorkspacePrompt entities → `domain/entities/`
2. Exceptions: `NotWorkspaceMember`, `InsufficientRole`, `OwnerTransferError` → `domain/entities/exceptions.py`
3. Repository ports (4 new) → `domain/ports/`
4. Modified ports (ProjectRepository, UserStoryRepository, TaskRepository, ExtractionRepository)
5. ORM Models → `infrastructure/database/models/`
6. Alembic migration #0007

**Phase 2 — Infrastructure** (~5 files)
7. SQLAlchemy implementations for 4 new repositories
8. Modified SQLAlchemyProjectRepository (list_by_workspace)
9. Add `list_by_workspace` to story/task/extraction repos

**Phase 3 — API Schemas + Dependencies** (~6 files)
10. API schemas (workspace, workspace_member, workspace_llm_config, workspace_prompt)
11. Modified ProjectRequest/Response (workspace_id, created_by)
12. Dependencies: get_workspace_for_user, require_admin, require_owner

**Phase 4 — API Routes** (~4 files)
13. Workspace CRUD + members route file
14. Workspace settings route file (LLM config, prompts)
15. Modified projects, stories, tasks, extractions, extraction routes

**Phase 5 — App Wiring** (~2 files)
16. Register new routes in `api/app.py`
17. Register new error handlers
18. Register new models in `models/__init__.py`, repos in `repositories/__init__.py`

**Phase 6 — Frontend Core** (~6 files)
19. `types/workspace.ts`
20. `schemas/workspace.ts`
21. `lib/workspace-api.ts`, `lib/llm-config-api.ts`, `lib/prompts-api.ts`
22. `stores/workspaceStore.ts`
23. Modified `types/project.ts`, `stores/projectStore.ts`, `stores/storyStore.ts`

**Phase 7 — Frontend UI** (~4 files)
24. `Sidebar.tsx` (React island with shadcn sidebar-07 + TeamSwitcher)
25. Modified `MainLayout.astro`
26. Delete `components/astro/Sidebar.astro`
27. Modified page `.astro` files to pass workspace context

**Phase 8 — Frontend Settings** (~2 files)
28. Workspace settings page (LLM config editor, prompt editor)
29. Member management UI in workspace settings

---

## 8. Key Design Details

### Slug Generation

```python
import re

def generate_slug(name: str, existing_slugs: set[str]) -> str:
    """Generate a unique slug from a workspace name.

    Examples:
        "Acme Project" → "acme-project"
        "Acme Project" (taken) → "acme-project-1"
        "My  Team!!" → "my-team"
    """
    base = re.sub(r"[^a-z0-9-]", "", name.lower().replace(" ", "-"))
    base = re.sub(r"-+", "-", base).strip("-")
    if not base:
        base = "workspace"
    slug = base
    counter = 1
    while slug in existing_slugs:
        slug = f"{base}-{counter}"
        counter += 1
    return slug
```

Used in `CreateWorkspaceUseCase` — the use case loads existing slugs via `repo.list_slugs()` and generates a unique one. If user provides an explicit slug, validate it matches the pattern and check uniqueness.

### Role Enum

Use `StrEnum` (Python 3.11+) — same pattern as `UserStoryStatus`. Stored as `String(20)` in DB.

```python
class WorkspaceRole(StrEnum):
    ADMIN = auto()   # "admin"
    MEMBER = auto()  # "member"
```

String storage is debuggable and readable in the DB. If we need integer storage in the future, we add a migration. For MVP, string is simpler and joins without casts.

### Owner Transfer — Atomic Transaction

```python
async def transfer_ownership(
    self, workspace_id: UUID, current_owner_id: UUID, new_owner_id: UUID
) -> None:
    async with self._session.begin():
        ws = await self._session.get(WorkspaceModel, workspace_id)
        if ws.owner_id != current_owner_id:
            raise OwnerTransferError("Only the current owner can transfer ownership")

        # Verify new owner is an admin
        new_owner_member = await self._session.execute(
            select(WorkspaceMemberModel).where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.user_id == new_owner_id,
                WorkspaceMemberModel.role == "admin",
            )
        )
        if not new_owner_member.scalar_one_or_none():
            raise OwnerTransferError("New owner must be an admin of this workspace")

        # Atomic: update workspace owner + demote old owner to admin
        ws.owner_id = new_owner_id
        await self._session.execute(
            update(WorkspaceMemberModel)
            .where(
                WorkspaceMemberModel.workspace_id == workspace_id,
                WorkspaceMemberModel.user_id == current_owner_id,
            )
            .values(role="admin")
        )
```

### LLMConfig Fields — Required vs Optional

| Field | Required at upsert? | Nullable in DB | Fallback |
|-------|--------------------|----------------|----------|
| `provider` | Yes | No | None |
| `model` | No | Yes | `settings.default_llm_model` |
| `temperature` | No | Yes | `0.1` |
| `max_tokens` | No | Yes | `2048` |
| `base_url` | No | Yes | `settings.ollama_base_url` |

### Prompt Fallback — Read-Time Resolution

No DB writes on fallback. `GET /settings/prompts` returns the merged config (workspace overrides merged on top of defaults). The endpoint shows admins what extraction WILL use — not what's stored in the workspace_prompts table.

### Delete Workspace — Hard Delete with CASCADE

PostgreSQL `ON DELETE CASCADE` at the FK level handles the chain:

```
workspaces → workspace_members (CASCADE)
workspaces → workspace_llm_configs (CASCADE)
workspaces → workspace_prompts (CASCADE)
workspaces → projects (CASCADE) → user_stories (CASCADE) → tasks (CASCADE)
                                                    → extractions (CASCADE)
```

Frontend requires a confirmation dialog with text input ("Type DELETE to confirm"). Soft-delete deferred — if needed post-MVP, add `deleted_at` column to workspace and filter in all queries.

---

## 9. Error Handling

| Scenario | HTTP | detail | type |
|----------|------|--------|------|
| Workspace not found | 404 | `"Workspace with id '{id}' not found"` | `entity_not_found` |
| User not a member | 403 | `"Not a member of this workspace"` | `not_workspace_member` |
| Insufficient role (needs admin) | 403 | `"Admin access required"` | `insufficient_role` |
| Not the workspace owner | 403 | `"Only the workspace owner can perform this action"` | `not_workspace_owner` |
| Duplicate slug | 409 | `"Workspace with slug '{slug}' already exists"` | `duplicate_entity` |
| Cannot remove owner | 400 | `"The workspace owner cannot be removed. Transfer ownership first."` | `cannot_remove_owner` |
| Cannot remove self if last admin | 400 | `"Cannot remove yourself as the last admin. Promote another member first."` | `last_admin` |
| Duplicate member | 409 | `"User is already a member of this workspace"` | `duplicate_entity` |
| Target user not an admin for transfer | 400 | `"New owner must be an admin of this workspace"` | `target_not_admin` |
| Target user not found for transfer | 400 | `"User with id '{id}' is not a member of this workspace"` | `user_not_member` |

All error responses follow the existing format: `{"detail": "...", "type": "..."}`. New error types registered in `api/app.py` and handlers in `api/errors.py`.

---

## Open Questions

- [ ] **Auth mechanism**: Current `get_current_user` uses headers (X-Storico-Internal-Token + X-Storico-User-Id). If Auth.js is fully wired, the dependency should switch to JWT/session validation. For MVP, keep the header-based approach and document the eventual migration.
- [ ] **Workspace ID in non-project-scoped routes**: The extraction route `/api/v1/extract` currently takes a `user_story_id` without workspace context. How does workspace scope resolve here? Via the story's project → workspace. The `get_workspace_for_user` dep needs to resolve through this chain, not from the URL path. This may need a custom resolver.
- [ ] **Dev data deletion**: The proposal says "delete existing projects in dev". This should be an Alembic migration step: `op.execute("DELETE FROM extractions; DELETE FROM tasks; DELETE FROM user_stories; DELETE FROM projects;")` — or simply recreate the DB in dev. Need to decide the exact approach.
