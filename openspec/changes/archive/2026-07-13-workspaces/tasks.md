# Tasks: Workspaces as Central Organizational Entity

**Depends on**: `openspec/changes/workspaces/spec.md`, `openspec/changes/workspaces/design.md`
**Implementation order**: 8 phases, 34 tasks, ~2,800-3,200 estimated total changed lines
**PR classification**: `size:exception` (exceeds 400 lines) — approved as single PR
**JWT auth migration**: Included in Phase 3 (replaces `X-Storico-Internal-Token` + `X-Storico-User-Id` header auth with `Authorization: Bearer <JWT>`)

---

## Phase 1 — Data Model (Backend Core)

*Creates domain entities, repository ports, ORM models, and the Alembic migration. Foundation for everything else.*

> ✅ **Phase 1 complete** — all 6 tasks implemented, verified, and committed.

### T-001: ✅ Create workspace domain entities

| Field | Value |
|-------|-------|
| **Description** | Create four new domain entity dataclasses in `domain/entities/` following the existing frozen dataclass + slots pattern from `project.py`. Entities: `Workspace`, `WorkspaceMember`, `WorkspaceLLMConfig`, `WorkspacePrompt`. Also add `WorkspaceRole(StrEnum)` — see design section 8 for invariants. |
| **Pattern** | `@dataclass(frozen=True, slots=True)` with `field(default_factory=uuid4)` for `id`, `field(default_factory=lambda: datetime.now(UTC))` for timestamps. `WorkspaceRole` uses `StrEnum` with `auto()` — same as `UserStoryStatus`. |
| **Key invariants** | Workspace: `name` not empty, `slug` unique globally, `owner_id` must reference an existing member. WorkspaceMember: exactly one `ADMIN` who is `owner_id`, `UNIQUE(workspace_id, user_id)`. WorkspaceLLMConfig: `provider` required, all other fields nullable. WorkspacePrompt: all fields nullable. |
| **Files to create** | `src/storico/domain/entities/workspace.py`, `src/storico/domain/entities/workspace_member.py`, `src/storico/domain/entities/workspace_llm_config.py`, `src/storico/domain/entities/workspace_prompt.py` |
| **Dependencies** | None |
| **Verification** | `python -c "from storico.domain.entities.workspace import Workspace; w = Workspace(name='Test', slug='test', owner_id=uuid4()); print(w)"` — no import errors, instantiation works |
| **Effort** | Small |

### T-002: ✅ Add workspace exceptions

| Field | Value |
|-------|-------|
| **Description** | Add new exception classes to `domain/entities/exceptions.py`: `NotWorkspaceMember`, `InsufficientRole`, `OwnerTransferError`, `LastAdminError`, `CannotRemoveOwnerError`. Inherit from `RepositoryError` (or `Exception` for use-case-level errors). Follow the existing pattern with `__init__` accepting meaningful parameters. |
| **Pattern** | Follow existing exception classes: `EntityNotFound(entity_type, entity_id)`, `DuplicateEntity(entity_type, field, value)`, etc. `OwnerTransferError` takes a `message` string. |
| **Files to modify** | `src/storico/domain/entities/exceptions.py` |
| **Dependencies** | None |
| **Verification** | Import all new exceptions, ensure they are exported from `__init__.py` |
| **Effort** | Small |

### T-003: ✅ Create workspace repository ports (4 new)

| Field | Value |
|-------|-------|
| **Description** | Create four new `ABC` repository ports in `domain/ports/`: `WorkspaceRepository` (`save`, `find_by_id`, `list_by_user`, `find_by_slug`, `delete`, `count_members`, `list_slugs`), `WorkspaceMemberRepository` (`add`, `remove`, `update_role`, `find_by_workspace_and_user`, `list_by_workspace`, `list_by_user`, `transfer_ownership`, `count_admins`), `WorkspaceLLMConfigRepository` (`get(workspace_id)`, `upsert(config)`), `WorkspacePromptRepository` (`get(workspace_id)`, `upsert(prompt)`). |
| **Pattern** | Follow `ProjectRepository(ABC)` pattern: `@abstractmethod`, `async`, return types as `Entity | None` or `list[Entity]`. Each method has docstring. |
| **Files to create** | `src/storico/domain/ports/workspace_repository.py`, `src/storico/domain/ports/workspace_member_repository.py`, `src/storico/domain/ports/workspace_llm_config_repository.py`, `src/storico/domain/ports/workspace_prompt_repository.py` |
| **Dependencies** | T-001 |
| **Verification** | `python -c "from storico.domain.ports.workspace_repository import WorkspaceRepository; print(WorkspaceRepository.__abstractmethods__)"` |
| **Effort** | Small |

### T-004: ✅ Modify existing repository ports (ProjectRepository + others)

| Field | Value |
|-------|-------|
| **Description** | Modify `ProjectRepository`: rename `list_by_owner` → `list_by_workspace(workspace_id)`, add `count_by_workspace(workspace_id)`, keep `list()` for admin-only global view. Add `list_by_workspace(workspace_id)` to `UserStoryRepository`, `TaskRepository`, `ExtractionRepository`. These will JOIN through related models to filter by workspace_id. |
| **Pattern** | Keep existing methods unless explicitly removed. `list_by_owner` is replaced, not removed — the interface changes, so update all callers later. Use `# TODO: migrate to workspace_id` temporarily on the old method. |
| **Files to modify** | `src/storico/domain/ports/project_repository.py`, `src/storico/domain/ports/user_story_repository.py`, `src/storico/domain/ports/task_repository.py`, `src/storico/domain/ports/extraction_repository.py` |
| **Dependencies** | T-003 |
| **Verification** | Import each modified port, verify new methods are present |
| **Effort** | Small |

### T-005: ✅ Create workspace ORM models (4 new + modify ProjectModel)

| Field | Value |
|-------|-------|
| **Description** | Create four new ORM models in `infrastructure/database/models/`: `WorkspaceModel`, `WorkspaceMemberModel`, `WorkspaceLLMConfigModel`, `WorkspacePromptModel`. Follow the `Base` + `Mapped` + `mapped_column` pattern from `ProjectModel`. Add correct FK relationships with `ondelete="CASCADE"` and `UniqueConstraint` where specified. Also modify `ProjectModel`: replace `owner_id` column with `workspace_id` (FK→workspaces, CASCADE) and add `created_by` (FK→users, nullable). Add relationship to `workspace`. |
| **Pattern** | Follow `ProjectModel` exactly: `__tablename__`, `Mapped[UUID]` columns, `ForeignKey("tablename.column", ondelete="CASCADE")`, `UniqueConstraint` in `__table_args__` for compound keys. UUID PKs use `default=uuid4` on the mapped_column. |
| **Files to create** | `src/storico/infrastructure/database/models/workspace.py`, `src/storico/infrastructure/database/models/workspace_member.py`, `src/storico/infrastructure/database/models/workspace_llm_config.py`, `src/storico/infrastructure/database/models/workspace_prompt.py` |
| **Files to modify** | `src/storico/infrastructure/database/models/project.py` |
| **Dependencies** | T-001 |
| **Verification** | `python -c "from storico.infrastructure.database.models import WorkspaceModel; print(WorkspaceModel.__tablename__)"` |
| **Effort** | Medium (4 new files + 1 modified, relationships require care) |

### T-006: ✅ Create Alembic migration #0007

| Field | Value |
|-------|-------|
| **Description** | Generate a new Alembic revision (`0007_add_workspaces.py`). DDL only — no data migration per user decision. Steps: (1) Create `workspaces` table, (2) Create `workspace_members` table with `UniqueConstraint(workspace_id, user_id)`, (3) Create `workspace_llm_configs` table with unique `workspace_id`, (4) Create `workspace_prompts` table with unique `workspace_id`, (5) `ALTER TABLE projects DROP COLUMN owner_id` (drop FK first), (6) `ALTER TABLE projects ADD COLUMN workspace_id UUID NOT NULL REFERENCES workspaces(id) ON DELETE CASCADE`, (7) `ALTER TABLE projects ADD COLUMN created_by UUID REFERENCES users(id)`. Use `op.create_foreign_key()` / `op.drop_constraint()` for FK management. The projects table already has FK `owner_id → users(id)` — drop that constraint first, then drop the column. |
| **Pattern** | Follow existing migration files in `alembic/versions/`. Use `op.create_table()`, `op.create_unique_constraint()`, `op.drop_constraint()`, `op.create_foreign_key()`, `op.drop_column()`, `op.add_column()`. |
| **Files to create** | `src/storico/infrastructure/database/alembic/versions/0007_add_workspaces.py` |
| **Dependencies** | T-005 |
| **Verification** | `alembic upgrade head` succeeds without errors. `alembic history` shows 0007. Verify with `psql` that all 4 new tables exist, `projects` has `workspace_id` + `created_by` and no `owner_id`. |
| **Effort** | Medium |

---

## Phase 2 — Infrastructure (Backend)

*Implements the repository ports as concrete SQLAlchemy classes.*

### T-007: Create SQLAlchemy workspace repository implementations (4 new)

| Field | Value |
|-------|-------|
| **Description** | Implement all four repository ports as SQLAlchemy classes: `SQLAlchemyWorkspaceRepository`, `SQLAlchemyWorkspaceMemberRepository`, `SQLAlchemyWorkspaceLLMConfigRepository`, `SQLAlchemyWorkspacePromptRepository`. Each follows the `_to_domain()` / `_to_orm_kwargs()` dual-method pattern from `SQLAlchemyProjectRepository`. The `transfer_ownership` method in `SQLAlchemyWorkspaceMemberRepository` uses an async DB transaction (see design section 8 — atomic transaction). `WorkspaceLLMConfigRepository.upsert()` and `WorkspacePromptRepository.upsert()` use a SELECT-then-INSERT-or-UPDATE pattern. |
| **Pattern** | Constructor takes `AsyncSession`, private `_session`. `_to_domain(model)` maps ORM → domain entity. `_to_orm_kwargs(entity)` maps domain entity → dict for ORM constructor. Error handling wraps SQLAlchemy errors in `RepositoryError`. Use `select()`, `get()`, `delete()`, `update()`, etc. from SQLAlchemy. |
| **Files to create** | `src/storico/infrastructure/database/repositories/workspace_repository.py`, `src/storico/infrastructure/database/repositories/workspace_member_repository.py`, `src/storico/infrastructure/database/repositories/workspace_llm_config_repository.py`, `src/storico/infrastructure/database/repositories/workspace_prompt_repository.py` |
| **Dependencies** | T-003, T-005 |
| **Verification** | Import each repository, verify `_to_domain` and `_to_orm_kwargs` methods exist. Unit test with a mock or test DB session. |
| **Effort** | Large (4 repos with transaction logic in member repo) |

### T-008: Modify SQLAlchemyProjectRepository

| Field | Value |
|-------|-------|
| **Description** | Add `list_by_workspace(workspace_id: UUID) -> list[Project]` and `count_by_workspace(workspace_id: UUID) -> int` methods. Rename `list_by_owner` to `list_by_workspace` and update its SELECT filter. Update `_to_domain()` and `_to_orm_kwargs()` to use `workspace_id` instead of `owner_id` and include `created_by`. |
| **Pattern** | SELECT with `ProjectModel.workspace_id == workspace_id`. `_to_domain(model)` returns `Project(workspace_id=model.workspace_id, created_by=model.created_by, ...)`. |
| **Files to modify** | `src/storico/infrastructure/database/repositories/project_repository.py` |
| **Dependencies** | T-004, T-005, T-006 |
| **Verification** | Import repo, call `list_by_workspace()` with a test session. |
| **Effort** | Small |

### T-009: Add `list_by_workspace` to story/task/extraction repos

| Field | Value |
|-------|-------|
| **Description** | Add `list_by_workspace(workspace_id: UUID) -> list[Entity]` method to `SQLAlchemyUserStoryRepository`, `SQLAlchemyTaskRepository`, and `SQLAlchemyExtractionRepository`. Stories join through `ProjectModel.workspace_id`. Tasks join through `UserStoryModel → ProjectModel.workspace_id`. Extractions join through `UserStoryModel → ProjectModel.workspace_id`. |
| **Pattern** | Use `select(StoryModel).join(ProjectModel).where(ProjectModel.workspace_id == workspace_id)` pattern. |
| **Files to modify** | `src/storico/infrastructure/database/repositories/user_story_repository.py`, `src/storico/infrastructure/database/repositories/task_repository.py`, `src/storico/infrastructure/database/repositories/extraction_repository.py` |
| **Dependencies** | T-004, T-005, T-006 |
| **Verification** | Import each repo, call `list_by_workspace()` with a test session. |
| **Effort** | Small |

---

## Phase 3 — API Schemas + Auth (Backend)

*Pydantic schemas for the new entities and the JWT authentication migration.*

### T-010: Create API schemas for workspaces (4 new files)

| Field | Value |
|-------|-------|
| **Description** | Create four new Pydantic schema files in `api/schemas/`: (1) `workspace.py` — `CreateWorkspaceRequest` (name: str, slug: optional str), `UpdateWorkspaceRequest` (name: optional, slug: optional), `WorkspaceResponse` (id, name, slug, owner_id, role, member_count, created_at, updated_at), `WorkspaceListResponse` (workspaces: list[WorkspaceResponse]). (2) `workspace_member.py` — `AddMemberRequest` (user_id: UUID), `MemberResponse` (user_id, name, email, avatar_url, role, created_at), `MemberListResponse`, `TransferOwnershipRequest` (new_owner_id: UUID). (3) `workspace_llm_config.py` — `LLMConfigRequest` (all optional fields), `LLMConfigResponse` (resolved fields — never null). (4) `workspace_prompt.py` — `PromptRequest` (all optional), `PromptResponse` (resolved). |
| **Pattern** | Request schemas: `model_config = ConfigDict(extra="forbid")`. Response schemas: `model_config = ConfigDict(from_attributes=True)`. Use `Field(..., min_length=1)` for required strings, `Field(None)` for optional. |
| **Files to create** | `src/storico/api/schemas/workspace.py`, `src/storico/api/schemas/workspace_member.py`, `src/storico/api/schemas/workspace_llm_config.py`, `src/storico/api/schemas/workspace_prompt.py` |
| **Dependencies** | T-001, T-003 |
| **Verification** | `python -c "from storico.api.schemas.workspace import CreateWorkspaceRequest; r = CreateWorkspaceRequest(name='Test'); print(r)"` |
| **Effort** | Small |

### T-011: Modify project schemas

| Field | Value |
|-------|-------|
| **Description** | In `api/schemas/project.py`: Replace `owner_id: UUID` with `workspace_id: UUID` and `created_by: UUID | None = None` in `CreateProjectRequest` and `ProjectResponse`. Remove `owner_id` from create request body — derive `workspace_id` from URL path and `created_by` from auth context. |
| **Pattern** | Follow existing `ConfigDict` pattern. |
| **Files to modify** | `src/storico/api/schemas/project.py` |
| **Dependencies** | T-010 |
| **Verification** | `python -c "from storico.api.schemas.project import CreateProjectRequest, ProjectResponse; print(CreateProjectRequest.__annotations__)"` |
| **Effort** | Small |

### T-012: Migrate auth from proxy headers to JWT

| Field | Value |
|-------|-------|
| **Description** | **CRITICAL TASK** — this replaces the entire auth mechanism. In `api/dependencies.py`:
1. Remove `INTERNAL_TOKEN_HEADER` and `USER_ID_HEADER` constants.
2. Rewrite `get_current_user()` to read `Authorization: Bearer <token>` header.
3. Validate the JWT using `PyJWT` library — decode with `jwt.decode(token, secret, algorithms=["HS256"])`.
4. Extract `user_id` from JWT claims (the `sub` claim set in Auth.js JWT callback on the frontend).
5. Look up user from repository.
6. Remove the `from storico.config.settings import Settings` late import (keep only the one needed for secret).
7. Add `PyJWT` to `pyproject.toml` dependencies.

In `backend/config/settings.py`:
8. Rename `auth_internal_token` → add `auth_jwt_secret` if missing (or reuse `AUTH_SECRET` env var).

In `frontend/auth.config.ts`:
9. The `jwt` callback already sets `token.id` and `token.email`. Ensure the JWT is signed with a secret that FastAPI can verify. The frontend proxy needs to forward the `Authorization` header as-is to the FastAPI backend. Remove the `X-Storico-Internal-Token` and `X-Storico-User-Id` headers from the auth sync call.

In `frontend/src/lib/config.ts`:
10. Remove `internalToken` — no longer needed.

In `frontend/src/middleware.ts`:
11. Ensure the Astro API proxy passes the `Authorization` header from the Auth.js session JWT to the FastAPI backend. The Astro middleware should forward `Authorization: Bearer <jwt>` when proxying to `/api/v1/*`.

In `frontend/auth.config.ts`:
12. Remove `X-Storico-Internal-Token` header from the auth sync fetch. Add the `Authorization: Bearer <token>` header pattern.

**Backend route impact**: All routes using `Depends(get_current_user)` automatically get the new auth — no route changes needed for the auth mechanism itself.
**Frontend API client impact**: The `api.ts` client already allows arbitrary headers. The proxy layer (Astro middleware or Vercel) must inject the JWT into requests to `/api/v1/*`.
| **Pattern** | Use `jwt.decode()` with `algorithms=["HS256"]`. Secret comes from `settings.auth_jwt_secret` (use same value as `AUTH_SECRET` from Auth.js). Error responses: 401 with `{"detail": "Invalid or missing authentication token"}`. |
| **Files to create** | None |
| **Files to modify** | `src/storico/api/dependencies.py`, `src/storico/config/settings.py`, `backend/pyproject.toml` (add `PyJWT>=2.9.0`), `frontend/auth.config.ts`, `frontend/src/lib/config.ts`, `frontend/src/middleware.ts` |
| **Dependencies** | T-004 (UserRepository already exists) |
| **Verification** | Test: call any protected endpoint with `Authorization: Bearer <valid-jwt>` → 200. Call without auth → 401. Call with invalid token → 401. The JWT should be generated by Auth.js on the frontend side; for dev testing, generate one manually with `jwt.encode({"sub": user_id}, secret)`. |
| **Effort** | **Large** (touches auth chain, frontend proxy, and all route files) |

### T-013: Create workspace membership dependencies

| Field | Value |
|-------|-------|
| **Description** | Add three new dependency functions to `api/dependencies.py`:
1. `get_workspace_for_user(workspace_id: UUID = Path(...), current_user: User = Depends(get_current_user), ...) -> tuple[Workspace, WorkspaceRole]` — loads workspace + membership, 404 if workspace missing (no 403 for workspace GET to avoid leaking existence), 403 if not member.
2. `require_admin(ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user)) -> tuple[Workspace, WorkspaceRole]` — checks role == ADMIN, raises 403 if not.
3. `require_owner(ctx: tuple[Workspace, WorkspaceRole] = Depends(require_admin)) -> Workspace` — checks `workspace.owner_id == current_user.id`, raises 403 if not.

All follow the 4-layer chain from the design (section 3). Error responses follow the `{"detail": "...", "type": "..."}` format from the error table in the design.

**Note**: `require_owner` needs access to `current_user.id` — this must be resolved from the request context or passed through the dependency chain. Options: (a) have `get_current_user` store user in `request.state`, (b) pass user through the chain as a tuple parameter. Prefer option (b): `get_workspace_for_user` already depends on `get_current_user`, so `require_owner` can call `get_current_user` again (FastAPI caches the result per request).
| **Pattern** | Use `Depends(get_repository(...))` for repo injections. Raise `HTTPException` with status code and detail dict. |
| **Files to modify** | `src/storico/api/dependencies.py` |
| **Dependencies** | T-007, T-012 |
| **Verification** | Import all three deps, verify they resolve correctly in a test route. |
| **Effort** | Medium |

---

## Phase 4 — API Routes (Backend)

*All route files — new workspace routes and modifications to existing ones.*

### T-014: ✅ Create workspace CRUD + members routes

| Field | Value |
|-------|-------|
| **Description** | Create `api/routes/workspaces.py` with all workspace management routes under `APIRouter(prefix="/api/v1/workspaces", tags=["workspaces"])`:

**Workspace CRUD**:
- `POST /` — Create workspace. Call `CreateWorkspaceUseCase.execute(name, slug, user)`. Returns 201 with `WorkspaceResponse`. (Use case will be implemented inline in the route or as a simple function call — see T-016.)
- `GET /` — List user's workspaces. `member_repo.list_by_user(current_user.id)`. Returns 200 with `WorkspaceListResponse`.
- `GET /{workspace_id}` — Get workspace. `get_workspace_for_user` → return workspace + role. Return 404 not 403.
- `PUT /{workspace_id}` — Update workspace. `require_admin` → update name/slug.
- `DELETE /{workspace_id}` — Delete workspace. `require_admin` → `ws_repo.delete(workspace_id)`. 204 No Content.

**Member management**:
- `GET /{workspace_id}/members` — `require_admin` → `member_repo.list_by_workspace()`. 200.
- `POST /{workspace_id}/members` — `require_admin`. Validate user exists. Add member with `role="member"`. 201.
- `PUT /{workspace_id}/members/{user_id}` — `require_admin`. Change role. Cannot demote owner. 200.
- `DELETE /{workspace_id}/members/{user_id}` — `require_admin`. Cannot remove owner, cannot remove self if last admin. 204.
- `POST /{workspace_id}/transfer` — `require_owner`. Transfer ownership. `TransferOwnershipUseCase.execute()`. 200.

| **Pattern** | Use `Annotated` type aliases for common deps (like `ProjectRepoDep`). Use `Depends(get_repository(...))` for repos. Use `Depends(require_admin)` / `Depends(require_owner)` for auth gates. Follow `@router.post("/", status_code=201)` pattern. |
| **Files to create** | `src/storico/api/routes/workspaces.py` |
| **Dependencies** | T-010, T-013, T-016 (use cases — can be done after if inline) |
| **Verification** | Start the server with `uvicorn storico.api.app:create_app --factory`, hit all endpoints with HTTPie/curl. Test: create ws → list → add member → change role → transfer → delete. |
| **Effort** | **Large** (~300-400 lines for all CRUD + member + transfer routes) |

### T-015: ✅ Create workspace settings routes (LLM config + prompts)

| Field | Value |
|-------|-------|
| **Description** | Create `api/routes/workspace_settings.py` with routes under `APIRouter(prefix="/api/v1/workspaces/{workspace_id}/settings", tags=["workspace-settings"])`:

**LLM config**:
- `GET /llm` — `require_admin` → `config_repo.get(workspace_id)`. If None, return resolved global defaults (use `resolve_llm_config` function from design section 4). 200.
- `PUT /llm` — `require_admin` → `config_repo.upsert()`. Only update provided fields. Return resolved config. 200.

**Prompts**:
- `GET /prompts` — `require_admin` → `prompt_repo.get(workspace_id)`. If None, return global defaults. 200.
- `PUT /prompts` — `require_admin` → `prompt_repo.upsert()`. Only update provided fields. Return resolved prompts. 200.

Include the `resolve_llm_config` and `resolve_prompt` helper functions (can live in this file or a shared `services/` module). These functions implement the read-time fallback chain from design sections 4 and 5.

**Config resolution** (design section 4):
```python
async def resolve_llm_config(workspace_id, config_repo, settings) -> LLMConfigResponse:
    ws_config = await config_repo.get(workspace_id)
    if ws_config is None:
        return global defaults from settings
    return merge(ws_config fields with settings defaults for null fields)
```

**Prompt resolution** (design section 5):
```python
async def resolve_prompt(workspace_id, prompt_repo, prompt_manager) -> PromptResponse:
    ws_prompt = await prompt_repo.get(workspace_id)
    return merge(ws_prompt with global prompt defaults for null fields)
```
| **Pattern** | Same as workspace routes. Uses `require_admin` for all settings routes. |
| **Files to create** | `src/storico/api/routes/workspace_settings.py` |
| **Dependencies** | T-010, T-013 |
| **Verification** | `GET /settings/llm` returns global defaults when no config set. `PUT /settings/llm` saves, `GET` returns saved values. `GET /settings/prompts` same pattern. |
| **Effort** | Medium |

### T-016: ✅ Create workspace use cases

| Field | Value |
|-------|-------|
| **Description** | Create `application/workspaces/` package with these use case classes:

1. **`CreateWorkspaceUseCase`**: Validate name not empty, generate slug via `generate_slug()` function (design section 8) checking uniqueness against `repo.list_slugs()`. Start a DB transaction, create workspace + owner member (role=ADMIN). Commit.

2. **`AddMemberUseCase`**: Validate workspace exists, validate user exists (call `user_repo.find_by_id`), validate not already a member (`member_repo.find_by_workspace_and_user`), add with role `member`.

3. **`RemoveMemberUseCase`**: Validate member exists, validate not workspace owner, validate not last admin (`member_repo.count_admins(ws_id) > 1` or caller is not self), delete membership.

4. **`TransferOwnershipUseCase`**: Validate current owner matches workspace.owner_id, validate new owner is an admin (role=ADMIN), atomic transaction: update workspace.owner_id + demote old owner to admin. Uses `member_repo.transfer_ownership()`.

Each use case is a class with an `async execute(...)` method, following the pattern in `application/extraction/extract_from_story.py`.

**`generate_slug` helper**: Implement the slug generation function from design section 8 — `re.sub()` to parameterize, counter loop for uniqueness.

**Alternative**: If the use case layer feels too heavy for this phase, the slug generation + create workspace logic can be inline in the route handler. The design specifies use cases for clarity. Use whichever approach keeps the route handlers thin.

| **Pattern** | Use case class with `execute()` method. Accepts repository ports as constructor dependencies or method parameters. Raises domain exceptions that `api/errors.py` handlers map to HTTP responses. |
| **Files to create** | `src/storico/application/workspaces/__init__.py`, `src/storico/application/workspaces/create_workspace.py`, `src/storico/application/workspaces/manage_members.py`, `src/storico/application/workspaces/transfer_ownership.py`, `src/storico/application/workspaces/slug.py` |
| **Dependencies** | T-001, T-002, T-003, T-007 |
| **Verification** | Unit tests for each use case with mocked repos. Test create → slug uniqueness → transfer atomicity. |
| **Effort** | Medium |

### T-017: ✅ Modify projects route for workspace scoping

| Field | Value |
|-------|-------|
| **Description** | Modify `api/routes/projects.py`:
1. Change router prefix from `/api/v1/projects` to retain backward compatibility OR move under workspace. Decision: create a **NEW router** with prefix `/api/v1/workspaces/{workspace_id}/projects` and keep the old routes as deprecated (410 Gone).
2. All routes get `get_workspace_for_user` dep (member access, not admin).
3. `POST` route: derive `workspace_id` from URL path (from `get_workspace_for_user`), set `created_by = current_user.id`.
4. `GET /` list: filter by workspace_id using `repo.list_by_workspace(workspace_id)`.
5. `GET /{id}`, `PUT /{id}`, `DELETE /{id}`: verify project belongs to workspace before operating.

**Old route compatibility**: Add a deprecation warning: create a separate router with prefix `/api/v1/projects` that returns `410 Gone` with a `Location` header hint pointing to the new URL pattern. Or simply remove old prefix routes and let them 404. The spec says "returns 410 Gone or redirect". Implement 410 with a helpful message for the first version.

| **Files to modify** | `src/storico/api/routes/projects.py` |
| **Dependencies** | T-008, T-011, T-013 |
| **Verification** | `POST /api/v1/workspaces/{id}/projects` creates project with correct workspace_id. `GET /api/v1/workspaces/{id}/projects` returns only that workspace's projects. Old routes return 410. |
| **Effort** | Medium |

### T-018: ✅ Modify stories route (add workspace deps)

| Field | Value |
|-------|-------|
| **Description** | Modify `api/routes/stories.py`:
1. Add `get_workspace_for_user` dep to all routes — workspace context resolved from the story's project (story → project_id → workspace_id).
2. On `POST`: verify the project_id belongs to the user's workspace. Validate membership.
3. On `GET /{id}`: verify the story's project is in the user's accessible workspaces.
4. Add `list_by_workspace` query support: `GET /?workspace_id=...` filter.

The workspace_id isn't always in the URL for stories (they're still at `/api/v1/stories`). Add workspace scoping through a dependency that resolves the workspace from the story's project ID. This ensures cross-workspace access is blocked at the dependency level.

| **Files to modify** | `src/storico/api/routes/stories.py` |
| **Dependencies** | T-009, T-013 |
| **Verification** | A user in workspace A cannot access a story from workspace B's project. Stories are filtered by workspace. |
| **Effort** | Medium |

### T-019: ✅ Modify tasks route (add workspace deps)

| Field | Value |
|-------|-------|
| **Description** | Modify `api/routes/tasks.py`:
1. Add workspace scoping — all task access goes through story → project → workspace_id chain.
2. Add `get_workspace_for_user` dep or resolve workspace from the story's project.
3. Add `list_by_workspace` query support: `GET /?workspace_id=...`.

Same pattern as stories: workspace context resolved from the task's parent story's project.

| **Files to modify** | `src/storico/api/routes/tasks.py` |
| **Dependencies** | T-009, T-013 |
| **Verification** | Task access correctly scoped to workspace. Cross-workspace access returns 403. |
| **Effort** | Medium |

### T-020: ✅ Modify extractions route (add workspace deps)

| Field | Value |
|-------|-------|
| **Description** | Modify `api/routes/extractions.py`:
1. Add workspace scoping through the extraction's user_story → project → workspace_id chain.
2. Add `list_by_workspace` query support.

| **Files to modify** | `src/storico/api/routes/extractions.py` |
| **Dependencies** | T-009, T-013 |
| **Verification** | Extraction listing is scoped to workspace. |
| **Effort** | Small |

### T-021: ✅ Modify extraction route (re-prefix under workspace)

| Field | Value |
|-------|-------|
| **Description** | Modify `api/routes/extraction.py`:
1. Change route prefix from `/api/v1/extract` to `/api/v1/workspaces/{workspace_id}/extract` per user decision on open question #2.
2. The `workspace_id` from URL is used to validate membership via `get_workspace_for_user`.
3. The `user_story_id` in the body is used to verify the story belongs to a project within that workspace by walking `story → project.workspace_id` and comparing with URL `workspace_id`.
4. Current `get_current_user` dep already exists but is unused — now it's properly enforced.
5. Keep backward compatibility: old `/api/v1/extract/` returns 410 Gone with a helpful message about the new URL pattern.

| **Files to modify** | `src/storico/api/routes/extraction.py` |
| **Dependencies** | T-013, T-014 (for 410 pattern) |
| **Verification** | `POST /api/v1/workspaces/{id}/extract` works with workspace scope. Story must belong to the workspace's project. Old endpoint returns 410. |
| **Effort** | Medium |

---

## Phase 5 — App Wiring (Backend)

*Register new routes, error handlers, and module exports.*

### T-022: Register new routes in app.py

| Field | Value |
|-------|-------|
| **Description** | In `api/app.py`:
1. Import and register `workspaces` router.
2. Import and register `workspace_settings` router.
3. Import and register the new workspace-scoped projects router (if separate from old).
4. Register 410 deprecation handler for old routes (optional).
The routes in `api/routes/__init__.py` may need updates to export all new routers.

| **Files to modify** | `src/storico/api/app.py`, `src/storico/api/routes/__init__.py` |
| **Dependencies** | T-014, T-015 |
| **Verification** | `app.include_router()` calls present. Server starts without errors, all new endpoints accessible. |
| **Effort** | Small |

### T-023: Register error handlers in app.py and errors.py

| Field | Value |
|-------|-------|
| **Description** | Add new exception handlers in `api/app.py` (or update the existing catch-all):
1. The existing `RepositoryError` handler covers `EntityNotFound`, `DuplicateEntity`, etc. Workspace-specific exceptions like `InsufficientRole`, `OwnerTransferError`, `LastAdminError`, `CannotRemoveOwnerError` need dedicated handlers in `api/errors.py` returning the correct status codes with the `{"detail": "...", "type": "..."}` format from design section 9 error table.
2. Add handlers: `insufficient_role_handler` → 403, `owner_transfer_error_handler` → 400, `last_admin_handler` → 400, `cannot_remove_owner_handler` → 400.
3. Register each in `app.py` with `app.add_exception_handler()`.

| **Files to modify** | `src/storico/api/errors.py`, `src/storico/api/app.py` |
| **Dependencies** | T-002, T-014 |
| **Verification** | Raise each exception in a test route, verify status code and response body format. |
| **Effort** | Small |

### T-024: Register new models and repos in __init__.py

| Field | Value |
|-------|-------|
| **Description** | Update both `infrastructure/database/models/__init__.py` and `infrastructure/database/repositories/__init__.py` to export the new ORM models and repository implementations. This ensures Alembic can detect them and FastAPI dependency injection can find them. |
| **Files to modify** | `src/storico/infrastructure/database/models/__init__.py`, `src/storico/infrastructure/database/repositories/__init__.py` |
| **Dependencies** | T-005, T-007 |
| **Verification** | `from storico.infrastructure.database.models import WorkspaceModel` works. `from storico.infrastructure.database.repositories import SQLAlchemyWorkspaceRepository` works. |
| **Effort** | Small |

---

## Phase 6 — Frontend Core

*Frontend data layer: types, schemas, API clients, Zustand stores.*

### T-025: ✅ Create workspace types

| Field | Value |
|-------|-------|
| **Description** | Create `types/workspace.ts` with TypeScript interfaces following the camelCase convention: `Workspace` (id, name, slug, ownerId, role, memberCount, createdAt, updatedAt), `WorkspaceMember` (userId, name, email, avatarUrl, role, createdAt), `WorkspaceLLMConfig` (provider, model?, temperature?, maxTokens?, baseUrl?), `WorkspacePrompt` (systemPrompt?, instructionTemplate?, fewShotExamples?). The `role` field is `'admin' \| 'member'`. |
| **Pattern** | Follow `types/project.ts` pattern — export interfaces only, no classes. |
| **Files to create** | `frontend/src/types/workspace.ts` |
| **Dependencies** | None |
| **Verification** | `tsc --noEmit` passes for the file. |
| **Effort** | Small |

### T-026: ✅ Create workspace Zod schemas

| Field | Value |
|-------|-------|
| **Description** | Create `schemas/workspace.ts` with Zod schemas following the `schemas/project.ts` pattern: `createWorkspaceSchema` (name: min 1, slug: optional string), `updateWorkspaceSchema` (name: optional, slug: optional), `addMemberSchema` (userId: uuid string), `transferOwnershipSchema` (newOwnerId: uuid string), `llmConfigSchema`, `promptConfigSchema`. Export TS types via `z.infer`. |
| **Pattern** | Follow `schemas/project.ts` pattern exactly. |
| **Files to create** | `frontend/src/schemas/workspace.ts` |
| **Dependencies** | T-025 |
| **Verification** | Import schemas, validate sample objects. |
| **Effort** | Small |

### T-027: ✅ Create workspace API clients (3 files)

| Field | Value |
|-------|-------|
| **Description** | Create three API client modules:
1. **`lib/workspace-api.ts`**: CRUD operations: `createWorkspace(params)`, `listWorkspaces()`, `getWorkspace(id)`, `updateWorkspace(id, params)`, `deleteWorkspace(id)`. Also member management: `listMembers(wsId)`, `addMember(wsId, userId)`, `updateMemberRole(wsId, userId, role)`, `removeMember(wsId, userId)`, `transferOwnership(wsId, newOwnerId)`.
2. **`lib/llm-config-api.ts`**: `getLLMConfig(wsId)`, `upsertLLMConfig(wsId, config)`.
3. **`lib/prompts-api.ts`**: `getPrompts(wsId)`, `upsertPrompts(wsId, prompts)`.

All follow the `toSnakeCase`/`toCamelCase` pattern from `projects-api.ts`. API base path is `/api/v1/workspaces/{wsId}`.

| **Pattern** | Follow `projects-api.ts` pattern: `import { api } from './api'`, `import { toCamelCase, toSnakeCase } from './utils'`, async functions returning typed promises. |
| **Files to create** | `frontend/src/lib/workspace-api.ts`, `frontend/src/lib/llm-config-api.ts`, `frontend/src/lib/prompts-api.ts` |
| **Dependencies** | T-010, T-025 |
| **Verification** | Import in a page, verify functions are typed correctly. |
| **Effort** | Medium |

### T-028: ✅ Create workspace Zustand store

| Field | Value |
|-------|-------|
| **Description** | Create `stores/workspaceStore.ts` with a Zustand store following the `projectStore.ts` pattern: state has `workspaces: Workspace[]`, `currentWorkspace: Workspace | null`, `loading`, `error`. Actions: `fetchWorkspaces()` (calls workspace-api.listWorkspaces, sets state), `setCurrentWorkspace(w: Workspace)` (updates `currentWorkspace` and triggers `projectStore.fetchProjects()`), `createWorkspace(params)` (calls API, adds to list, sets as current), `switchWorkspace(id)` (find by ID, set as current). `getById(id)`. On first mount (if `currentWorkspace` is null), fetch workspaces and auto-select the first one. |

**Workspace context flow** (from design section 6):
1. `WorkspaceSwitcher` selects workspace → calls `workspaceStore.setCurrentWorkspace(w)`
2. `workspaceStore` stores `currentWorkspace` and its `id`
3. `projectStore.fetchProjects()` reads `currentWorkspace.id`, calls API with workspace scope
4. Astro View Transitions preserve the Zustand state across page navigations
5. On page mount, if `currentWorkspace` is null (first load), `workspaceStore` fetches the list and selects the first one

| **Pattern** | Follow `projectStore.ts` pattern: `import { create } from 'zustand'`, store interface + implementation. No `persist` middleware needed (View Transitions keep state in memory). |
| **Files to create** | `frontend/src/stores/workspaceStore.ts` |
| **Dependencies** | T-025, T-027 |
| **Verification** | Import store, call actions, verify state updates. |
| **Effort** | Medium |

### T-029: ✅ Modify existing frontend types and stores

| Field | Value |
|-------|-------|
| **Description** | Three modifications:
1. **`types/project.ts`**: Replace `ownerId: string` with `workspaceId: string`, add `createdBy: string | null`.
2. **`stores/projectStore.ts`**: `createProject` signature changes from accepting `ownerId` to reading `workspaceId` from `workspaceStore.currentWorkspace.id`. `fetchProjects()` scopes to `currentWorkspace.id`. Add workspace ID to API call URL: `api/workspaces/{wsId}/projects` instead of `api/projects/`.
3. **`stores/storyStore.ts`**: Add workspace-scoped fetching awareness — `fetchStories(projectId)` resolves workspace context from `projectStore`.

| **Files to modify** | `frontend/src/types/project.ts`, `frontend/src/stores/projectStore.ts`, `frontend/src/stores/storyStore.ts` |
| **Dependencies** | T-025, T-028 |
| **Verification** | `tsc --noEmit` passes. Verify store actions use correct workspace-scoped URLs. |
| **Effort** | Small |

---

## Phase 7 — Frontend UI

*Migrates the sidebar from Astro to a React island with workspace switching.*

### T-030: Create React sidebar with WorkspaceSwitcher

| Field | Value |
|-------|-------|
| **Description** | Create `components/react/Sidebar.tsx` — a React island that replaces `components/astro/Sidebar.astro`. This is the biggest frontend change.

**Structure** (from design section 6):
```
Sidebar.tsx
├── WorkspaceSwitcher (shadcn sidebar-07 TeamSwitcher adaptation)
│   ├── Current workspace badge [icon + name + chevron]
│   ├── Dropdown:
│   │   ├── Workspace list (searchable)
│   │   │   └── Each item: icon + name + slug
│   │   ├── Separator
│   │   └── "+ Add workspace" action → dialog
├── Nav links (shadcn sidebar-menu)
│   ├── Dashboard (LayoutDashboard)
│   ├── Projects (FolderKanban)
│   ├── Stories (FileText)
│   ├── Kanban (KanbanSquare)
│   ├── Export (Upload)
│   └── Settings (Settings) — only shown if role === 'admin'
├── Sidebar footer: collapse toggle, version
```

**Props**: `locale: string`, `currentPath: string`, `userJson: string` (serialized user object).

**Behavior**:
- On mount, if `workspaceStore.workspaces` is empty, call `fetchWorkspaces()`.
- If `currentWorkspace` is null, auto-select the first workspace.
- WorkspaceSwitcher dropdown: click to switch, "Add workspace" opens a dialog (use shadcn `Dialog` from `components/ui/dialog.tsx`).
- Nav links: highlight active based on `currentPath` (same logic as current Sidebar.astro).
- Settings link hidden if user role is not `'admin'` in the current workspace.
- Collapse toggle: persist state in localStorage (same as current sidebar).
- Use `client:load` in Astro — this island runs on page load.

**shadcn sidebar pattern**: Install the shadcn sidebar-07 command palette component or adapt from the shadcn blocks library. The TeamSwitcher component from shadcn's sidebar-07 block shows exactly the workspace-switching UX needed — a dropdown with workspace list, search, and "Add workspace" action.

| **Files to create** | `frontend/src/components/react/Sidebar.tsx` |
| **Dependencies** | T-025, T-028 |
| **Verification** | Sidebar renders with workspace switcher. Switching workspace updates the store. Nav links highlight correctly. Collapse works and persists. |
| **Effort** | **Large** (~200 lines + dialog component) |

### T-031: Modify MainLayout and delete old Sidebar

| Field | Value |
|-------|-------|
| **Description** | Three changes:
1. **`layouts/MainLayout.astro`**: Replace `<Sidebar locale={locale} currentPath={currentPath} />` (Astro component) with `<Sidebar client:load locale={locale} currentPath={currentPath} userJson={userJson} />` (React island). Remove the import of `Sidebar` from `@/components/astro/Sidebar.astro`. Add import from `@/components/react/Sidebar`.
2. **Delete** `components/astro/Sidebar.astro`.
3. **Remove unused imports**: The `PanelLeftClose`, `PanelLeftOpen`, and lucide imports in the old sidebar are no longer needed.

| **Files to modify** | `frontend/src/layouts/MainLayout.astro` |
| **Files to delete** | `frontend/src/components/astro/Sidebar.astro` |
| **Dependencies** | T-030 |
| **Verification** | Page loads without errors. Sidebar renders as React island. WorkspaceSwitcher is interactive. |
| **Effort** | Small |

### T-032: Modify page .astro files for workspace context

| Field | Value |
|-------|-------|
| **Description** | Update all page `.astro` files under `pages/[locale]/` to pass workspace context where needed. Pages that need workspace-scoped data:
- `dashboard.astro` — no changes needed if Dashboard component reads from workspaceStore.
- `stories.astro` — no changes needed if StoriesList reads from stores.
- `stories/[id].astro` — same.
- `projects/index.astro` — same.
- `projects/[id].astro` — same.
- `kanban.astro` — same.
- `export.astro` — same.
- `settings.astro` — **needs update**: When at `/settings`, the sidebar should NOT show Settings as admin-only (because global user settings are at `/settings`, not workspace settings). Workspace settings will be at `/workspaces/{id}/settings` — a new page (Phase 8). Keep `/settings` for user-level settings (theme, language, LLM API keys).

Most pages need **no changes** if components use the Zustand stores directly. The key change is that `projectStore.fetchProjects()` now auto-scopes to `currentWorkspace.id`.

Add a check in `MainLayout.astro` or in each page: if `workspaceStore.currentWorkspace` is null (e.g., during SSR or first load), the layout should suppress data-fetching components or show a loading state.

**Critical**: The Astro pages still work because they delegate data fetching to client-side React islands that read from Zustand stores. No server-side data fetching changes needed.

| **Files to modify** | Potentially: `frontend/src/layouts/MainLayout.astro` (add workspace initialization script) |
| **Dependencies** | T-028, T-031 |
| **Verification** | All pages load without errors. Navigate between pages — Zustand stores persist state (View Transitions). |
| **Effort** | Small |

---

## Phase 8 — Frontend Settings

*Workspace-level settings pages for LLM config, prompts, and member management.*

### T-033: Create workspace settings page (LLM config + prompt editors)

| Field | Value |
|-------|-------|
| **Description** | Create `pages/[locale]/workspaces/[id]/settings.astro` (or a new route pattern) with two sections:

1. **LLM configuration editor**: Form fields for provider (select: ollama, openai), model (text input), temperature (range/number), max tokens (number), base URL (text). On load, fetch current config from `llm-config-api.getLLMConfig(wsId)`. On save, call `upsertLLMConfig(wsId, config)`. Show toast on success/error. Use shadcn `Form`, `Input`, `Select`, `Button`.

2. **Prompt editor**: Textarea editors for system_prompt, instruction_template, and a JSON editor for few_shot_examples (or structured form). Same load/save pattern via `prompts-api`.

Both sections use `require_admin` on the backend, so if the user is not an admin, the API returns 403. The sidebar already hides the Settings link for non-admins.

**Route**: `/workspaces/{id}/settings` — Astro dynamic route. The `id` parameter is the workspace UUID. The page needs to read `workspaceStore.currentWorkspace` to verify the user is viewing the correct workspace's settings.

**Note**: The frontend doesn't have a dedicated settings page route yet. You may need to create:
- `pages/[locale]/workspaces/[id]/settings.astro` (page shell)
- `components/react/WorkspaceSettings.tsx` (React island with LLM + prompt editors)
- `components/react/MemberManagement.tsx` (React island for member list/add/remove)

| **Files to create** | `frontend/src/pages/[locale]/workspaces/[id]/settings.astro`, `frontend/src/components/react/WorkspaceSettings.tsx` |
| **Dependencies** | T-027, T-028, T-030 |
| **Verification** | Navigate to `/workspaces/{id}/settings`. LLM config loads and saves. Prompt config loads and saves. Non-admin gets 403 (UI shows error). |
| **Effort** | Medium |

### T-034: Create member management UI

| Field | Value |
|-------|-------|
| **Description** | Create `components/react/MemberManagement.tsx` as a React island for the workspace settings page:

1. **Member list**: Table showing all members (avatar, name, email, role, joined date). Admin sees action buttons.
2. **Add member**: Form with user ID input (since MVP has no user search — direct add by ID). Validates UUID format.
3. **Change role**: Dropdown per member row (only for non-owner members). Cannot demote owner.
4. **Remove member**: Confirmation dialog (shadcn `AlertDialog`). Cannot remove owner. Check for last admin.
5. **Transfer ownership**: Section at bottom showing current owner, with a "Transfer" button that opens a dialog to select a new owner from admin members list.

All operations use the workspace-api functions from T-027.

| **Files to create** | `frontend/src/components/react/MemberManagement.tsx` |
| **Dependencies** | T-027, T-028, T-033 |
| **Verification** | Load member list. Add a member. Change role. Remove member (non-owner). Verify owner cannot be removed. Transfer ownership works. |
| **Effort** | Medium |

---

## Summary

| Phase | Tasks | Files (create/modify/delete) | Estimated lines |
|-------|-------|------------------------------|-----------------|
| 1 — Data Model | T-001 to T-006 | 12 create, 5 modify | 500-600 |
| 2 — Infrastructure | T-007 to T-009 | 4 create, 4 modify | 300-350 |
| 3 — API Schemas + Auth | T-010 to T-013 | 4 create, 4 modify | 200-300 |
| 4 — API Routes | T-014 to T-021 | 2 create, 6 modify | 700-900 |
| 5 — App Wiring | T-022 to T-024 | 0 create, 4 modify | 50-80 |
| 6 — Frontend Core | T-025 to T-029 | 5 create, 5 modify | ~230 |
| 7 — Frontend UI | T-030 to T-032 | 1 create, 1 modify, 1 delete | 200-250 |
| 8 — Frontend Settings | T-033 to T-034 | 3 create, 0 modify | 300-400 |
| **Total** | **34 tasks** | **31 create, 27 modify, 1 delete** | **~2,800-3,200** |

### Execution Order (dependency-safe batches)

1. **T-001 → T-002** (entities + exceptions — parallel)
2. **T-003 → T-004** (ports — parallel with each other, after T-001)
3. **T-005** (ORM models — after T-001)
4. **T-006** (migration — after T-005)
5. **T-007 → T-008 → T-009** (repos — parallel after T-003/T-005)
6. **T-010 → T-011** (schemas — parallel after T-001)
7. **T-012** (JWT auth — after T-004, can run parallel with T-010)
8. **T-013** (deps — after T-007, T-012)
9. **T-016** (use cases — after T-001/T-002/T-003/T-007, parallel with routes)
10. **T-014 → T-015 → T-017 → T-018 → T-019 → T-020 → T-021** (routes — after T-010/T-013, can run in parallel)
11. **T-022 → T-023 → T-024** (wiring — after all routes)
12. **T-025 → T-026 → T-027** (frontend core — ✅ done)
13. **T-028 → T-029** (stores — ✅ done)
14. **T-030 → T-031 → T-032** (sidebar — after T-028)
15. **T-033 → T-034** (settings — after T-027)
