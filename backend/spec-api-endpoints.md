# API Endpoints — Full Specification

## Overview

This spec covers the HTTP API layer for Storico MVP. Domain entities, repository ports, SQLAlchemy implementations, and Alembic migration exist — these spec requirements wire them into FastAPI CRUD endpoints with consistent error handling, CORS, and a stub extraction endpoint to unblock frontend development.

---

## 1. Requirements

### RQ-API-01: Pydantic Schemas [MUST]

Each resource has request and response schemas in `api/schemas/`. Request schemas use `model_config = {"extra": "forbid"}`. Response schemas include `id`, `created_at`, `updated_at` where applicable. IDs are UUID strings.

| Schema | File | Request | Response | Fields |
|--------|------|---------|----------|--------|
| Common | `common.py` | PaginationParams, PaginatedResponse, ErrorResponse | — | page, size, items, total, detail, type |
| Project | `project.py` | CreateProjectRequest, UpdateProjectRequest | ProjectResponse | name, owner_id, description, id, created_at, updated_at |
| UserStory | `story.py` | CreateUserStoryRequest, UpdateUserStoryRequest | UserStoryResponse | project_id, actor, feature, benefit, raw_text, id, created_at |
| Task | `task.py` | CreateTaskRequest, UpdateTaskRequest | TaskResponse | user_story_id, title, description, status, priority, labels, dependencies, id, created_at, updated_at |
| Extraction | `extraction.py` | — | ExtractionResponse | user_story_id, model_used, raw_response, confidence_score, id, created_at |
| User | `user.py` | — | UserResponse | email, name, auth_provider, id, created_at |

### RQ-API-02: Project CRUD [MUST]

`api/routes/projects.py` router at prefix `/api/v1/projects`.

| Method | Path | Status | Notes |
|--------|------|--------|-------|
| POST | `/api/v1/projects` | 201 | Creates project from CreateProjectRequest body |
| GET | `/api/v1/projects` | 200 | Paginated list via query params `?page=1&size=20` |
| GET | `/api/v1/projects/{id}` | 200 / 404 | Returns project or EntityNotFound |
| PUT | `/api/v1/projects/{id}` | 200 / 404 | Full update via UpdateProjectRequest; updates `updated_at` server-side |
| DELETE | `/api/v1/projects/{id}` | 204 / 404 | No content on success; EntityNotFound on missing |

### RQ-API-03: User Story CRUD [MUST]

`api/routes/stories.py` router at prefix `/api/v1/stories`.

| Method | Path | Status | Notes |
|--------|------|--------|-------|
| POST | `/api/v1/stories` | 201 | From CreateUserStoryRequest body |
| GET | `/api/v1/stories` | 200 | Paginated; filter by `?project_id=UUID` |
| GET | `/api/v1/stories/{id}` | 200 / 404 | — |
| PUT | `/api/v1/stories/{id}` | 200 / 404 | Full update |
| DELETE | `/api/v1/stories/{id}` | 204 / 404 | — |

### RQ-API-04: Task CRUD [MUST]

`api/routes/tasks.py` router at prefix `/api/v1/tasks`.

| Method | Path | Status | Notes |
|--------|------|--------|-------|
| POST | `/api/v1/tasks` | 201 | From CreateTaskRequest body |
| GET | `/api/v1/tasks` | 200 | Paginated; filter by `?user_story_id=UUID` |
| GET | `/api/v1/tasks/{id}` | 200 / 404 | — |
| PUT | `/api/v1/tasks/{id}` | 200 / 404 | Full update; `updated_at` set server-side |
| DELETE | `/api/v1/tasks/{id}` | 204 / 404 | — |

### RQ-API-05: Extraction Listing [MUST]

`api/routes/extractions.py` router at prefix `/api/v1/extractions`.

| Method | Path | Status | Notes |
|--------|------|--------|-------|
| GET | `/api/v1/extractions` | 200 | Paginated; filter by `?user_story_id=UUID` |
| GET | `/api/v1/extractions/{id}` | 200 / 404 | — |

### RQ-API-06: User Profile [SHOULD]

`api/routes/users.py` router — `GET /api/v1/users/me` returns 200 with the first user in the database (stub for MVP; no auth).

### RQ-API-07: Extraction Stub [MUST]

`api/routes/extraction.py` router — `POST /api/v1/extract` returns 201 with 2-3 mock tasks matching `Task` entity structure (title, description, labels=["stub"], status="backlog"). No LLM call. `GET /api/v1/extract/status/{id}` returns 200 with `{"status": "completed", "id": "..."}`. Extraction is NOT persisted.

### RQ-API-08: Error Handling [MUST]

Global exception handler in `app.py`:

| Exception | HTTP Status | Response Format |
|-----------|-------------|-----------------|
| EntityNotFound | 404 | `{"detail": "...", "type": "entity_not_found"}` |
| DuplicateEntity | 409 | `{"detail": "...", "type": "duplicate_entity"}` |
| RepositoryError | 500 | `{"detail": "...", "type": "repository_error"}` |
| Unhandled | 500 | `{"detail": "Internal server error", "type": "internal_error"}` |

### RQ-API-09: CORS [MUST]

CORS middleware in `create_app()` with `allow_origins` from `Settings.cors_origins`. Default: `["*"]`.

### RQ-API-10: Repository Injection [MUST]

Factory dependency `Depends(get_repository(RepoClass))` that accepts a repository class and instantiates it with the async session from `get_session()`.

---

## 2. Key Scenarios

### S-01: Create and list projects with pagination
- GIVEN no projects exist
- WHEN POST `/api/v1/projects` with `{"name":"Storico","owner_id":"<uuid>","description":"..."}` 
- THEN status 201, response has `id`, `name`, `created_at`
- AND GET `/api/v1/projects?page=1&size=20` returns 200 with `{"items": [project], "total": 1, "page": 1}`

### S-02: Create user story linked to project, retrieve by id
- GIVEN a project exists with id `P1`
- WHEN POST `/api/v1/stories` with `{"project_id":"P1","actor":"user","feature":"log in","benefit":"access account","raw_text":"As a user..."}`
- THEN status 201, response includes `project_id: "P1"` and `id`
- AND GET `/api/v1/stories/{id}` returns the same story

### S-03: Create task with labels, update it, verify updated_at
- GIVEN a user story with id `S1`
- WHEN POST `/api/v1/tasks` with `{"user_story_id":"S1","title":"Build login","labels":["frontend","auth"]}`
- THEN status 201, response has `labels: ["frontend","auth"]`, `created_at == updated_at`
- WHEN PUT `/api/v1/tasks/{id}` with `{"status":"in_progress"}`
- THEN status 200, `updated_at > created_at`

### S-04: Request non-existent resource → 404
- GIVEN a valid UUID `00000000-0000-0000-0000-000000000000`
- WHEN GET `/api/v1/projects/{uuid}`
- THEN status 404, body is `{"detail": "Project with id '...' not found", "type": "entity_not_found"}`

### S-05: Duplicate email → 409
- GIVEN a user with email `test@example.com` exists in DB
- WHEN POST `/api/v1/users` (if implemented) or attempting to create duplicate via repo directly
- THEN status 409, body is `{"detail": "User with email 'test@example.com' already exists", "type": "duplicate_entity"}`

### S-06: POST /extract returns mock tasks
- GIVEN a user story with id `S1`
- WHEN POST `/api/v1/extract` with `{"user_story_id": "S1", "raw_text": "As a user..."}`
- THEN status 201, response has `tasks` array with 2-3 items, each having `title`, `description`, `labels: ["stub"]`, `status: "backlog"`

### S-07: CORS preflight
- WHEN OPTIONS request to any origin
- THEN response includes `Access-Control-Allow-Origin: *` (or configured value)

---

## 3. Edge Cases

| Case | Expected |
|------|----------|
| Invalid UUID in path | 422 from FastAPI validation |
| Missing required field in body | 422 with field-level error details |
| Extra unknown fields in body | 422 (extra="forbid" on request schemas) |
| Empty list result | 200 with `{"items":[], "total":0, "page":1}` |
| DELETE non-existent | 404 EntityNotFound |
| DB connection failure | 500 RepositoryError wrapping SQLAlchemy error |
| Pagination with negative page | 422 from Pydantic validation (ge=1) |
| Pagination size > 100 | 422 (max size capped at 100) |

---

## 4. Test Requirements

| Area | Approach |
|------|----------|
| **Runner** | pytest + pytest-asyncio + httpx AsyncClient |
| **DB** | SQLite in-memory via `aiosqlite`; tables created from Base.metadata, dropped on teardown |
| **Fixtures** | `app` (create_app), `client` (httpx), `db_session` (AsyncSession), `db_engine` (create_all/drop_all) |
| **Test files** | One per resource: `tests/test_api/test_projects.py`, `test_stories.py`, `test_tasks.py`, `test_extractions.py`, `test_users.py`, `test_extraction.py` |
| **Coverage** | Happy path + error path per endpoint (POST create, GET list, GET by id, PUT update, DELETE) |
| **Extraction stub** | Assert mock tasks match Task entity shape exactly; no DB persistence check |

---

## 5. Dependencies

- `db-models` change: Complete (all 5 ORM models, repos, session, migration exist)
- FastAPI already in `pyproject.toml`
- `pydantic` already in `pyproject.toml`
- `httpx` already in dev dependencies
- Settings must add `cors_origins: list[str] = ["*"]`

## 6. Open Questions

| Question | Impact |
|----------|--------|
| Should `GET /api/v1/users/me` create a default user on first call? | Simpler for frontend dev but adds side-effect to a GET |
| Should `/api/v1/extract` persist mock extractions? | Makes listing work but extraction is not real LLM; current proposal says no |
