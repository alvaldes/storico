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

`GET` y `PUT /settings/llm` requieren admin. `GET /settings/llm/status` es la excepción
legible por cualquier miembro: responde `{configured, provider, missing}` con los
**nombres de los campos** que faltan (`model`, `api_key`, `base_url`) y nunca con la
credencial ni el endpoint, porque el miembro que no puede leer la configuración es
justamente quien choca con la extracción que depende de ella. Un workspace sin fila
resuelve a `ollama`, cuyo único requisito es el modelo.

La regla de completitud vive una sola vez, en
`storico/domain/services/llm_config_readiness.py`: `ollama` necesita `model`;
`openai`, `anthropic` y `gemini` necesitan `model` y `api_key`; cualquier otro nombre
es un proveedor personalizado compatible con OpenAI y necesita `model` y `base_url`
(la `api_key` queda opcional). `POST /workspaces/{wsId}/extract/` aplica esa misma
regla **antes** de crear la extracción y responde `400` con
`error_code: "LLM_CONFIG_INCOMPLETE"` y la lista `missing`.

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/workspaces/{wsId}/settings/llm` | Obtener config LLM |
| PUT | `/api/v1/workspaces/{wsId}/settings/llm` | Actualizar config LLM |
| GET | `/api/v1/workspaces/{wsId}/settings/llm/status` | ¿Está completa la config LLM? |
| POST | `/api/v1/workspaces/{wsId}/settings/llm/models` | Modelos disponibles del proveedor |
| POST | `/api/v1/llm/test` | Test de conexión LLM |

`POST /settings/llm/models` acepta un body opcional con la selección que el formulario
tiene en pantalla (`provider`, `base_url`, `api_key`), para que la respuesta describa el
proveedor **elegido** y no el que ya estaba guardado. Un body que nombra un proveedor
describe esa consulta por completo: una `api_key` o `base_url` omitida queda *ausente*
para esa consulta y nunca se toma de la fila guardada —tomarla enviaría la credencial de
un proveedor al endpoint de otro—. Sin body (o sin `provider`) se responde por la config
guardada del workspace. Es `POST` y no `GET` con query string porque la selección puede
llevar una API Key, y una query string la escribe en los logs de acceso; `POST
/api/v1/llm/test` transporta credenciales pendientes de la misma forma. Requiere admin.

### Proveedores personalizados (scoped a workspace)

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/workspaces/{wsId}/settings/providers` | Listar proveedores personalizados |
| POST | `/api/v1/workspaces/{wsId}/settings/providers` | Registrar un proveedor personalizado |
| PATCH | `/api/v1/workspaces/{wsId}/settings/providers/{providerId}` | Renombrar un proveedor personalizado |

Todos requieren rol admin. El nombre se normaliza (recorte y minúsculas) y se valida
contra `^[a-z0-9][a-z0-9._-]{0,49}$`; un nombre de proveedor integrado o ya registrado
en el mismo workspace responde `409`, y un `providerId` de otro workspace responde
`404`. Al renombrar el proveedor que el workspace tiene seleccionado, también se
actualiza `workspace_llm_configs.provider`.

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
