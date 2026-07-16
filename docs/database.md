# Base de Datos

> Schema, tablas, relaciones y migraciones de Storico.
> Última actualización: 2026-07-15

## Stack

- **Relacional**: PostgreSQL 16 (vía SQLAlchemy async + asyncpg)
- **Vectorial**: Qdrant (embeddings para RAG)
- **Migraciones**: Alembic (11 migraciones aplicadas)
- **Head**: `0011`

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
projects ──1:N── user_stories ──1:N── tasks
user_stories ──1:N── extractions
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

#### workspace_prompts

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| workspace_id | UUID | FK → workspaces.id (CASCADE), UNIQUE |
| system_prompt | Text | nullable |
| instruction_template | Text | nullable |
| few_shot_examples | JSONB | nullable |
| updated_at | DateTime(tz) | NOT NULL |

Uno por workspace.

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
| title | String(255) | NOT NULL |
| description | Text | default `""` |
| status | String(50) | default `"backlog"` |
| priority | String(20) | default `"medium"` |
| labels | JSON | nullable |
| dependencies | JSON | nullable |
| created_at | DateTime(tz) | NOT NULL |
| updated_at | DateTime(tz) | NOT NULL |

Index: `user_story_id`

#### extractions

| Columna | Tipo | Restricciones |
|---------|------|--------------|
| id | UUID | PK |
| user_story_id | UUID | FK → user_stories.id |
| model_used | String(100) | NOT NULL |
| status | String(20) | default `"pending"` |
| error_info | Text | nullable |
| prompt_config | JSON | nullable |
| raw_response | Text | NOT NULL |
| confidence_score | Float | nullable |
| created_at | DateTime(tz) | NOT NULL |

Index: `user_story_id`

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
| `3fefad99b84d` | Add avatar_url, CASCADE fixes | 2026-07-09 |
| `0004` | Account linking (user_accounts) | 2026-07-11 |
| `0005` | User preferences (JSONB) | 2026-07-11 |
| `0006` | Add status to user_stories | 2026-07-13 |
| `0007` | Workspaces + members + LLM config + prompts | 2026-07-13 |
| `0008` | Add is_first_login to users | 2026-07-15 |
| `0009` | Align schema drift | 2026-07-15 |
| `0010` | Reduce workspace name length 255→100 | 2026-07-15 |
| `0011` | Add api_key to workspace_llm_configs | 2026-07-15 |

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
