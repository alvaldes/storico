# API Reference

> Documentación de la API REST de Storico.
> La especificación OpenAPI completa está disponible en `/docs` (Swagger UI) cuando el backend está corriendo.

## Base URL

```
Desarrollo: http://localhost:8000
Producción: https://storico-api.vercel.app (tentativo)
```

Autenticación vía header `Authorization: Bearer <token>`. El token se obtiene automáticamente vía Auth.js.

## Endpoints

### Health

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/health` | Health check del servicio |

### Workspaces

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/workspaces` | Listar workspaces |
| POST | `/api/v1/workspaces` | Crear workspace |
| GET | `/api/v1/workspaces/{id}` | Obtener workspace |
| PUT | `/api/v1/workspaces/{id}` | Actualizar workspace |
| DELETE | `/api/v1/workspaces/{id}` | Eliminar workspace |
| GET | `/api/v1/workspaces/{id}/members` | Listar miembros |
| POST | `/api/v1/workspaces/{id}/members` | Agregar miembro |
| PUT | `/api/v1/workspaces/{id}/members/{userId}` | Cambiar rol |
| DELETE | `/api/v1/workspaces/{id}/members/{userId}` | Remover miembro |
| POST | `/api/v1/workspaces/{id}/transfer` | Transferir ownership |

### Projects (scoped a workspace)

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/workspaces/{wsId}/projects` | Listar proyectos (paginado) |
| POST | `/api/v1/workspaces/{wsId}/projects` | Crear proyecto |
| GET | `/api/v1/workspaces/{wsId}/projects/{id}` | Obtener proyecto |
| PUT | `/api/v1/workspaces/{wsId}/projects/{id}` | Actualizar proyecto |
| DELETE | `/api/v1/workspaces/{wsId}/projects/{id}` | Eliminar proyecto |

### User Stories

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/stories` | Listar stories (filtro `?project_id=`) |
| POST | `/api/v1/stories` | Crear story |
| GET | `/api/v1/stories/{id}` | Obtener story |
| PUT | `/api/v1/stories/{id}` | Actualizar story |
| DELETE | `/api/v1/stories/{id}` | Eliminar story |

### Tasks

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/tasks` | Listar tasks (filtro `?user_story_id=`) |
| POST | `/api/v1/tasks` | Crear task |
| GET | `/api/v1/tasks/{id}` | Obtener task |
| PUT | `/api/v1/tasks/{id}` | Actualizar task |
| DELETE | `/api/v1/tasks/{id}` | Eliminar task |

### Extraction

| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/extract` | Extraer tareas de una user story |
| GET | `/api/v1/extractions` | Listar extracciones |
| GET | `/api/v1/extractions/{id}` | Obtener extracción |

### Users

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/users/me` | Perfil del usuario actual |
| GET | `/api/v1/users/me/settings` | Configuración del usuario |
| PUT | `/api/v1/users/me/settings` | Guardar configuración |
| POST | `/api/v1/users/me/onboarding` | Completar onboarding |

### LLM Config (scoped a workspace)

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/workspaces/{wsId}/settings/llm` | Obtener config LLM |
| PUT | `/api/v1/workspaces/{wsId}/settings/llm` | Actualizar config LLM |
| GET | `/api/v1/workspaces/{wsId}/settings/llm/models` | Modelos disponibles |
| POST | `/api/v1/llm/test` | Test de conexión LLM |

### Prompts (scoped a workspace)

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/workspaces/{wsId}/settings/prompts` | Obtener prompts |
| PUT | `/api/v1/workspaces/{wsId}/settings/prompts` | Actualizar prompts |

## Formatos de Respuesta

### Éxito

```json
{
  "id": "uuid",
  "name": "Project name",
  "created_at": "2026-07-15T12:00:00Z",
  "updated_at": "2026-07-15T12:00:00Z"
}
```

### Listas paginadas

```json
{
  "items": [...],
  "total": 42,
  "page": 1
}
```

### Errores

```json
{
  "detail": "Project with id '...' not found",
  "type": "entity_not_found"
}
```

| Tipo | HTTP Status |
|------|-------------|
| `entity_not_found` | 404 |
| `duplicate_entity` | 409 |
| `repository_error` | 500 |
| `internal_error` | 500 |

### Extracción

```json
POST /api/v1/extract
{
  "user_story_id": "uuid",
  "raw_text": "As a user, I want..."
}

Response 201:
{
  "tasks": [
    {
      "title": "Implement login form",
      "description": "Create a login form with email and password fields",
      "labels": ["frontend", "auth"],
      "status": "backlog",
      "priority": "high"
    }
  ]
}
```

## Especificaciones Completas

Para el detalle fino de cada endpoint (schemas, escenarios, edge cases), ver:
- [`docs/api/spec-api-endpoints.md`](api/spec-api-endpoints.md) — Spec original de endpoints
- [`docs/api/spec-tasks-api-endpoints.md`](api/spec-tasks-api-endpoints.md) — Desglose de tareas de implementación
