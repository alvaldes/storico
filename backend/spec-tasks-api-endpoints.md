# Tasks: API Endpoints

> **Change**: `api-endpoints` — Wire FastAPI CRUD endpoints for the Storico MVP
> **Date**: 2026-07-06
> **Spec**: `spec-api-endpoints.md` (also in Engram: `sdd/api-endpoints/spec`)
> **Design**: Engram `sdd/api-endpoints/design` (obs #223)

---

## 1. Review Workload Forecast

| Category | New Files | Modified Files | Est. Lines | Notes |
|----------|-----------|----------------|------------|-------|
| Schemas | 7 | 0 | ~170 | `common.py`, `project.py`, `story.py`, `task.py`, `extraction.py`, `user.py`, `__init__.py` |
| Dependencies | 1 | 0 | ~15 | `dependencies.py` — `get_repository()` factory |
| Error handling | 1 | 0 | ~40 | `errors.py` — 3 exception handlers + generic catch |
| Routes | 6 | 0 | ~340 | projects(~65), stories(~80), tasks(~80), extractions(~45), users(~25), extraction(~45) |
| App wiring | 0 | 1 | ~20 | `app.py` — CORS, error handlers, router registrations |
| Settings | 0 | 1 | +1 | `settings.py` — one line: `cors_origins` |
| Test conftest | 0 | 1 | ~30 | Additional fixtures for API tests |
| Test files | 6 | 0 | ~550 | ~90 lines each × 6 files |
| **Total** | **21** | **3** | **~1,170** | |

**Line budget risk**: **CRITICAL**. Estimated ~1,170 new lines across 24 files. This clearly exceeds the 400-line review budget. **Must be delivered as chained PRs.**

---

## 2. Delivery Strategy

**Recommendation: 3 chained PRs** (sequential, each building on the previous):

| PR | Phases | Est. Lines | Review Scope |
|----|--------|------------|--------------|
| **PR 1** | Phase 1 (Schemas + deps + errors) + Phase 3 (settings + app wiring stubs) | ~250 | Foundation: no routes yet, but API layer exists. Can be reviewed in isolation. |
| **PR 2** | Phase 2 (All 6 route files) | ~340 | Routes layer; depends on PR 1 schemas/deps/errors. |
| **PR 3** | Phase 4 (Test conftest additions + 6 test files) | ~580 | Could optionally split into 2 PRs if needed (3 test files each). |

**Alternative**: Merge PR 3 test files into PR 1 and PR 2 (tests alongside code), which shrinks overall PRs but adds scope to each review. The chained approach keeps each PR focused.

---

## 3. Tasks

### Phase 1: Schemas + Dependencies + Error Handling

---

#### API-T1: Settings — Add `cors_origins`

- **Files**: `backend/src/storico/config/settings.py` (modified)
- **What**: Add `cors_origins: str = "*"` to the `Settings` class. This controls the CORS allow-origins header for the API. Default `"*"` for development; restrict before production.
- **Dependencies**: None
- **Acceptance criteria**:
  - `Settings().cors_origins` returns `"*"` by default
  - Can override via `STORICO_CORS_ORIGINS` env var

---

#### API-T2: Common schemas

- **Files**:
  - `backend/src/storico/api/schemas/__init__.py` (new)
  - `backend/src/storico/api/schemas/common.py` (new)
- **What**: Create the `api/schemas/` directory and two files:

  **`common.py`** — three shared Pydantic models:
  - `PaginationParams` — `page: int = Field(default=1, ge=1)`, `size: int = Field(default=20, ge=1, le=100)`. Used as query params via `Depends()`.
  - `PaginatedResponse[T]` — generic model: `items: list[T]`, `total: int`, `page: int`. Use `model_config = {"generic_types": True}` for Python 3.12 forward refs.
  - `ErrorResponse` — `detail: str`, `type: str`. Returned as JSON body for 4xx/5xx.

  **`__init__.py`** — re-export all schema classes from submodules:
  ```python
  from storico.api.schemas.common import ErrorResponse, PaginatedResponse, PaginationParams
  from storico.api.schemas.project import CreateProjectRequest, ProjectResponse, UpdateProjectRequest
  # ... etc for all schema classes
  ```
- **Dependencies**: None (self-contained)
- **Acceptance criteria**:
  - `PaginationParams` rejects `page=0` or `size=101` with 422
  - `PaginatedResponse[int](items=[1,2], total=2, page=1)` instantiates correctly
  - `ErrorResponse(detail="x", type="y")` renders as `{"detail": "x", "type": "y"}`
  - All schema classes importable from `storico.api.schemas`

---

#### API-T3: Project schemas

- **Files**: `backend/src/storico/api/schemas/project.py` (new)
- **What**: Three Pydantic models matching the `Project` frozen dataclass:
  - `CreateProjectRequest` — `name: str`, `owner_id: UUID`, `description: str = ""`. `model_config = {"extra": "forbid"}`.
  - `UpdateProjectRequest` — `name: str | None = None`, `description: str | None = None`. Optional fields (partial update via PUT). `extra = "forbid"`.
  - `ProjectResponse` — `id: UUID`, `name: str`, `owner_id: UUID`, `description: str`, `created_at: datetime`, `updated_at: datetime`. `model_config = {"from_attributes": True}` for ORM compatibility.
- **Dependencies**: API-T2 (common schemas for the `__init__` re-export pattern)
- **Acceptance criteria**:
  - `CreateProjectRequest(extra_field="x")` raises 422 validation error
  - `ProjectResponse.model_validate(project_entity)` works (from_attributes)
  - All fields match `Project` domain entity types exactly

---

#### API-T4: UserStory schemas

- **Files**: `backend/src/storico/api/schemas/story.py` (new)
- **What**: Three Pydantic models matching `UserStory`:
  - `CreateUserStoryRequest` — `project_id: UUID`, `actor: str`, `feature: str`, `benefit: str`, `raw_text: str`. `extra="forbid"`.
  - `UpdateUserStoryRequest` — all fields optional except no project_id update for MVP. `actor: str | None = None`, `feature: str | None = None`, `benefit: str | None = None`, `raw_text: str | None = None`. `extra="forbid"`.
  - `UserStoryResponse` — `id: UUID`, `project_id: UUID`, `actor`, `feature`, `benefit`, `raw_text`, `created_at: datetime`. `from_attributes=True`.
- **Dependencies**: API-T2
- **Acceptance criteria**:
  - Missing `project_id` in CreateRequest → 422
  - Extra field in CreateRequest → 422
  - Response can be constructed from ORM model

---

#### API-T5: Task schemas

- **Files**: `backend/src/storico/api/schemas/task.py` (new)
- **What**: Three Pydantic models matching `Task`:
  - `CreateTaskRequest` — `user_story_id: UUID`, `title: str`, `description: str = ""`, `status: str = "backlog"`, `priority: str = "medium"`, `labels: list[str] = []`, `dependencies: list[str] = []`. `extra="forbid"`.
  - `UpdateTaskRequest` — all fields optional: `title: str | None = None`, `description: str | None = None`, `status: str | None = None`, `priority: str | None = None`, `labels: list[str] | None = None`, `dependencies: list[str] | None = None`. `extra="forbid"`.
  - `TaskResponse` — all fields from entity + `id: UUID`, `created_at: datetime`, `updated_at: datetime`. `from_attributes=True`.
- **Dependencies**: API-T2
- **Acceptance criteria**:
  - `labels` and `dependencies` accept `["frontend", "auth"]` as JSON array
  - Empty lists are valid (not the same as missing)
  - Extra fields rejected

---

#### API-T6: Extraction and User schemas

- **Files**:
  - `backend/src/storico/api/schemas/extraction.py` (new)
  - `backend/src/storico/api/schemas/user.py` (new)
- **What**:

  **`extraction.py`** — `ExtractionResponse`:
  - `id: UUID`, `user_story_id: UUID`, `model_used: str`, `raw_response: str`, `confidence_score: float | None = None`, `created_at: datetime`. `from_attributes=True`.

  **`user.py`** — `UserResponse`:
  - `id: UUID`, `email: str`, `name: str`, `auth_provider: str`, `created_at: datetime`. `from_attributes=True`.
- **Dependencies**: API-T2
- **Acceptance criteria**:
  - Both schemas can be constructed from ORM model
  - `confidence_score` is nullable

---

#### API-T7: Repository injection factory

- **Files**: `backend/src/storico/api/dependencies.py` (new)
- **What**: Implement `get_repository()` factory dependency:
  ```python
  from collections.abc import Callable
  from typing import Annotated, TypeVar

  from fastapi import Depends
  from sqlalchemy.ext.asyncio import AsyncSession

  from storico.infrastructure.database.session import get_session

  RepoType = TypeVar("RepoType")

  def get_repository(repo_class: type[RepoType]) -> Callable[..., RepoType]:
      def _get_repo(session: Annotated[AsyncSession, Depends(get_session)]) -> RepoType:
          return repo_class(session)
      return _get_repo
  ```
- **Dependencies**: None (imports from existing infrastructure only)
- **Acceptance criteria**:
  - `get_repository(SQLAlchemyProjectRepository)` returns a callable
  - The returned callable, when used as `Depends()`, creates the repo with the current session
  - Type hints resolve correctly (mypy/pyright clean)

---

#### API-T8: Error handlers

- **Files**: `backend/src/storico/api/errors.py` (new)
- **What**: Three exception handler functions + one generic catch-all:
  - `entity_not_found_handler(request, exc: EntityNotFound)` → 404 JSON: `{"detail": str(exc), "type": "entity_not_found"}`
  - `duplicate_entity_handler(request, exc: DuplicateEntity)` → 409 JSON: `{"detail": str(exc), "type": "duplicate_entity"}`
  - `repository_error_handler(request, exc: RepositoryError)` → 500 JSON: `{"detail": str(exc), "type": "repository_error"}`
  - `generic_error_handler(request, exc: Exception)` → 500 JSON: `{"detail": "Internal server error", "type": "internal_error"}`
  - Imports `EntityNotFound`, `DuplicateEntity`, `RepositoryError` from `storico.domain.entities.exceptions`
- **Dependencies**: None (domain exceptions already exist)
- **Acceptance criteria**:
  - `EntityNotFound("Project", "abc")` returns 404 with correct message format
  - `DuplicateEntity("User", "email", "x@y.com")` returns 409 with correct message
  - Generic `Exception` returns 500 (not exposed detail)
  - Handlers are functions (not methods) — compatible with `app.add_exception_handler`

---

### Phase 2: Routes

---

#### API-T9: Project CRUD routes

- **Files**: `backend/src/storico/api/routes/projects.py` (new)
- **What**: Router at prefix `/api/v1/projects` with 5 endpoints:
  - `GET /` — list projects with pagination. Inject `PaginationParams` via `Depends()`. Call `repo.list()`, slice with `[(page-1)*size : page*size]`, return `PaginatedResponse[ProjectResponse]`.
  - `GET /{id}` — `repo.find_by_id(id)`, raise `EntityNotFound` if None, return `ProjectResponse`.
  - `POST /` — accept `CreateProjectRequest`, construct `Project` entity (let UUID/created_at/updated_at auto-generate), `repo.save(project)`, return `ProjectResponse` with status 201.
  - `PUT /{id}` — accept `UpdateProjectRequest`, `repo.find_by_id(id)` → 404 if None, `dataclasses.replace()` with non-None fields + `updated_at=datetime.now(UTC)`, `repo.save(updated)`, return `ProjectResponse`.
  - `DELETE /{id}` — `repo.find_by_id(id)` → 404 if None, `repo.delete(id)`, return 204.
  - Use `Depends(get_repository(SQLAlchemyProjectRepository))` for repo injection.
  - Import `Project` from domain entities, `EntityNotFound` from exceptions.
- **Dependencies**: API-T7 (dependencies.py), API-T3 (project schemas), API-T8 (error handlers — exceptions exist but handlers are registered in app.py)
- **Acceptance criteria**:
  - Full CRUD cycle works: POST → GET list → GET by id → PUT → DELETE
  - DELETE returns 204 (not 200 with null body)
  - GET non-existent ID returns 404 with correct error shape
  - PUT updates only provided fields (partial update), sets `updated_at` server-side
  - Pagination params apply correctly

---

#### API-T10: UserStory CRUD routes

- **Files**: `backend/src/storico/api/routes/stories.py` (new)
- **What**: Router at prefix `/api/v1/stories` with 5 endpoints + project_id filter:
  - `GET /` — list with pagination. Accept optional `project_id: UUID | None = None` query param. If provided, call `repo.list_by_project(project_id)`. Otherwise `repo.list()`. Slice and return `PaginatedResponse[UserStoryResponse]`.
  - `GET /{id}` — standard get-by-id pattern.
  - `POST /` — construct `UserStory` from `CreateUserStoryRequest`, save, return 201.
  - `PUT /{id}` — find → `replace()` with non-None fields → save → return 200.
  - `DELETE /{id}` — find → delete → 204.
  - Repo: `SQLAlchemyUserStoryRepository`.
- **Dependencies**: API-T7, API-T4, API-T8
- **Acceptance criteria**:
  - `?project_id=<uuid>` filters stories correctly
  - Without `project_id`, returns all stories
  - Same CRUD patterns as API-T9

---

#### API-T11: Task CRUD routes

- **Files**: `backend/src/storico/api/routes/tasks.py` (new)
- **What**: Router at prefix `/api/v1/tasks` with 5 endpoints + user_story_id filter:
  - `GET /` — list with pagination. Accept optional `user_story_id: UUID | None = None` query param. If provided, call `repo.list_by_story(user_story_id)`. Otherwise `repo.list()`.
  - `GET /{id}` — standard.
  - `POST /` — construct `Task` from `CreateTaskRequest` (labels/deps as `list[str]`), save, return 201.
  - `PUT /{id}` — find → `replace()` with non-None fields → `updated_at=now` → save → return 200.
    - `labels` and `dependencies` are `list[str]` — handle `None` vs empty list correctly in replace logic. If the field is `None` in UpdateTaskRequest, keep existing value. If it's `[]`, set to empty list.
  - `DELETE /{id}` — find → delete → 204.
  - Repo: `SQLAlchemyTaskRepository`.
- **Dependencies**: API-T7, API-T5, API-T8
- **Acceptance criteria**:
  - `?user_story_id=<uuid>` filters tasks correctly
  - `labels` and `dependencies` round-trip correctly as JSON arrays
  - PUT with `{"status": "in_progress"}` preserves existing labels/dependencies
  - PUT with `{"labels": []}` clears labels

---

#### API-T12: Extraction listing routes

- **Files**: `backend/src/storico/api/routes/extractions.py` (new)
- **What**: Router at prefix `/api/v1/extractions` with 2 read-only endpoints:
  - `GET /` — list with pagination. Accept optional `user_story_id: UUID | None = None`. Filter via `repo.list_by_story()` or `repo.list()`.
  - `GET /{id}` — standard get-by-id → 404.
  - Repo: `SQLAlchemyExtractionRepository`.
- **Dependencies**: API-T7, API-T6, API-T8
- **Acceptance criteria**:
  - GET list returns extractions with correct pagination
  - GET by id returns extraction or 404
  - No POST/PUT/DELETE (read-only)

---

#### API-T13: User profile stub

- **Files**: `backend/src/storico/api/routes/users.py` (new)
- **What**: Router at prefix `/api/v1/users` with 1 endpoint:
  - `GET /me` — calls `repo.list()`, returns the first user as `UserResponse`. If no users exist, returns `None` (or empty response — simplest: return `{"user": null}`, no 404 since there's no auth to identify "me").
  - Repo: `SQLAlchemyUserRepository`.
  - This is a stub for MVP — no auth, no user identification.
- **Dependencies**: API-T7, API-T6, API-T8
- **Acceptance criteria**:
  - Returns first user from DB as `UserResponse`
  - Returns `null` or empty response when DB has no users (no crash)
  - Does not create users as a side effect

---

#### API-T14: Extraction stub routes

- **Files**: `backend/src/storico/api/routes/extraction.py` (new)
- **What**: Router at prefix `/api/v1/extract` with 2 endpoints:
  - `POST /` — accepts `{"user_story_id": str, "raw_text": str}` (use a simple Pydantic model `ExtractRequest` defined inline or in `schemas/extraction.py`). Returns 201 with 2-3 mock tasks matching Task structure:
    ```python
    {
        "tasks": [
            {"title": "...", "description": "...", "labels": ["stub"], "status": "backlog", "priority": "high"},
            {"title": "...", "description": "...", "labels": ["stub"], "status": "backlog", "priority": "medium"},
        ]
    }
    ```
    No LLM call. No persistence.
  - `GET /status/{id}` — returns 200 with `{"status": "completed", "id": "<path_id>"}`. Placeholder.
- **Dependencies**: API-T6 (partial — could define ExtractRequest inline to avoid dependency)
- **Acceptance criteria**:
  - POST returns 201 with `tasks` array of 2-3 items
  - Each task has `title`, `description`, `labels: ["stub"]`, `status: "backlog"`, `priority`
  - GET /status/{id} returns `{"status": "completed", "id": "..."}`
  - No DB writes occur

---

### Phase 3: App Wiring

---

#### API-T15: App wiring — CORS, error handlers, router registration

- **Files**: `backend/src/storico/api/app.py` (modified)
- **What**: Add to `create_app()`:
  1. **CORS middleware**: `app.add_middleware(CORSMiddleware, allow_origins=allowed_origins, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])`. Read `allowed_origins` from `Settings().cors_origins` (parse as comma-separated or `["*"]`).
  2. **Error handler registration**: Call `app.add_exception_handler(...)` for all 3 exceptions from `api/errors.py`, plus the generic handler.
  3. **Router registration**: `app.include_router(...)` for all 6 new route files + the existing health router.
     - `projects.router` → prefix `/api/v1/projects`, tags `["projects"]`
     - `stories.router` → prefix `/api/v1/stories`, tags `["stories"]`
     - `tasks.router` → prefix `/api/v1/tasks`, tags `["tasks"]`
     - `extractions.router` → prefix `/api/v1/extractions`, tags `["extractions"]`
     - `users.router` → prefix `/api/v1/users`, tags `["users"]`
     - `extraction.router` → prefix `/api/v1/extract`, tags `["extraction"]`

  Import structure:
  ```python
  from fastapi.middleware.cors import CORSMiddleware
  from storico.api.errors import entity_not_found_handler, duplicate_entity_handler, repository_error_handler, generic_error_handler
  from storico.api.routes import projects, stories, tasks, extractions, users, extraction
  from storico.domain.entities.exceptions import EntityNotFound, DuplicateEntity, RepositoryError
  from storico.config.settings import Settings
  ```
- **Dependencies**: API-T1 (cors_origins), API-T8 (error handlers), API-T9 through API-T14 (all routes)
- **Acceptance criteria**:
  - App starts without import errors
  - `GET /docs` renders OpenAPI/Swagger UI with all endpoints listed
  - CORS headers (`Access-Control-Allow-Origin: *`) present on all responses
  - OPTIONS preflight requests succeed
  - `EntityNotFound` raised in any route returns 404 JSON
  - `DuplicateEntity` raised in any route returns 409 JSON

---

### Phase 4: Tests

---

#### API-T16: Test fixtures for API tests

- **Files**: `backend/tests/conftest.py` (modified)
- **What**: Add fixtures for API integration tests:
  - `override_get_session` — fixture that maps `app.dependency_overrides[get_session]` → `db_session` fixture, clears on teardown:
    ```python
    @pytest_asyncio.fixture
    async def override_get_session(db_session):
        from storico.infrastructure.database.session import get_session
        app.dependency_overrides[get_session] = lambda: db_session
        yield
        app.dependency_overrides.clear()
    ```
  - Modify or add `api_client` fixture that uses `app` + `override_get_session` + `db_session` to provide a fully wired test client.
  
  **Important**: The `client` fixture already exists in conftest.py but uses the real `get_session` (SQLite in-memory engine from lifespan). The new `override_get_session` fixture re-wires dependency injection so that the test `db_session` (with its own engine + create_all) is used instead. Tests will need both `db_session` (for data setup) and `client` with overrides.
  
  Since `client` already exists, the cleanest approach: create a new fixture `api_client` that combines `app` + `override_get_session` + the existing `client` transport pattern, OR modify the existing `client` to be parameterizable. Recommend: add a dedicated `api_client` fixture for API tests to avoid breaking existing health endpoint tests.
- **Dependencies**: API-T15 (app wiring complete — routers registered)
- **Acceptance criteria**:
  - `api_client` fixture yields an `AsyncClient` wired to test DB
  - Data created via `db_session` is visible through `api_client` requests (and vice versa)
  - `dependency_overrides` are cleaned up after each test
  - Existing health tests still pass unchanged

---

#### API-T17: Test project CRUD endpoints

- **Files**: `backend/tests/test_api/test_projects.py` (new)
- **What**: Integration tests for project routes:
  - `test_create_project` — POST with valid body → 201, response has `id`, `name`, `created_at`
  - `test_create_project_extra_fields` — POST with extra field → 422
  - `test_create_project_missing_required` — POST missing `name` → 422
  - `test_list_projects_empty` — GET → 200, `items=[]`, `total=0`
  - `test_list_projects_pagination` — create 3 projects, GET with `page=1&size=2` → 2 items, `total=3`
  - `test_get_project_by_id` — POST then GET by id → 200, matches created
  - `test_get_project_not_found` — GET random UUID → 404
  - `test_update_project` — POST then PUT → 200, fields changed, `updated_at > created_at`
  - `test_update_project_partial` — PUT with single field → 200, other fields unchanged
  - `test_delete_project` — POST then DELETE → 204, subsequent GET → 404
  - `test_delete_project_not_found` — DELETE random UUID → 404
  - Use `pytest.mark.asyncio` on all async test functions
  - Use `parametrize` where appropriate for similar error cases
- **Dependencies**: API-T16 (test fixtures)
- **Acceptance criteria**:
  - All tests pass with `conda run -n storico pytest tests/test_api/test_projects.py -v`
  - Full CRUD cycle covered end-to-end
  - 404 and 422 error paths tested

---

#### API-T18: Test user story CRUD endpoints

- **Files**: `backend/tests/test_api/test_stories.py` (new)
- **What**: Integration tests for story routes (same pattern as API-T17 but with project_id filter):
  - All CRUD happy-path and error-path tests
  - `test_list_stories_filter_by_project` — create stories in 2 projects, GET with `?project_id=X` → only stories from project X
  - `test_list_stories_no_filter` — returns all stories across projects
  - `test_create_story_invalid_project_id` — non-existent UUID → succeeds at API level (no FK constraint in domain)
- **Dependencies**: API-T16
- **Acceptance criteria**:
  - All tests pass
  - project_id filter works correctly

---

#### API-T19: Test task CRUD endpoints

- **Files**: `backend/tests/test_api/test_tasks.py` (new)
- **What**: Integration tests for task routes (same pattern + labels/deps):
  - All CRUD happy-path and error-path tests
  - `test_create_task_with_labels` — POST with `labels: ["frontend", "auth"]` → 201, response has labels
  - `test_create_task_with_dependencies` — POST with `dependencies: ["task-1"]` → 201
  - `test_update_task_preserves_labels` — PUT with `status` only → labels unchanged
  - `test_update_task_clears_labels` — PUT with `labels: []` → labels is empty list
  - `test_list_tasks_filter_by_story` — GET with `?user_story_id=X` filter
- **Dependencies**: API-T16
- **Acceptance criteria**:
  - All tests pass
  - labels/dependencies round-trip correctly through JSON
  - Partial update preserves unset fields

---

#### API-T20: Test extraction listing and user profile

- **Files**: `backend/tests/test_api/test_extractions.py` (new)
  `backend/tests/test_api/test_users.py` (new)
- **What**: Two smaller test files:

  **`test_extractions.py`**:
  - `test_list_extractions_empty` — GET → 200, empty list
  - `test_list_extractions_filter` — create extraction, GET with `?user_story_id=X` → matching item
  - `test_get_extraction_by_id` — create then GET by id → 200
  - `test_get_extraction_not_found` — random UUID → 404

  **`test_users.py`**:
  - `test_get_me_no_users` — GET /me → 200, `user` is null
  - `test_get_me_with_user` — create user via db_session, GET /me → 200, returns user data
- **Dependencies**: API-T16
- **Acceptance criteria**:
  - All tests pass
  - Extraction read-only endpoints work
  - User profile stub returns correct data or null

---

#### API-T21: Test extraction stub endpoints

- **Files**: `backend/tests/test_api/test_extraction.py` (new)
- **What**: Integration tests for the POST /extract stub:
  - `test_extract_returns_mock_tasks` — POST with body → 201, response has `tasks` list, 2-3 items
  - `test_extract_task_shape` — each task has `title`, `description`, `labels: ["stub"]`, `status: "backlog"`, `priority`
  - `test_extract_status` — GET /status/{id} → 200, `{"status": "completed"}`
  - `test_extract_invalid_body` — POST without required fields → 422
- **Dependencies**: API-T16
- **Acceptance criteria**:
  - All tests pass
  - Mock tasks match expected shape exactly
  - No DB interaction occurs

---

## 4. Dependency Graph

```
API-T1 (settings)
  └── no deps

API-T2 (common schemas)
  └── no deps

API-T3 (project schemas) ──┐
API-T4 (story schemas)   ──┤
API-T5 (task schemas)    ──┤── depend on API-T2
API-T6 (extraction/user) ──┘

API-T7 (dependencies) ── no deps
API-T8 (error handlers) ── no deps

API-T9 (project routes)  ── depends on API-T7, API-T3, API-T8
API-T10 (story routes)   ── depends on API-T7, API-T4, API-T8
API-T11 (task routes)    ── depends on API-T7, API-T5, API-T8
API-T12 (extr. listing)  ── depends on API-T7, API-T6, API-T8
API-T13 (user profile)   ── depends on API-T7, API-T6, API-T8
API-T14 (extract stub)   ── depends on API-T6 (or none if inline model)

API-T15 (app wiring)     ── depends on API-T1, API-T8, API-T9..API-T14

API-T16 (test fixtures)  ── depends on API-T15
API-T17..API-T21 (tests) ── depends on API-T16
```

## 5. Chained PR Breakdown

### PR 1: Foundation (~250 lines)
- API-T1 (settings)
- API-T2 (common schemas)
- API-T3 (project schemas)
- API-T4 (story schemas)
- API-T5 (task schemas)
- API-T6 (extraction/user schemas)
- API-T7 (dependencies)
- API-T8 (error handlers)

Creates: `api/schemas/*` (7 files), `api/dependencies.py`, `api/errors.py`
Modifies: `config/settings.py` (+1 line)

### PR 2: Routes (~340 lines)
- API-T9 (project routes)
- API-T10 (story routes)
- API-T11 (task routes)
- API-T12 (extraction routes)
- API-T13 (user routes)
- API-T14 (extraction stub)
- API-T15 (app wiring)

Creates: `api/routes/projects.py`, `stories.py`, `tasks.py`, `extractions.py`, `users.py`, `extraction.py`
Modifies: `api/app.py`

### PR 3: Tests (~580 lines)
- API-T16 (test fixtures)
- API-T17 (project tests)
- API-T18 (story tests)
- API-T19 (task tests)
- API-T20 (extraction + user tests)
- API-T21 (extract stub tests)

Creates: `tests/test_api/*.py` (6 files)
Modifies: `tests/conftest.py`

**Note**: If PR 3 at ~580 lines is too large, split into:
- PR 3a: conftest + project/story/task tests (~350 lines)
- PR 3b: extraction/user/extract tests (~230 lines)
