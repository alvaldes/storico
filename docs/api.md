# API Reference

> Documentación de la API REST de Storico.
> La especificación OpenAPI completa está disponible en `/docs` (Swagger UI) cuando el backend está corriendo.

## Base URL

```
Desarrollo: http://localhost:8000
Producción: https://storico-api.163.192.150.75.sslip.io (el contenedor en la VM)
```

El proyecto de Vercel `storico-api` también construye y deploya en cada push, pero **no** es el endpoint
en uso: producción corre en el contenedor de la VM (ver [deployment.md](deployment.md)).

Autenticación vía header `Authorization: Bearer <token>`. El token se obtiene automáticamente vía Auth.js.

## Endpoints

Las rutas de colección terminan en `/` — es la forma canónica que expone FastAPI, y
pedirlas sin la barra responde un redirect `307`. Las tablas de abajo usan la forma
canónica.

### Health

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check: base de datos (la única dependencia requerida) |
| GET | `/api/v1/health/services` | Diagnóstico completo: base de datos, Ollama y Qdrant |

### Workspaces

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/workspaces/` | Listar workspaces |
| POST | `/api/v1/workspaces/` | Crear workspace |
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
| GET | `/api/v1/workspaces/{wsId}/projects/` | Listar proyectos (paginado) |
| POST | `/api/v1/workspaces/{wsId}/projects/` | Crear proyecto |
| GET | `/api/v1/workspaces/{wsId}/projects/{id}` | Obtener proyecto |
| PUT | `/api/v1/workspaces/{wsId}/projects/{id}` | Actualizar proyecto |
| DELETE | `/api/v1/workspaces/{wsId}/projects/{id}` | Eliminar proyecto |

### User Stories

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/stories/` | Listar stories (filtro `?project_id=`) |
| POST | `/api/v1/stories/` | Crear story |
| GET | `/api/v1/stories/{id}` | Obtener story |
| PUT | `/api/v1/stories/{id}` | Actualizar story |
| DELETE | `/api/v1/stories/{id}` | Eliminar story |

### Tasks

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/tasks/` | Listar tasks (filtro `?user_story_id=`) |
| POST | `/api/v1/tasks/` | Crear task |
| GET | `/api/v1/tasks/{id}` | Obtener task |
| PUT | `/api/v1/tasks/{id}` | Actualizar task |
| DELETE | `/api/v1/tasks/{id}` | Eliminar task |

### Extraction

| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/workspaces/{wsId}/extract/` | Iniciar la extracción (asíncrona: responde `202`) |
| GET | `/api/v1/workspaces/{wsId}/extract/status/{extractionId}` | Estado de una extracción de ese workspace |
| GET | `/api/v1/extractions/` | Listar extracciones (filtros `?user_story_id=`, `?workspace_id=`) |
| GET | `/api/v1/extractions/{id}` | Obtener una extracción |

`POST /api/v1/extract` (sin workspace) ya no existe: el router legacy responde `410 Gone`
en `/api/v1/extract/` y en cualquiera de sus subrutas — la forma sin barra redirige ahí,
como toda ruta de colección. La única ruta vigente es la workspace-scoped.

### Users

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/users/me` | Perfil del usuario actual |
| GET | `/api/v1/users/me/settings` | Configuración del usuario |
| PUT | `/api/v1/users/me/settings` | Guardar configuración |
| PATCH | `/api/v1/users/me/onboarding` | Completar onboarding (opcionalmente renombra el workspace) |

`/users/me/settings` transporta **una sola preferencia**: `preferences.export.defaultFormat`
(`json` o `markdown`). No lleva configuración de LLM ni credencial alguna. Antes
declaraba un bloque `llm` con un `model`/`api_key`/`base_url` por proveedor que nada leía —la
configuración viva es por **workspace**— y la revisión `0022` removió esa clave de lo guardado.
`PUT` rechaza con `422` un body que traiga `llm` (el schema usa `extra="forbid"`), y `GET`
tolera una fila heredada que todavía lo tenga: descarta esa clave y responde el resto.

`trello` era un valor seleccionable que la exportación del workspace siempre respondía con
`400` (`GET /api/v1/workspaces/{wsId}/export/tasks?format=trello`), así que también queda
retirado: el `Literal` se angostó a `json` y `markdown`. Un valor retirado no se puede
descartar como una clave —`extra="forbid"` nunca ve un valor y sólo rechaza miembros que el
modelo no declara, así que un `trello` guardado llega al `Literal` y lo falla—; por eso `GET`
normaliza un `trello` guardado a `json` en vez de fallar (sin esa normalización la fila
heredada sería un `500`), `PUT` lo rechaza con `422`, y la normalización no se escribe de
vuelta, así que el almacenamiento conserva lo que tenía.

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

Todos requieren rol admin. El nombre se recorta y se guarda **tal como se escribe**: de 1
a 50 caracteres después del recorte, cualquier carácter permitido (mayúsculas, espacios,
acentos), y `Groq` y `groq` son dos proveedores distintos. Responde `409` si el nombre ya
existe en el workspace, si es uno de los cuatro proveedores integrados (en cualquier
combinación de mayúsculas) o si es el valor reservado del selector
(`__add_custom_provider__`); un `providerId` de otro workspace responde `404`. Al renombrar
el proveedor que el workspace tiene seleccionado, también se actualiza
`workspace_llm_configs.provider`.

Una excepción a los `409`: renombrar una fila **a su propio nombre** responde `200` sin
cambiar nada, y esa comprobación corre antes que la de nombres reservados y que la de
duplicados. Es lo que permite que una fila heredada llamada `Ollama` —creada por la
migración `0021`, cuando el registro permitía ese nombre— reenvíe su propio nombre sin
chocar contra la regla que ahora lo reserva.

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

**Contrato de existencia (404 vs 403).** En los recursos con alcance de workspace la regla es
explícita: **404** cuando la fila no existe, **403** cuando existe pero no es alcanzable para quien
consulta (membresía o contención). Está implementada y razonada en
`backend/src/storico/api/routes/projects.py:95-101` y
`backend/src/storico/api/routes/extraction.py:134-139`: la existencia y la contención son hechos
distintos y se reportan distinto. Eso implica que un id de otro workspace se puede distinguir de un
id inexistente. Es un comportamiento **elegido**, no una inconsistencia por arreglar — el mismo
trade-off que ya aplicaba `extraction.py` —: unificarlo al revés, 404 para todo, sería una decisión
de contrato de API, no un fix, porque cambiaría códigos que el cliente ya recibe y que hoy nadie
ramifica.

La excepción es el proveedor propio: `backend/src/storico/api/routes/workspace_settings.py:356-358`
responde **404** cuando el `providerId` pertenece a otro workspace, así que ahí ese id **no** se
distingue de uno inexistente (el mensaje es "Custom provider not found"). El backlog retirado
afirmaba que la regla era uniforme en todo el backend; medido el 2026-09-23 no lo es para esa ruta.
Alinear la excepción o mantenerla es una decisión de contrato de API, y no forma parte de este
retiro.

### Extracción

```http
POST /api/v1/workspaces/{wsId}/extract/
Content-Type: application/json

{
  "user_story_id": "uuid",
  "model": null,
  "temperature": null,
  "run_validation": false
}
```

Responde **`202 Accepted`** de inmediato: la extracción corre en segundo plano y el cliente
consulta su estado hasta que pasa a `completed` o `failed`.

```json
{
  "extraction_id": "uuid",
  "status": "pending",
  "user_story_id": "uuid",
  "message": "Extraction started. Poll GET /extractions/{extraction_id} for progress."
}
```

Si la configuración del LLM del workspace está incompleta para el proveedor elegido, la
ruta responde `400` con `error_code: "LLM_CONFIG_INCOMPLETE"` y la lista `missing`, **sin
crear ninguna extracción**.

```http
GET /api/v1/workspaces/{wsId}/extract/status/{extractionId}
```

```json
{
  "id": "uuid",
  "user_story_id": "uuid",
  "model_used": "llama3.2",
  "status": "completed",
  "user_story_status": "extracted",
  "error_info": null,
  "prompt_config": { "validate": false, "temperature": null },
  "raw_response": "1. summary: Set up the database schema\ndescription: Create the tables...",
  "confidence_score": null,
  "created_at": "2026-07-15T12:00:00Z",
  "completed_at": "2026-07-15T12:00:04Z",
  "tasks": []
}
```

`completed_at` registra cuándo terminó la extracción: viaja con la hora real cuando el
`status` es `completed` o `failed`, y en `null` mientras siga en `pending`. Las extracciones
anteriores a la revisión `0023` también viajan en `null`, porque **no se rellenaron hacia
atrás**: su hora de fin nunca se registró, y tanto copiar `created_at` como usar la hora del
despliegue habría inventado un dato.

Las tareas generadas no viajan en la respuesta de estado: se leen con
`GET /api/v1/tasks/?user_story_id=...` una vez que la extracción pasó a `completed`.

## Especificaciones Completas

Para el detalle fino de cada endpoint (schemas, escenarios, edge cases), ver:
- [`docs/api/spec-api-endpoints.md`](api/spec-api-endpoints.md) — Spec original de endpoints
- [`docs/api/spec-tasks-api-endpoints.md`](api/spec-tasks-api-endpoints.md) — Desglose de tareas de implementación
