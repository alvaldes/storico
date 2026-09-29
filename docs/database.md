# Base de Datos

> Schema, tablas, relaciones y migraciones de Storico.
> Última actualización: 2026-09-29

## Stack

- **Relacional**: PostgreSQL 16 (vía SQLAlchemy async + asyncpg)
- **Vectorial**: Qdrant (embeddings para RAG)
- **Migraciones**: Alembic (28 revisiones)
- **Head**: `0028`

## Modelo de Datos

### Diagrama de Entidades

```
users ──1:N── user_accounts
users ──1:1── user_preferences
users ──1:N── workspace_members ──N:1── workspaces
users ──1:N── projects*
workspaces ──1:N── projects
workspaces ──1:1── workspace_prompts
workspaces ──1:1── workspace_llm_configs
workspaces ──1:N── custom_providers
projects ──1:N── user_stories ──1:N── tasks
user_stories ──1:N── extractions ──1:N── tasks
extractions ──1:N── task_invalidations
```

*\* `projects.created_by` referencia a `users.id` (nullable)*

### Tablas

#### users

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| email | String(255) | UNIQUE, NOT NULL |
| name | String(255) | NOT NULL |
| avatar_url | String(500) | nullable |
| is_first_login | Boolean | default `false` |
| created_at | DateTime(tz) | NOT NULL |

#### user_accounts

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| user_id | UUID | FK → users.id (CASCADE) |
| provider | String(50) | NOT NULL |
| provider_id | String(255) | NOT NULL |
| created_at | DateTime(tz) | NOT NULL |

UNIQUE: `(provider, provider_id)`

#### user_preferences

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| user_id | UUID | PK, FK → users.id (CASCADE) |
| preferences | JSONB | NOT NULL, default `{}` |
| updated_at | DateTime(tz) | NOT NULL |

Relación 1:1 con users.

#### workspaces

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| name | String(100) | NOT NULL |
| slug | String(100) | UNIQUE, NOT NULL |
| owner_id | UUID | FK → users.id (CASCADE) |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

#### workspace_members

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| workspace_id | UUID | FK → workspaces.id (CASCADE) |
| user_id | UUID | FK → users.id (CASCADE) |
| role | String(20) | NOT NULL ("admin" / "member") |
| created_at | DateTime(tz) | NOT NULL |

UNIQUE: `(workspace_id, user_id)`

#### workspace_llm_configs

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| workspace_id | UUID | FK → workspaces.id (CASCADE), UNIQUE |
| provider | String(50) | default `"ollama"` |
| model | String(100) | nullable |
| temperature | Float | nullable |
| max_tokens | Integer | nullable |
| base_url | String(500) | nullable |
| api_key | String(500) | nullable |
| updated_at | DateTime(tz) | NOT NULL |

Uno por workspace.

#### custom_providers

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| workspace_id | UUID | FK → workspaces.id (CASCADE), indexado |
| name | String(50) | NOT NULL |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

UNIQUE: `(workspace_id, name)`

Nombres de proveedores LLM que un workspace registró para endpoints que no son uno de
los cuatro proveedores integrados (`ollama`, `openai`, `anthropic`, `gemini`). A
diferencia de `workspace_prompts` y `workspace_llm_configs`, la relación es 1:N: el
mismo nombre puede existir en dos workspaces, pero no dos veces en el mismo. El nombre
es el valor que `workspace_llm_configs.provider` guarda y el que selecciona el adapter,
por lo que la migración `0021` registra una fila por cada config existente cuyo
`provider` no sea uno de los cuatro integrados. El modelo, la API Key y la URL Base
siguen viviendo en `workspace_llm_configs`.

#### workspace_prompts

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| workspace_id | UUID | FK → workspaces.id (CASCADE), UNIQUE |
| system_prompt | Text | nullable |
| instruction_template | Text | nullable |
| few_shot_enabled | Boolean | NOT NULL, default true |
| few_shot_limit | Integer | NOT NULL, default 3 |
| few_shot_threshold | Float | NOT NULL, default 0.85 |
| updated_at | DateTime(tz) | NOT NULL |

Uno por workspace. Los ejemplos few-shot viven como puntos en Qdrant y se
recuperan por workspace en el momento de la extracción; la columna legacy
`few_shot_examples` fue eliminada por la migración `0027`. Antes del drop se
midió que ninguna de las 14 filas tenía contenido; esa medición es previa y ya
no es reproducible. La columna solo la leía el job de seed, eliminado en el
mismo cambio.

> Nota: `few_shot_enabled`/`few_shot_limit`/`few_shot_threshold` los añadió la
> migración `0020` con `server_default` (`true`/`3`/`0.85`).

#### projects

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| name | String(255) | NOT NULL |
| description | Text | default `""` |
| workspace_id | UUID | FK → workspaces.id (CASCADE) |
| created_by | UUID | FK → users.id |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

#### user_stories

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| project_id | UUID | FK → projects.id |
| actor | Text | NOT NULL |
| feature | Text | NOT NULL |
| benefit | Text | NOT NULL |
| raw_text | Text | NOT NULL |
| created_at | DateTime(tz) | NOT NULL |
| status | String(20) | default `"pending"` |

Index: `project_id`

#### tasks

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| user_story_id | UUID | FK → user_stories.id |
| extraction_id | UUID | **NOT NULL** · FK → extractions.id (`ON DELETE CASCADE`) |
| title | String(255) | NOT NULL |
| description | Text | default `""` |
| status | String(50) | default `"backlog"` |
| priority | String(20) | default `"medium"` |
| labels | JSON | nullable |
| dependencies | JSON | nullable |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

Index: `user_story_id`, `ix_tasks_extraction_id`

`extraction_id` llega en `0028` y responde a una pregunta que `user_story_id` no puede contestar:
`user_story_id` sigue estando, y es la columna que hace que **todas** las versiones de una historia
sean visibles desde la historia; `extraction_id` es lo que separa las tareas de una corrida de las de
la siguiente. Ninguna tarea existe sin la corrida que la produjo.

#### extractions

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| user_story_id | UUID | FK → user_stories.id |
| version_number | Integer | **NOT NULL** · `ck_extractions_version_number_positive` (`> 0`) |
| model_used | String(100) | NOT NULL |
| provider | String(50) | **NOT NULL** |
| temperature | Float | **NOT NULL** |
| prompt_rendered | Text | nullable — no nulo exactamente cuando la corrida llegó a renderizar el prompt |
| status | String(20) | default `"pending"` |
| error_info | Text | nullable |
| prompt_config | JSON | nullable |
| raw_response | Text | NOT NULL |
| confidence_score | Float | nullable |
| created_at | DateTime(tz) | NOT NULL |
| completed_at | DateTime(tz) | nullable — no nulo exactamente cuando `status` es terminal. Las filas anteriores a la revisión `0023` quedan en `NULL`: no se rellenaron hacia atrás. |

Index: `user_story_id` · Unique: `uq_extractions_story_version` sobre `(user_story_id, version_number)`

Las cuatro columnas nuevas son el snapshot de la corrida y son **obligatorias** (`prompt_rendered`
no, y no puede serlo: una corrida que muere antes de renderizar no tiene prompt que congelar).
Hoy `prompt_rendered` está siempre en `NULL`: el método que lo escribe (`record_rendered_prompt`)
ya existe en el puerto y en el adaptador, pero nadie lo llama todavía — la escritura entre el render
y la llamada al proveedor es el trabajo de la siguiente unidad de este mismo slice. Congelar el
insumo de una versión fallida es el requisito; PR 1 pone la columna, la unidad que sigue pone la
escritura.

`version_number` se **deriva la vigente**, no se almacena: la vigente es la `version_number` más alta
con `status = 'completed'`. No hay flag, ni trigger, ni vista materializada — la derivación vive en
la lectura (`ORDER BY version_number DESC`, `status = 'completed'`, `LIMIT 1`). Toda corrida consume
un número, incluidas la que queda `pending` y la que falla: por eso el tablero no se vacía cuando
una extracción falla.

#### task_invalidations

La marca de "tarea inválida" es **una fila por evento**, no una columna en `tasks`: sólo una fila
puede guardar quién la retiró y cuándo.

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| task_id | UUID | NOT NULL · FK → tasks.id (`ON DELETE CASCADE`) |
| reason | String(500) | NOT NULL · `ck_task_invalidations_reason_not_blank` (`length(trim(reason)) > 0`) |
| marked_by | UUID | nullable · FK → users.id (`ON DELETE SET NULL`) |
| marked_at | DateTime(tz) | NOT NULL |
| revoked_by | UUID | nullable · FK → users.id (`ON DELETE SET NULL`) |
| revoked_at | DateTime(tz) | nullable · `ck_task_invalidations_revoke_pair` — `revoked_by` y `revoked_at` son nulos juntos o no lo son |

Index: `ix_task_invalidations_task_id` · Unique parcial: `uq_task_invalidations_active_task` sobre
`task_id` `WHERE revoked_at IS NULL` — a lo sumo una marca activa por tarea; retirar es un UPDATE,
nunca un DELETE. Las referencias a `users.id` sobreviven la baja de una cuenta (`SET NULL`).

La tabla existe desde `0028` y **todavía no la escribe nadie**: los endpoints de marca son el slice
(b). Su restricción de integridad ya es real, así que una marca duplicada o sin motivo queda rechazada
por la base de datos desde el primer día.

#### La migración `0028` no rellena hacia atrás

`0028` lee `SELECT count(*) FROM extractions` y `FROM tasks` **antes de cualquier DDL** y levanta un
error si alguna pareja no está vacía. No hay backfill: las extracciones históricas no tienen provider,
ni temperatura, ni número de versión real, y una columna `NOT NULL` con default inventado mentiría
mejor que un error. La limpieza de datos que la precede es una operación destructiva aparte, con su
propia confirmación, y es **precondición del deploy** que lleva `0028` — no es un paso de Alembic.

## Convenciones

- **IDs**: UUID v4 generados en la aplicación (no en la DB)
- **Timestamps**: `created_at`, `updated_at` con timezone
- **Soft delete**: No implementado — DELETE físico
- **JSON/JSONB**: Para campos dinámicos (`labels`, `dependencies`, `preferences`, `prompt_config`)
- **FK Naming**: `fk_{table}_{column}_{referred_table}`
- **Index Naming**: `ix_{table}_{column}`
- **Unique Naming**: `uq_{table}_{column}`

## Migraciones (Alembic)

| Rev | Descripción | Fecha |
|-----|------------|-------|
| `0001` | Schema inicial (users, projects, stories, tasks, extractions) | 2026-07-05 |
| `0002` | Add status + error_info to extractions | 2026-07-06 |
| `0003` | Add avatar_url, CASCADE fixes | 2026-07-09 |
| `0004` | Account linking (user_accounts) | 2026-07-11 |
| `0005` | User preferences (JSONB) | 2026-07-11 |
| `0006` | Add status to user_stories | 2026-07-13 |
| `0007` | Workspaces + members + LLM config + prompts | 2026-07-13 |
| `0008` | Add is_first_login to users | 2026-07-15 |
| `0009` | Align schema drift | 2026-07-15 |
| `0010` | Reduce workspace name length 255→100 | 2026-07-15 |
| `0011` | Add api_key to workspace_llm_configs | 2026-07-15 |
| `0012` | Add icon to workspaces | 2026-07-16 |
| `0013` | Add icon to projects | 2026-07-16 |
| `0014` | CASCADE / SET NULL fixes for account deletion | 2026-07-17 |
| `0015` | UUID v7 switchover marker (no DDL) | 2026-07-23 |
| `0016` | UserStoryStatus + TaskStatus enums with data migration | 2026-09-05 |
| `0017` | Add user_story_status to extractions | 2026-09-07 |
| `0018` | Add extraction_status enum | 2026-09-08 |
| `0019` | Add updated_at to user_stories | 2026-09-12 |
| `0020` | Add few-shot retrieval config to workspace_prompts | 2026-09-14 |
| `0021` | Add custom_providers table + backfill | 2026-09-17 |
| `0022` | Drop the per-user llm block from stored preferences | 2026-09-18 |
| `0023` | Add completed_at to extractions | 2026-09-19 |
| `0024` | Encrypt workspace LLM API keys | 2026-09-19 |
| `0025` | Convert extractions.status to the extraction_status_new enum | 2026-09-21 |
| `0026` | Drop the duplicate index on tasks.user_story_id | 2026-09-21 |
| `0027` | Drop the legacy `workspace_prompts.few_shot_examples` column | 2026-09-24 |
| `0028` | Extraction versioning: `version_number`, `provider`, `temperature`, `prompt_rendered`, `tasks.extraction_id`, `task_invalidations` | 2026-09-29 |

Comandos útiles:

```bash
# Crear nueva migración
cd backend
alembic revision --autogenerate -m "description"

# Aplicar migraciones
alembic upgrade head

# Revertir una
alembic downgrade -1

# Ver historial
alembic history
```

## Qdrant (Vector Store)

- **Colección**: Extracciones con embeddings
- **Vector size**: 768 (Ollama `nomic-embed-text`)
- **Distance**: Cosine
- **Propósito**: RAG — contexto histórico para nuevas extracciones
- **Uso**: Antes de llamar al LLM, se busca similitud > 0.85 en Qdrant y se incluyen resultados como ejemplos few-shot en el prompt
