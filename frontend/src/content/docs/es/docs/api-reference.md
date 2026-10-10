---
title: Referencia de la API
description: Todos los endpoints que expone la API de Storico, con sus parámetros y respuestas.
---

Cada ruta de abajo se genera desde la propia aplicación FastAPI, así que describe lo que el código responde y no lo que un documento recordaba. Los nombres propios de la API —rutas, campos, tipos— quedan en inglés, porque la API está en inglés.

## auth

### `POST` `/api/v1/auth/sync`

Sync User

Sync a user from OAuth login — 3-step linking flow.

Step (a): find by (provider, provider_id) → update profile.
Step (b): fallback to find_by_email → link accounts.
Step (c): neither → create user + link account + create personal workspace.

**Parámetros**

_Sin parámetros._

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `email` | `string` | sí |
| `name` | `string` | sí |
| `auth_provider` | `string` | sí |
| `auth_provider_id` | `string` | sí |
| `avatar_url` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `UserResponse` |
| `422` | Validation Error | `HTTPValidationError` |

## export

### `GET` `/api/v1/workspaces/{workspace_id}/export/tasks`

Export Tasks

Export tasks from a workspace in the requested format and scope.

Supported formats:
- ``json`` (default): JSON array of tasks
- ``markdown``: Markdown document with one section per story
- ``csv``: one row per task, columns in this order — ``story, version,
  title, description, status, priority, labels, dependencies`` — with
  multi-value cells (``labels``, ``dependencies``) joined by ``;``. The
  column order is a contract: adding a column later is compatible;
  renaming or reordering one is not.

**Scope — one target, never two** (the same rule the Trello trigger
resolves through): no target exports the whole workspace; ``project_id``
or ``user_story_id`` narrows it to that project or story; both together
answer ``422 REQUEST_VALIDATION_FAILED``. A target must exist and sit in
the path workspace (a foreign project or story answers ``403``, a missing
one ``404``).

**Version**: without ``extraction_id``, each story's current version (the
highest-numbered ``completed`` run) is exported — the filter rides the
serializing statement itself, so a superseded version's tasks can never
leak into the file. With ``extraction_id`` **and** ``user_story_id``, the
named version's tasks are exported even when a newer run superseded it —
the version is identified by its extraction id, never by its version
number, which is a position in a history the next run moves. An
``extraction_id`` without ``user_story_id`` answers ``422``: a version
belongs to a story, and a version asked for at project or workspace level
is a question with no answer. The ``version`` column of the CSV carries
the run's version number; the ``json`` and ``markdown`` shapes are
unchanged.

The response includes a ``Content-Disposition`` header for file download,
unless ``preview=true``: then the exact same body — the same endpoint, the
same parameters, one code path — is returned **without** that header, so
the browser displays it instead of saving it. One serialization, two
dispositions: what a preview shows cannot differ from what the download
saves, because they are the same bytes.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |
| `extraction_id` | `query` | no | `string | null` |
| `format` | `query` | no | `string` |
| `preview` | `query` | no | `boolean` |
| `project_id` | `query` | no | `string | null` |
| `user_story_id` | `query` | no | `string | null` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | — |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/workspaces/{workspace_id}/export/trello`

Export To Trello

Send the workspace's current-version tasks to a new Trello board.

**Asynchronous, like the extraction**: the job row is created pending, the
work is dispatched with ``asyncio.create_task`` in the API process (D5 — no
Celery, no Redis), and this answers ``202`` immediately. The client polls
``GET .../export/trello/{export_id}`` until the job reaches ``completed``
(with the board URL) or ``failed`` (with its error code, and the board URL
too when a half-built board exists).

**Any member may trigger** (D7): the credentials are what is admin-only —
the ``/settings/trello`` pair — and the export reads the same tasks
``GET .../export/tasks`` already lets any member read. A workspace with no
credential pair stored answers ``409 TRELLO_CREDENTIALS_MISSING`` before
anything is created.

The scope is one of three, never two (D1): both optional targets given is a
``422`` — the rule the Kanban cascade applies. Only each story's current
version is exported (D8), the same filter the file export rides.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `project_id` | `string | null` | no |
| `user_story_id` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `202` | Successful Response | `TrelloExportResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/export/trello/preview`

Preview Trello Export

Return the board plan the Trello trigger would send — as JSON, creating nothing.

The shape (decision E4, record ``export-page-rework``): the board's name,
its lists in Kanban order, and each card's title, description, labels and
resolved dependency titles — the same ``TrelloBoardPlan`` the runner builds,
through the same application entry point (``build_board_plan_for_scope``),
so the preview can only ever show what the export would create.

**It describes, it does not perform.** No ``trello_exports`` row is written
and the workspace's Trello credentials are never read: describing what
would be exported requires no permission to create it, so a workspace
without credentials answers the preview instead of ``409``.

**Scope — the trigger's rule, inherited**: no target previews the whole
workspace's board; ``project_id`` or ``user_story_id`` narrows it; both
together answer ``422 REQUEST_VALIDATION_FAILED``, a foreign target ``403``
and a missing one ``404`` — the same refusals the trigger and the file
export apply.

The scope parameters stop at story level for now: a version dimension for
the Trello export is planned (the same EP that teaches the trigger and the
plan to carry it) and will join here as a parameter that requires
``user_story_id`` — the pairing the file export already enforces. No field
is invented for it ahead of that decision.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |
| `project_id` | `query` | no | `string | null` |
| `user_story_id` | `query` | no | `string | null` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `TrelloBoardPlanResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/export/trello/{export_id}`

Get Trello Export

Report one export job's state, board URL and error code.

Readable by any member — the same audience that may trigger the export. A
job of another workspace is reported as a miss (404), so a foreign id is
not distinguishable from an absent one.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `export_id` | `path` | sí | `string` |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `TrelloExportResponse` |
| `422` | Validation Error | `HTTPValidationError` |

## extract

### `POST` `/api/v1/workspaces/{workspace_id}/extract/`

Extract Tasks

Extract tasks from a user story using an LLM.

The user story must belong to a project within the workspace specified
in the URL path. Only the workspace owner or a member with the ``admin``
role may start an extraction: a member with the ``member`` role gets
403 ``WORKSPACE_OWNER_OR_ADMIN_REQUIRED`` and a non-member 403
``NOT_A_WORKSPACE_MEMBER``, and neither creates an extraction.

**This endpoint is asynchronous.** It creates a pending extraction
record, launches the LLM call in a background task, and responds
**immediately** with ``202 Accepted``. The client must poll
``GET /api/v1/extractions/{extraction_id}`` to get the final status.

When the extraction completes, tasks are persisted to the database
and can be fetched via ``GET /api/v1/tasks?user_story_id=...``.

If ``body.model`` is ``None``, the model is resolved from the
workspace's LLM config.

The workspace's LLM configuration must be complete for its provider before
anything is created. When it is not, this answers ``400`` with
``error_code: "LLM_CONFIG_INCOMPLETE"`` and the missing field names, leaving the
story and the extraction table untouched.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `user_story_id` | `string` | sí |
| `model` | `string | null` | no |
| `temperature` | `number | null` | no |
| `run_validation` | `boolean` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `202` | Successful Response | `ExtractResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/extract/status/{extraction_id}`

Extraction Status

Get the status and details of an extraction by its ID.

The extraction must belong to a user story in the workspace specified
in the URL path. Workspace membership is validated via
``get_workspace_for_user``.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `extraction_id` | `path` | sí | `string` |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `ExtractionResponse` |
| `422` | Validation Error | `HTTPValidationError` |

## extractions

### `GET` `/api/v1/extractions/`

List Extractions

List extractions with optional filters and pagination.

Filters:
- ``user_story_id``: filter by user story (requires workspace membership).
- ``workspace_id``: filter by workspace (requires workspace membership).

If neither filter is provided, returns extractions from all workspaces
the current user is a member of.

The page and its total come from one statement in the database —
``count(*) OVER ()`` rides on the rows' own query, so no separate
``SELECT COUNT(*)`` is issued. The order is ``created_at DESC, id DESC``,
which makes the paging deterministic.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `page` | `query` | no | `integer` |
| `size` | `query` | no | `integer` |
| `user_story_id` | `query` | no | `string | null` |
| `workspace_id` | `query` | no | `string | null` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `PaginatedResponse_ExtractionResponse_` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/extractions/{extraction_id}`

Get Extraction

Get an extraction by its ID.

The user must be a member of the workspace that owns the extraction's user story project.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `extraction_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `ExtractionResponse` |
| `422` | Validation Error | `HTTPValidationError` |

## health

### `GET` `/api/v1/health`

Health

Return API health status.

Only checks the database — the single required dependency. Ollama, Qdrant and the
embeddings provider are optional integrations: /health does not check them, and
/health/services publishes them as optional probes without letting them degrade its
status.

The schema is reported next to the database but does not change ``status`` or the HTTP code:
this is a liveness probe, and a schema behind the code is a reason not to send traffic, not a
reason to kill and restart a container that is running.

The two probes run concurrently (``asyncio.gather``): the route costs the slowest probe rather
than their sum, which liveness clients were paying in full on every poll.

**Parámetros**

_Sin parámetros._

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | — |

### `GET` `/api/v1/health/ready`

Health Ready

Readiness: 200 only when the database answers and the schema is at the code's head.

Liveness and readiness answer different questions, which is why this is a second route rather
than a stricter ``/health``. A container whose schema is behind should not take traffic, but
restarting it would not migrate anything — so ``/health`` keeps answering 200 and this route
answers 503 until an operator applies the pending revision.

The status code is the whole interface: ``curl -sf`` under ``set -e`` fails a deploy without
parsing JSON on the VM. The body is the same document either way, so a reader never has to
branch on the code to read it.

Like its siblings this route takes no authentication, and it publishes no revision.

The two probes run concurrently (``asyncio.gather``): the route costs the slowest probe rather
than their sum, which readiness gates were paying in full on every deploy check.

**Parámetros**

_Sin parámetros._

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | — |

### `GET` `/api/v1/health/services`

Health Services

Full diagnostics — every probe, published with its scope.

Each probe carries ``"scope": "required" | "optional"``. Required means the
deployment is not useful without it; optional means an integration a workspace may
never use, whose failure degrades a feature rather than the service. The top-level
``status`` reflects the required probes only, so an optional integration being
unreachable does not paint the whole deployment degraded. The five probes run
concurrently (``asyncio.gather``) and none of them raises — each catches its own
exceptions — so the route costs the slowest probe instead of the sum of all five,
which the public /status page and polling clients were paying in full.

This is a debugging endpoint: use /api/v1/health for the liveness answer and
/api/v1/health/ready for readiness.

**Parámetros**

_Sin parámetros._

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | — |

## projects

### `GET` `/api/v1/workspaces/{workspace_id}/projects/`

List Projects

List all projects in the workspace. Workspace member access.

The per-project story count is folded into the page query with a LEFT
OUTER JOIN + GROUP BY (removes the N+1 ``count_stories`` loop), and the
page and its total come from that one statement in the database —
``count(*) OVER ()`` rides on the rows' own query, so no separate
``SELECT COUNT(*)`` is issued. The order is ``created_at DESC, id DESC``,
which makes the paging deterministic. See
domain/entities/project.py:ProjectWithCount.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |
| `page` | `query` | no | `integer` |
| `size` | `query` | no | `integer` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `PaginatedResponse_ProjectResponse_` |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/workspaces/{workspace_id}/projects/`

Create Project

Create a new project in the workspace. Workspace member access.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `name` | `string` | sí |
| `description` | `string` | no |
| `icon` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `201` | Successful Response | `ProjectResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/projects/{project_id}`

Get Project

Get a project by its ID. Workspace member access.

Uses ``find_by_id_with_count`` (LEFT OUTER JOIN + GROUP BY) so the
project and its story count come from a single round-trip, replacing
the previous find_by_id + count_stories pattern (2 round-trips).
The JSON schema of the response is unchanged.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `project_id` | `path` | sí | `string` |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `ProjectResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `PUT` `/api/v1/workspaces/{workspace_id}/projects/{project_id}`

Update Project

Update an existing project. Workspace member access.

``save`` does not return the story count, so after persisting the
update we re-fetch via ``find_by_id_with_count`` (one round-trip).
Together with the membership check up front, this replaces the old
find_by_id + save + count_stories pattern (3 round-trips) with
membership_check(save already persists) + find_with_count = 2.
Response schema is unchanged.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `project_id` | `path` | sí | `string` |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `name` | `string | null` | no |
| `description` | `string | null` | no |
| `icon` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `ProjectResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `DELETE` `/api/v1/workspaces/{workspace_id}/projects/{project_id}`

Delete Project

Delete a project by its ID. Workspace member access.

Does not need the story count, so the membership-only path is used
(the helper still returns the count, which we discard here).

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `project_id` | `path` | sí | `string` |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `204` | Successful Response | — |
| `422` | Validation Error | `HTTPValidationError` |

## settings

### `DELETE` `/api/v1/users/me`

Delete Account

Permanently delete the current user's account and ALL associated data.

This action cannot be undone. All projects, stories, tasks, extractions,
and linked accounts are cascade-deleted — with one designed refusal: if
the account's invalidation revocations still stand, the delete is refused
with 409 ``ACCOUNT_DELETE_BLOCKED`` before anything is touched.
``fk_task_invalidations_revoked_by_users`` is ``ON DELETE RESTRICT``, so
those rows refuse to lose their revoker; the pre-check names each blocking
mark (story id, version number, task title) so the user can act on it —
by having the marking stories deleted, since a revoke is history and has
no undo endpoint. A revoke that lands between the pre-check and the delete
still surfaces as the raw integrity refusal: translating it belongs to
``UserRepository.delete``, which this route does not own.

**Parámetros**

_Sin parámetros._

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `DeleteAccountResponse` |

### `GET` `/api/v1/users/me/settings`

Get Settings

Return the current user's application preferences.

Returns defaults (from pydantic schema) when no preferences exist yet.

A stored document is read through the schema with the removed keys dropped: ``AppSettings``
forbids extras, so a row written before the per-user LLM block was removed would otherwise
fail validation and answer 500. Revision ``0022`` cleaned storage; this covers a row it did
not reach.

**Parámetros**

_Sin parámetros._

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `UserPreferencesResponse` |

### `PUT` `/api/v1/users/me/settings`

Update Settings

Create or replace the current user's application preferences.

**Parámetros**

_Sin parámetros._

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `preferences` | `AppSettings` | sí |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `UserPreferencesResponse` |
| `422` | Validation Error | `HTTPValidationError` |

## stories

### `GET` `/api/v1/stories/`

List Stories

List user stories with optional filters and pagination.

Filters:
- ``project_id``: filter by project (requires workspace membership).
- ``workspace_id``: filter by workspace (requires workspace membership).

If neither filter is provided, returns stories from all workspaces
the current user is a member of.

The page and its total come from one statement in the database —
``count(*) OVER ()`` rides on the rows' own query, so no separate
``SELECT COUNT(*)`` is issued. The order is ``created_at DESC, id DESC``,
which makes the paging deterministic.

Each item's ``version_summary`` is projected from **one** batched read for
the whole page's story ids — never one per card (decision D4/D2 of feature
``versioning-visibility``). A story with no versions answers ``null``, and
an empty page answers without a statement at all.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `page` | `query` | no | `integer` |
| `project_id` | `query` | no | `string | null` |
| `size` | `query` | no | `integer` |
| `workspace_id` | `query` | no | `string | null` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `PaginatedResponse_UserStoryResponse_` |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/stories/`

Create Story

Create a new user story.

The story's project must belong to a workspace the user is a member of.
Duplicate stories (same actor, feature and benefit) within the same project are
not allowed.

**Parámetros**

_Sin parámetros._

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `project_id` | `string` | sí |
| `actor` | `string` | sí |
| `feature` | `string` | sí |
| `benefit` | `string` | sí |
| `raw_text` | `string` | sí |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `201` | Successful Response | `UserStoryResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/stories/{story_id}`

Get Story

Get a user story by its ID.

The user must be a member of the workspace that owns the story's project.
The response projects the story's ``version_summary`` — one read for the
one story, the same projection the list page carries (decision D4).

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `story_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `UserStoryResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `PUT` `/api/v1/stories/{story_id}`

Update Story

Update an existing user story.

The user must be a member of the workspace that owns the story's project.
The response projects the story's ``version_summary`` like the reads do:
answering ``null`` here would report a version count of zero for a story
that has versions (decision D4).

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `story_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `actor` | `string | null` | no |
| `feature` | `string | null` | no |
| `benefit` | `string | null` | no |
| `raw_text` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `UserStoryResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `DELETE` `/api/v1/stories/{story_id}`

Delete Story

Delete a user story by its ID.

Only the workspace owner or an ``ADMIN`` may delete: a plain ``MEMBER`` is
refused with 403 ``WORKSPACE_OWNER_OR_ADMIN_REQUIRED``, a non-member keeps
403 ``NOT_A_WORKSPACE_MEMBER``, and a missing story is 404. The deletion
snapshots the story's versions, removes its vector points (when a vector
store is configured) and then deletes the story and writes an audit record
of the destroyed versions in one transaction. A vector store that cannot
be reached answers 503 ``VECTOR_STORE_UNAVAILABLE`` and leaves the story,
its versions and its tasks intact for a retry.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `story_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `204` | Successful Response | — |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/stories/{story_id}/invalidations`

List Story Invalidations

List the story's active invalidation marks, newest first.

The story-detail card renders one flag per task, so the page asks once for
the story instead of once per task. The user must be a member of the
workspace that owns the story's project — the unchanged
``require_story_workspace_access`` walk, so a missing story is 404 and a
non-member is 403 ``NOT_A_WORKSPACE_MEMBER``, exactly the posture of
``GET /{story_id}/versions``. The gate is membership, not ownership: every
member may read the record, the mutations are the gated half.

The response is a **bare unpaginated array** like the versions read: the
list is an input to the card, not a paginated resource. Every version of
the story is included; the caller intersects the marks with the tasks it is
displaying, so a frozen version's cards stay correct without a second
query shape. Revoked marks are history and never appear here — they belong
to ``GET /api/v1/tasks/{task_id}/invalidations``.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `story_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `StoryInvalidationResponse[]` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/stories/{story_id}/versions`

List Story Versions

List every version of a user story, newest first, for the version selector.

The user must be a member of the workspace that owns the story's project —
the unchanged ``require_story_workspace_access`` walk, so a missing story is
404 and a non-member is 403 ``NOT_A_WORKSPACE_MEMBER``, exactly the posture
``GET /{story_id}`` has; nothing about the workspace leaks into either body.

The response is a **bare unpaginated array**: the list is the selector's
pagination *input*, not a paginated resource, so the paginator's window must
never truncate it. ``pending`` and ``failed`` runs are part of the history
the user must see and are never filtered out. The two booleans are derived
here, never stored: ``is_current`` marks the first ``completed`` entry of
the ``version_number DESC`` list (a story with no completed run has no
current entry — the legal frozen state), and ``has_output`` is
``status == completed``.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `story_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `StoryVersionResponse[]` |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/workspaces/{workspace_id}/stories/import`

Import Stories

Import user stories into a project from an uploaded CSV file.

The workspace in the path must exist and the caller must be a member of
it (``get_workspace_for_user``). The project must then belong to that
same workspace. The upload is validated as a whole before anything is
written: one blocking error anywhere answers ``422`` with the full error
list and no story is created. Rows that duplicate an existing story (or
an earlier row of the same upload) are skipped and reported, never fatal.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`multipart/form-data`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `project_id` | `string` | sí |
| `file` | `string` | sí |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `201` | Successful Response | `StoryImportResponse` |
| `422` | Validation Error | `HTTPValidationError` |

## tasks

### `GET` `/api/v1/tasks/`

List Tasks

List tasks with optional filters and pagination.

Filters:
- ``user_story_id``: filter by user story (requires workspace membership).
  By default only the story's current version (the highest-numbered
  ``completed`` run) is answered; passing ``extraction_id`` reads exactly
  that version instead, so a superseded version's tasks stay addressable.
  A version that does not belong to the requested story — or does not
  exist — is refused with 422 ``REQUEST_VALIDATION_FAILED``.
- ``workspace_id``: filter by workspace (requires workspace membership).
- ``project_id``: filter by project (requires membership of the project's
  workspace). Like the workspace board, it answers each story's current
  version only.

``extraction_id`` is a story-scoped question: supplying it without
``user_story_id`` is refused with 422 before any repository call (the
repository's own ``ValueError`` for that shape is an internal invariant,
not an HTTP contract).

The three scope filters are mutually exclusive: several at once are
refused with 422 ``REQUEST_VALIDATION_FAILED`` before any repository call
(decision D7) — an ``if``/``elif`` chain would silently answer one of
them, a wrong answer shaped like a right one.

If no scope filter is provided, returns tasks from all workspaces
the current user is a member of.

The page and its total come from one statement in the database —
``count(*) OVER ()`` rides on the rows' own query, so no separate
``SELECT COUNT(*)`` is issued. The order is ``created_at DESC, id DESC``,
which makes the paging deterministic. Every item's ``version_number`` is
resolved from **one** batched read of the page's distinct extraction ids —
never one lookup per card (decision D8).

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `extraction_id` | `query` | no | `string | null` |
| `page` | `query` | no | `integer` |
| `project_id` | `query` | no | `string | null` |
| `size` | `query` | no | `integer` |
| `user_story_id` | `query` | no | `string | null` |
| `workspace_id` | `query` | no | `string | null` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `PaginatedResponse_TaskResponse_` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/tasks/{task_id}`

Get Task

Get a task by its ID.

The user must be a member of the workspace that owns the task's user story project.
The response carries the version chip's data (decision D8): one batched
read resolves the task version's number.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `task_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `TaskResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `PUT` `/api/v1/tasks/{task_id}`

Update Task

Update an existing task.

The D5/D21 field matrix: ``status`` and ``labels`` are editable in every
version state; ``dependencies`` is only editable while the task's version
is the story's current one — a dependencies write on a frozen version is
refused with 409 ``TASK_VERSION_FROZEN``. For ``labels`` and
``dependencies`` on an editable task:
- ``None`` means keep existing values.
- ``[]`` means clear the list.

The response carries the version chip's data (decision D8) resolved from
the saved task: the board store merges this response into the card it
just moved, so a ``null`` ``version_number`` here would erase the chip on
drop.

The user must be a member of the workspace that owns the task's user story project.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `task_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `status` | `TaskStatus | null` | no |
| `labels` | `string[] | null` | no |
| `dependencies` | `string[] | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `TaskResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/tasks/{task_id}/invalidations`

List Invalidations

The task's full mark history, active mark first.

Membership-only: every member may read the record, the gate is on the
mutations. Revoked rows are part of the history and carry their
``revoked_by``/``revoked_at`` attribution.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `task_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `InvalidationResponse[]` |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/tasks/{task_id}/invalidations`

Create Invalidation

Mark the task invalid, with a reason, as the current user.

Gated to the workspace owner or an admin. A blank reason never reaches the
handler — ``CreateInvalidationRequest`` refuses it at body validation with
422 ``REQUEST_VALIDATION_FAILED``. The refusal order is the design's: the
frozen check first, then the active-mark read — resolved through
``find_active_by_task`` **before** any write, so a second active mark is a
designed 409 ``TASK_ALREADY_MARKED`` carrying the live mark's reason, and
the table's partial unique index stays the lost-race backstop it is, not
the contract. Revoking is the only way a mark stops being active.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `task_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `reason` | `string` | sí |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `201` | Successful Response | `InvalidationResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `DELETE` `/api/v1/tasks/{task_id}/invalidations/current`

Revoke Invalidation

Revoke the task's active mark — an UPDATE of the row, never a DELETE.

Gated to the workspace owner or an admin. The row that answers 404 is the
active mark ``find_active_by_task`` resolves: no active mark means nothing
to revoke. The row's reason, ``marked_by`` and ``marked_at`` stay intact —
the revoke history is the record.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `task_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `204` | Successful Response | — |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/tasks/{task_id}/invalidations/repetition`

Find Repetition

Warn on marks of the story's other versions whose title repeats this task's.

The D16 read, and deliberately nothing more: the title is resolved
server-side from the task id (the endpoint accepts no arbitrary text), the
SQL narrows to the story's other versions' active marks, and the match is
an exact comparison of ``normalize_task_title`` outputs — casefold plus
whitespace collapse. No fuzzy, no vector, no prefix, and no write: the read
creates, updates and revokes nothing.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `task_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `RepetitionResponse` |
| `422` | Validation Error | `HTTPValidationError` |

## users

### `GET` `/api/v1/users/me`

Get Me

Get the currently authenticated user's profile with workspace memberships.

Runs the three downstream repository queries **sequentially**. Previous
versions used ``asyncio.gather`` for concurrency, but SQLAlchemy async
sessions provisioning connections with ``pool_pre_ping`` race when the
three queries fire simultaneously on separate sessions, causing:
``InvalidRequestError: concurrent operations are not permitted``
(https://sqlalche.me/e/20/isce).

Each query pays a ~700ms round-trip to the remote Supabase pooler, so
the total wall time is roughly 3 × RTT regardless of concurrency.
Future work: use a single session for all three queries, or cache the
response (the user profile changes infrequently).

**Parámetros**

_Sin parámetros._

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `UserProfileResponse` |

### `PATCH` `/api/v1/users/me/onboarding`

Complete Onboarding

Mark onboarding as completed for the authenticated user.

Optionally renames the user's personal workspace if ``workspace_name``
is provided in the request body. Idempotent — calling this endpoint
multiple times returns 200 without error.

Args:
    payload: Optional body with ``workspace_name`` to rename the
        auto-created personal workspace. Defaults to empty (skip rename).

Returns:
    ``{ "success": true }`` on completion.

**Parámetros**

_Sin parámetros._

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `workspace_name` | `string | null` | no |
| `workspace_icon` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `map<string, any>` |
| `422` | Validation Error | `HTTPValidationError` |

## workspace-settings

### `GET` `/api/v1/workspaces/{workspace_id}/settings/llm`

Get Llm Config

Get the workspace LLM configuration.

Returns resolved config: workspace overrides merged on top of global
defaults. Admin only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `LLMConfigResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `PUT` `/api/v1/workspaces/{workspace_id}/settings/llm`

Upsert Llm Config

Upsert workspace LLM configuration.

Only the fields provided in the request body are updated. Returns the
resolved config after the update. Admin only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `provider` | `string | null` | no |
| `model` | `string | null` | no |
| `temperature` | `number | null` | no |
| `max_tokens` | `integer | null` | no |
| `base_url` | `string | null` | no |
| `api_key` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `LLMConfigResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/workspaces/{workspace_id}/settings/llm/models`

List Available Models

List available models from an LLM provider.

Proxies the request to the provider's model list API. The body optionally
carries the selection the settings form has in hand so the answer describes
the provider the user just picked; without one the saved workspace config is
probed, which is what keeps the persisted state observable.

``POST`` rather than ``GET`` with query parameters because the pending
selection carries an API key, and a query string writes it into access logs.
The sibling ``POST /llm/test`` in this module carries pending credentials the
same way.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

`LLMModelProbeRequest | null`

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `ModelInfo[]` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/settings/llm/status`

Get Llm Config Status

Report whether this workspace can extract, and what it is still missing.

Readable by any member, unlike every other route in this module. The member who
cannot read the configuration is exactly the one who meets the failed extraction,
so this is the one piece of it they are entitled to: the missing field names,
never the key or the endpoint those fields hold.

An unconfigured workspace resolves to Ollama, so its single gap is the model.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `LLMConfigStatusResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/workspaces/{workspace_id}/settings/llm/test`

Test Llm Connection

Test a connection to the specified LLM provider.

Sends a minimal prompt ("Hello") and returns the result.
Each of the four built-in providers constructs its own adapter (Ollama, Gemini, OpenAI,
or Anthropic) and returns the raw response or a connection error message. Any other name
is a workspace-registered custom provider, tested against its OpenAI-compatible endpoint
the same way ``_build_llm_port`` routes extraction.

The endpoint and the credential come from the request body — that is what a probe of
not-yet-saved values is — so the workspace gate in front of this handler is what keeps
that pair from being aimed at an arbitrary host by a caller with no stake here.
Admin only, like every other write route in this module.

On failure, the message names the provider and a classified reason only. The branch
catches a broad ``Exception`` rather than a transport-specific one, so a non-transport
failure is classified as "the provider could not be reached" — the classification is an
approximation, not an exact diagnosis. The detail that would tell the two apart is the
exception's own text, and that text is deliberately never echoed to the caller (it can
embed the request URL, and one provider historically put the API key in that URL); it
goes to the log at warning level instead, where an operator can read it and a caller
cannot.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `provider` | `string` | sí |
| `baseUrl` | `string | null` | no |
| `apiKey` | `string | null` | no |
| `model` | `string` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `LLMTestResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/settings/prompts`

Get Prompts

Get the workspace prompt configuration.

Returns resolved prompts: workspace overrides merged on top of global
defaults. Admin only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `PromptResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `PUT` `/api/v1/workspaces/{workspace_id}/settings/prompts`

Upsert Prompts

Upsert workspace prompt configuration.

Only the fields provided in the request body are updated. Returns the
resolved prompt config after the update. Admin only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `system_prompt` | `string | null` | no |
| `instruction_template` | `string | null` | no |
| `few_shot_enabled` | `boolean | null` | no |
| `few_shot_limit` | `integer | null` | no |
| `few_shot_threshold` | `number | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `PromptResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/settings/providers`

List Custom Providers

List the workspace's registered custom providers, ordered by name.

Scoped to the workspace: no other workspace's providers are reachable here.
Admin only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `CustomProviderResponse[]` |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/workspaces/{workspace_id}/settings/providers`

Create Custom Provider

Register a custom provider name for this workspace. Admin only.

The name is normalized by the request schema (trimmed, keeping its casing), so
surrounding whitespace cannot produce a second row for a name the workspace
already has.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `name` | `string` | sí |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `201` | Successful Response | `CustomProviderResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `PATCH` `/api/v1/workspaces/{workspace_id}/settings/providers/{provider_id}`

Rename Custom Provider

Rename a custom provider, and the selection that names it. Admin only.

The path declares the workspace, so containment is a different fact from
existence — the same rule ``routes/projects.py`` and ``routes/extraction.py``
follow: an absent id answers 404, and an id that exists but belongs to another
workspace answers 403, so the two are distinguishable. The earlier rationale —
reporting the foreign id as absent so it could not be probed for existence — was
replaced by this rule (issue #5, 2026-09-24), not refuted. Renaming the
provider this workspace has selected also rewrites the selection, so the two
cannot drift apart.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `provider_id` | `path` | sí | `string` |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `name` | `string` | sí |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `CustomProviderResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/settings/trello`

Get Trello Config

Get the workspace Trello credentials, decrypted. Admin only.

Returns ``null`` fields for a workspace that has not configured the pair yet.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `TrelloConfigResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `PUT` `/api/v1/workspaces/{workspace_id}/settings/trello`

Upsert Trello Config

Upsert workspace Trello credentials. Admin only.

Only the fields provided in the request body are updated. A blank credential is
stored as ``None`` — the repository's encrypt path would otherwise spend a token
storing a value that has to be decrypted back to nothing — and a value carried
over from the existing row is normalized too, so any save also cleans a legacy
blank. The repository encrypts on the way in; the response returns the decrypted
pair, the same convention as the LLM config module.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `api_key` | `string | null` | no |
| `token` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `TrelloConfigResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/settings/trello/status`

Get Trello Config Status

Report whether this workspace has Trello credentials, and which it is missing.

Readable by any member, unlike every other route in this module. The member who
cannot read the credentials is exactly the one who meets the failed export, so
this is the one piece of it they are entitled to: the missing field names, never
the values those fields hold.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `TrelloConfigStatusResponse` |
| `422` | Validation Error | `HTTPValidationError` |

## workspaces

### `GET` `/api/v1/workspaces/`

List Workspaces

List all workspaces the authenticated user is a member of.

**Parámetros**

_Sin parámetros._

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `WorkspaceListResponse` |

### `POST` `/api/v1/workspaces/`

Create Workspace

Create a new workspace.

The authenticated user becomes both admin and owner of the newly
created workspace.

**Parámetros**

_Sin parámetros._

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `name` | `string` | sí |
| `slug` | `string | null` | no |
| `icon` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `201` | Successful Response | `WorkspaceResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}`

Get Workspace

Get workspace details.

Uses ``get_workspace_for_user`` which returns 404 if the workspace
does not exist (no 403 — avoids leaking existence).

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `WorkspaceResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `PUT` `/api/v1/workspaces/{workspace_id}`

Update Workspace

Update workspace name and/or slug. Admin only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `name` | `string | null` | no |
| `slug` | `string | null` | no |
| `icon` | `string | null` | no |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `WorkspaceResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `DELETE` `/api/v1/workspaces/{workspace_id}`

Delete Workspace

Delete a workspace and all associated data. Admin only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `204` | Successful Response | — |
| `422` | Validation Error | `HTTPValidationError` |

### `GET` `/api/v1/workspaces/{workspace_id}/members`

List Members

List all members of a workspace. Admin only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `MemberListResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/workspaces/{workspace_id}/members`

Add Member

Add a user as a member of the workspace by email. Admin only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `user_email` | `string` | sí |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `201` | Successful Response | `MemberResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `PUT` `/api/v1/workspaces/{workspace_id}/members/{user_id}`

Update Member Role

Change a member's role. Admin only.

The workspace owner's role cannot be changed. Transfer ownership
first if you need to change the owner's role.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `user_id` | `path` | sí | `string` |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `role` | `string` | sí |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `MemberResponse` |
| `422` | Validation Error | `HTTPValidationError` |

### `DELETE` `/api/v1/workspaces/{workspace_id}/members/{user_id}`

Remove Member

Remove a member from the workspace. Admin only.

The workspace owner cannot be removed. An admin cannot remove
themselves if they are the last admin.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `user_id` | `path` | sí | `string` |
| `workspace_id` | `path` | sí | `string` |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `204` | Successful Response | — |
| `422` | Validation Error | `HTTPValidationError` |

### `POST` `/api/v1/workspaces/{workspace_id}/transfer`

Transfer Ownership

Transfer workspace ownership to another admin. Owner only.

**Parámetros**

| Nombre | Ubicación | Obligatorio | Tipo |
| --- | --- | --- | --- |
| `workspace_id` | `path` | sí | `string` |

**Cuerpo de la petición** (`application/json`)

| Campo | Tipo | Obligatorio |
| --- | --- | --- |
| `new_owner_id` | `string` | sí |

**Respuestas**

| Estado | Descripción | Esquema |
| --- | --- | --- |
| `200` | Successful Response | `map<string, any>` |
| `422` | Validation Error | `HTTPValidationError` |
