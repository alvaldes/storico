# Workspaces Specification

> Full spec for the Workspaces feature — new organizational entity that replaces the flat User→Project model with multi-tenant workspace isolation.

## Purpose

Introduce Workspaces as the top-level organizational boundary in Storico. Workspaces group projects, members, LLM configuration, and prompt templates into fully isolated tenants, enabling team collaboration, role-based access, and per-team LLM/prompt configuration.

---

## 1. Functional Requirements

### Workspace CRUD

| ID | Title | Description | Priority | Notes |
|----|-------|-------------|----------|-------|
| WS-001 | Create workspace | The system MUST allow any authenticated user to create a workspace. The creator becomes both admin and owner. A personal workspace MUST be auto-created on first registration. | P0 | On user registration, auto-create a workspace named `<user.name>'s Workspace`. Creator is admin+owner. |
| WS-002 | List user's workspaces | The system MUST return all workspaces the authenticated user belongs to (as member or admin). | P0 | No pagination for MVP; returns full list. |
| WS-003 | Get workspace by ID | The system MUST return workspace details for a given ID if the user is a member. | P0 | Returns 404 (not 403) to avoid leaking workspace existence. |
| WS-004 | Update workspace | The system MUST allow admins to update workspace name and slug. | P0 | Slug uniqueness enforced at DB level. Re-slugging must cascade to URL references. |
| WS-005 | Delete workspace | The system MUST allow admins to delete a workspace, which cascades to all members, projects, stories, tasks, LLM config, and prompts. | P1 | Confirmation dialog required on frontend. Soft-delete not required for MVP. |

### Workspace Membership

| ID | Title | Description | Priority | Notes |
|----|-------|-------------|----------|-------|
| WS-006 | Add member | The system MUST allow admins to add a user to the workspace with role `member`. | P0 | User must already exist in the system. Invitation flow (email) is out of scope for MVP — direct add by user ID. |
| WS-007 | Remove member | The system MUST allow admins to remove a member from the workspace. The owner cannot be removed. | P0 | If owner is the only admin, they must transfer ownership or promote another admin first. |
| WS-008 | List members | The system MUST return all members of a workspace with their roles. Admin only. | P0 | Includes user info (id, name, email, avatar). |
| WS-009 | Change member role | The system MUST allow admins to promote a member to admin or demote an admin to member. | P0 | Cannot demote the owner. Cannot promote beyond admin (no super-admin role). |
| WS-010 | Transfer ownership | The system MUST allow the current owner to transfer ownership to another admin. On transfer, the new owner becomes owner+admin; the old owner becomes admin. | P0 | Only the current owner can initiate. Target must be an admin. |

### Project Scoping

| ID | Title | Description | Priority | Notes |
|----|-------|-------------|----------|-------|
| WS-011 | Create project in workspace | The system MUST allow members to create a project within a workspace. The project's `workspace_id` SHALL be set to the workspace ID. | P0 | `created_by` FK to User for audit. |
| WS-012 | List projects in workspace | The system MUST return all projects scoped to the workspace the user is a member of. | P0 | Excludes projects from other workspaces entirely. |

### LLM Config Management

| ID | Title | Description | Priority | Notes |
|----|-------|-------------|----------|-------|
| WS-013 | Get workspace LLM config | The system MUST return the LLM config for a workspace (admin only). If no custom config exists, SHALL fall back to global defaults. | P0 | Fallback is read-time — no DB row created for defaults. |
| WS-014 | Upsert workspace LLM config | The system MUST allow admins to set or update the workspace's LLM config (provider, model, temperature, max_tokens, base_url). | P0 | Upsert pattern — creates if absent, updates if exists. All fields are optional; only provided fields are updated. |

### Prompt Management

| ID | Title | Description | Priority | Notes |
|----|-------|-------------|----------|-------|
| WS-015 | Get workspace prompts | The system MUST return the prompt templates for a workspace (admin only). Falls back to global defaults if no custom prompts set. | P1 | System prompt, instruction template, few-shot examples. |
| WS-016 | Upsert workspace prompts | The system MUST allow admins to set or update workspace prompt templates. | P1 | Same upsert pattern as LLM config. |

### Auth Enforcement

| ID | Title | Description | Priority | Notes |
|----|-------|-------------|----------|-------|
| WS-017 | Unauthenticated request returns 401 | ALL API routes MUST require authentication. If no valid auth token is provided, the system SHALL return 401. | P0 | Applies to existing routes (auth debt fix) and new routes. |
| WS-018 | Cross-workspace access returns 403 | If a user is authenticated but NOT a member of the target workspace, the system SHALL return 403 for any workspace-scoped route. | P0 | 404 for workspace GET to avoid existence leaks. 403 for data routes. |
| WS-019 | Insufficient role returns 403 | If a user is a member but attempts an admin-only action, the system SHALL return 403. | P0 | Admin-only: member management, LLM config, prompts, workspace settings, workspace deletion, ownership transfer. |

### User Settings Separation

| ID | Title | Description | Priority | Notes |
|----|-------|-------------|----------|-------|
| WS-020 | User settings remain at user level | The system MUST keep theme, language, and user profile settings at the user level, NOT scoped to workspace. | P0 | `GET /api/v1/settings` and `PUT /api/v1/settings` remain unchanged. |

### Workspace Resolution

| ID | Title | Description | Priority | Notes |
|----|-------|-------------|----------|-------|
| WS-021 | Workspace resolved from URL path | The system MUST extract `workspace_id` from the URL path parameter — NOT from headers, subdomains, or request body. | P0 | FastAPI `Path` extractor. Pattern: `/api/v1/workspaces/{workspace_id}/...` |

---

## 2. Non-Functional Requirements

| ID | Title | Description |
|----|-------|-------------|
| NFR-001 | Workspace isolation | A user MUST NOT see data from a workspace they do not belong to. All workspace-scoped queries MUST filter by `workspace_id` joined through the membership table. |
| NFR-002 | Role enforcement | Members MUST NOT access admin-only endpoints. The dependency chain (`get_current_user` → `get_workspace_for_user` → `require_admin`) SHALL be applied to every workspace-scoped route. |
| NFR-003 | No regression | Existing user-level flows (auth sync, settings, user profile) MUST remain unchanged. The `/api/v1/settings` and `/api/v1/me` endpoints SHALL NOT require workspace context. |
| NFR-004 | Performance overhead | The workspace membership check MUST add less than 50ms overhead per request. This SHALL be verified with a query that joins `workspace_members` by `(workspace_id, user_id)` — indexed columns. |

---

## 3. User Scenarios

### Scenario 1: First registration auto-creates personal workspace

```
GIVEN a user who has never registered
WHEN they register with a valid email via OAuth (Google or GitHub)
THEN the system creates a personal workspace named "<User's Name>'s Workspace"
AND the user is assigned as admin+owner of that workspace
AND the user sees the dashboard with their personal workspace selected
```

### Scenario 2: User creates a workspace and invites a colleague

```
GIVEN Alice is authenticated with workspace "Alice's Workspace" selected
WHEN she navigates to Workspace Settings → Create New Workspace
AND enters name "Acme Project" and clicks Create
THEN a new workspace "Acme Project" is created with Alice as admin+owner
AND Alice navigates to Members → Add Member
AND enters Bob's user ID
THEN Bob appears in the member list with role "member"
AND Bob can now see "Acme Project" in his TeamSwitcher
```

### Scenario 3: Admin updates LLM config for workspace

```
GIVEN Alice is an admin of workspace "Acme Project"
WHEN she navigates to Workspace Settings → LLM Configuration
AND changes the model from "llama3.2" to "mistral" and temperature to 0.2
AND clicks Save
THEN the system persists the LLM config for "Acme Project"
AND subsequent extractions in this workspace use "mistral" with temperature 0.2
```

### Scenario 4: Member denied access to workspace settings

```
GIVEN Bob is a member (not admin) of workspace "Acme Project"
WHEN he navigates to Workspace Settings → LLM Configuration
THEN the system returns HTTP 403 Forbidden
AND the UI hides the Settings menu item for Bob (conditionally rendered)
```

### Scenario 5: Owner transfers ownership to another admin

```
GIVEN Alice is the owner of workspace "Acme Project"
AND Bob is an admin of the same workspace
WHEN Alice navigates to Members → Transfer Ownership
AND selects Bob as the new owner and confirms
THEN Bob becomes the new owner (admin+owner)
AND Alice's role changes to admin (not owner)
AND Alice can no longer delete the workspace or transfer ownership again
```

### Scenario 6: User switches workspace → data scope changes

```
GIVEN Alice is a member of both "Alice's Workspace" and "Acme Project"
AND "Alice's Workspace" has project "Personal Blog"
AND "Acme Project" has project "E-commerce App"
WHEN Alice selects "Alice's Workspace" in the TeamSwitcher
THEN the project list shows "Personal Blog" only
WHEN Alice selects "Acme Project" in the TeamSwitcher
THEN the project list shows "E-commerce App" only
```

### Scenario 7: Unauthenticated request to workspace endpoint

```
GIVEN no authentication token is provided
WHEN a request is made to GET /api/v1/workspaces
THEN the system returns HTTP 401 Unauthorized
AND the response body describes the missing authentication
```

---

## 4. Acceptance Criteria

| ID | Criterion | Related Requirement |
|----|-----------|-------------------|
| AC-001 | New user registration creates a personal workspace with user as admin+owner | WS-001 |
| AC-002 | Authenticated user can list their workspaces via `GET /api/v1/workspaces` | WS-002 |
| AC-003 | Admin can add a user by ID to a workspace with role `member` | WS-006 |
| AC-004 | Admin can remove a non-owner member from a workspace | WS-007 |
| AC-005 | Admin can promote a member to admin and demote an admin (except owner) | WS-009 |
| AC-006 | Owner can transfer ownership to another admin; old owner becomes admin | WS-010 |
| AC-007 | Projects created in a workspace have `workspace_id` set and `created_by` set | WS-011 |
| AC-008 | Member of workspace A cannot access projects from workspace B (403) | WS-018, NFR-001 |
| AC-009 | Admin can upsert LLM config for a workspace; member gets 403 | WS-013, WS-014, WS-019 |
| AC-010 | Admin can upsert workspace prompts; member gets 403 | WS-015, WS-016, WS-019 |
| AC-011 | All API routes return 401 when no auth token is provided | WS-017 |
| AC-012 | User settings (`/api/v1/settings`) still work without workspace context | WS-020, NFR-003 |
| AC-013 | Workspace membership check completes in <50ms (verified by integration test) | NFR-004 |
| AC-014 | `owner_id` is completely removed from the codebase (all references replaced) | WS-011 |

---

## 5. Data Schema Reference

### Table: `workspaces`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `name` | VARCHAR(255) | NOT NULL | Display name |
| `slug` | VARCHAR(100) | NOT NULL, UNIQUE | URL-friendly identifier |
| `owner_id` | UUID | NOT NULL, FK → `users.id` | The single owner; special admin |
| `created_at` | TIMESTAMPTZ | NOT NULL, default `now()` | |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default `now()` | |

### Table: `workspace_members`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `workspace_id` | UUID | NOT NULL, FK → `workspaces.id` ON DELETE CASCADE | |
| `user_id` | UUID | NOT NULL, FK → `users.id` ON DELETE CASCADE | |
| `role` | ENUM('admin', 'member') | NOT NULL | |
| `created_at` | TIMESTAMPTZ | NOT NULL, default `now()` | |
| | | UNIQUE(workspace_id, user_id) | Prevents duplicate membership |

### Table: `workspace_llm_configs`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `workspace_id` | UUID | NOT NULL, FK → `workspaces.id` ON DELETE CASCADE, UNIQUE | 1:1 with workspace |
| `provider` | VARCHAR(50) | NOT NULL | e.g., "ollama", "openai" |
| `model` | VARCHAR(100) | NOT NULL | e.g., "llama3.2", "gpt-4" |
| `temperature` | FLOAT | nullable | Defaults to system default if NULL |
| `max_tokens` | INT | nullable | Defaults to system default if NULL |
| `base_url` | VARCHAR(500) | nullable | For custom Ollama endpoints |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default `now()` | |

### Table: `workspace_prompts`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK, default `gen_random_uuid()` | |
| `workspace_id` | UUID | NOT NULL, FK → `workspaces.id` ON DELETE CASCADE, UNIQUE | 1:1 with workspace |
| `system_prompt` | TEXT | nullable | Overrides global system prompt |
| `instruction_template` | TEXT | nullable | Overrides global instruction template |
| `few_shot_examples` | JSONB | nullable | Overrides global few-shot examples |
| `updated_at` | TIMESTAMPTZ | NOT NULL, default `now()` | |

### Table: `projects` (modified)

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| `id` | UUID | PK | |
| `workspace_id` | UUID | NOT NULL, FK → `workspaces.id` ON DELETE CASCADE | **NEW** — replaces `owner_id` |
| `created_by` | UUID | nullable, FK → `users.id` | **NEW** — audit-only, existing rows get NULL |
| `name` | VARCHAR(255) | NOT NULL | |
| `description` | TEXT | nullable | |
| `created_at` | TIMESTAMPTZ | NOT NULL | |
| `updated_at` | TIMESTAMPTZ | NOT NULL | |

**Removed**: `owner_id` (UUID, FK → `users.id`) — replaced by `workspace_id` + `created_by`.

---

## 6. API Contract

### Workspace Management

#### `GET /api/v1/workspaces`

List all workspaces the authenticated user belongs to.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `{ "workspaces": [{ id, name, slug, role, owner_id, created_at }] }` |
| Status | 200 OK, 401 Unauthorized |
| Permission | Authenticated user |

#### `POST /api/v1/workspaces`

Create a new workspace.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Body | `{ "name": "string", "slug": "string (optional, auto-generated from name)" }` |
| Response | `{ "id": "uuid", "name": "string", "slug": "string", "owner_id": "uuid", "role": "admin", "created_at": "datetime" }` |
| Status | 201 Created, 400 Bad Request (validation), 401 Unauthorized, 409 Conflict (slug taken) |
| Permission | Any authenticated user |

#### `GET /api/v1/workspaces/{workspace_id}`

Get workspace details.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `{ "id": "...", "name": "...", "slug": "...", "owner_id": "...", "role": "admin|member", "member_count": int, "created_at": "..." }` |
| Status | 200 OK, 401 Unauthorized, 404 Not Found |
| Permission | Workspace member |

#### `PUT /api/v1/workspaces/{workspace_id}`

Update workspace name/slug.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Body | `{ "name": "string (optional)", "slug": "string (optional)" }` |
| Response | `{ "id": "...", "name": "...", "slug": "...", "updated_at": "..." }` |
| Status | 200 OK, 400 Bad Request, 401, 403 Forbidden, 404, 409 Conflict |
| Permission | Workspace admin |

#### `DELETE /api/v1/workspaces/{workspace_id}`

Delete workspace and all associated data.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `204 No Content` |
| Status | 204 No Content, 401, 403, 404 |
| Permission | Workspace admin |

#### `POST /api/v1/workspaces/{workspace_id}/transfer`

Transfer workspace ownership to another admin.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Body | `{ "new_owner_id": "uuid" }` |
| Response | `{ "message": "Ownership transferred", "previous_owner_id": "uuid", "new_owner_id": "uuid" }` |
| Status | 200 OK, 400 (target not admin), 401, 403 (not current owner), 404 |
| Permission | Workspace owner (current) |

### Workspace Members

#### `GET /api/v1/workspaces/{workspace_id}/members`

List workspace members.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `{ "members": [{ "user_id": "uuid", "name": "...", "email": "...", "role": "admin|member", "joined_at": "..." }] }` |
| Status | 200 OK, 401, 403, 404 |
| Permission | Workspace admin |

#### `POST /api/v1/workspaces/{workspace_id}/members`

Add a member to the workspace.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Body | `{ "user_id": "uuid" }` |
| Response | `{ "user_id": "uuid", "role": "member", "created_at": "..." }` |
| Status | 201 Created, 400 (user not found), 401, 403, 404, 409 (already member) |
| Permission | Workspace admin |

#### `PUT /api/v1/workspaces/{workspace_id}/members/{user_id}`

Change member role.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Body | `{ "role": "admin" | "member" }` |
| Response | `{ "user_id": "uuid", "role": "admin|member", "updated_at": "..." }` |
| Status | 200 OK, 400 (cannot demote owner), 401, 403, 404 |
| Permission | Workspace admin |

#### `DELETE /api/v1/workspaces/{workspace_id}/members/{user_id}`

Remove a member from the workspace.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `204 No Content` |
| Status | 204, 400 (cannot remove owner), 401, 403, 404 |
| Permission | Workspace admin |

### Workspace Settings

#### `GET /api/v1/workspaces/{workspace_id}/settings/llm`

Get workspace LLM config (falls back to global defaults).

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `{ "provider": "...", "model": "...", "temperature": float|null, "max_tokens": int|null, "base_url": "..." }` |
| Status | 200 OK, 401, 403, 404 |
| Permission | Workspace admin |

#### `PUT /api/v1/workspaces/{workspace_id}/settings/llm`

Upsert workspace LLM config.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Body | `{ "provider": "string (optional)", "model": "string (optional)", "temperature": "float (optional)", "max_tokens": "int (optional)", "base_url": "string (optional)" }` |
| Response | `{ "provider": "...", "model": "...", ... }` |
| Status | 200 OK, 400, 401, 403, 404 |
| Permission | Workspace admin |

#### `GET /api/v1/workspaces/{workspace_id}/settings/prompts`

Get workspace prompts (falls back to global defaults).

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `{ "system_prompt": "text|null", "instruction_template": "text|null", "few_shot_examples": "array|null" }` |
| Status | 200 OK, 401, 403, 404 |
| Permission | Workspace admin |

#### `PUT /api/v1/workspaces/{workspace_id}/settings/prompts`

Upsert workspace prompts.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Body | `{ "system_prompt": "text (optional)", "instruction_template": "text (optional)", "few_shot_examples": "array (optional)" }` |
| Response | `{ "system_prompt": "...", ... }` |
| Status | 200 OK, 400, 401, 403, 404 |
| Permission | Workspace admin |

### Data (Workspace-Scoped)

#### `GET /api/v1/workspaces/{workspace_id}/projects`

List projects in workspace.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `{ "projects": [{ id, name, description, created_by, created_at, updated_at }] }` |
| Status | 200 OK, 401, 403, 404 |
| Permission | Workspace member |

#### `POST /api/v1/workspaces/{workspace_id}/projects`

Create a project in the workspace.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Body | `{ "name": "string", "description": "string (optional)" }` |
| Response | `{ "id": "uuid", "name": "...", "workspace_id": "uuid", "created_by": "uuid", "created_at": "..." }` |
| Status | 201 Created, 400, 401, 403, 404 |
| Permission | Workspace member |

### User-Level (Unchanged)

#### `GET /api/v1/settings`

Get user preferences (theme, language).

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `{ "theme": "light|dark|auto", "language": "en|es" }` |
| Status | 200 OK, 401 |
| Permission | Authenticated user |

#### `GET /api/v1/me`

Get current user profile with workspace list.

| Field | Value |
|-------|-------|
| Headers | `Authorization: Bearer <token>` |
| Response | `{ "user": { id, name, email, avatar }, "workspaces": [{ id, name, slug, role }] }` |
| Status | 200 OK, 401 |
| Permission | Authenticated user |
