# API Reference

> Documentación de la API REST de Storico.
> La especificación OpenAPI completa está disponible en `/docs` (Swagger UI) cuando el backend está corriendo.

## Base URL

```
Desarrollo: http://localhost:8000
Producción: https://storico-api.163.192.150.75.sslip.io (el contenedor en la VM)
```

El proyecto de Vercel `storico-api`, que construía y deployaba en cada push, se **borró el 2026-09-25**:
nunca fue el endpoint en uso. Producción corre en el contenedor de la VM
(ver [deployment.md](deployment.md)).

Autenticación vía header `Authorization: Bearer <token>`. El token se obtiene automáticamente vía Auth.js.

## Endpoints

Las rutas de colección terminan en `/` — es la forma canónica que expone FastAPI, y
pedirlas sin la barra responde un redirect `307`. Las tablas de abajo usan la forma
canónica.

### Health

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/health` | Health check: base de datos (la única dependencia requerida) |
| GET | `/api/v1/health/services` | Diagnóstico completo: cinco probes (`database`, `schema`, `ollama`, `qdrant`, `embeddings`), cada uno con su `scope` |

`/api/v1/health/services` clasifica cada probe con un campo `scope`: `required` (el
deployment no es útil sin él: `database` y `schema`) u `optional` (una integración que
un workspace puede no usar nunca: `ollama`, `qdrant`, `embeddings`, cuya falla degrada
una función, no el servicio). El `status` superior se calcula solo con los probes
requeridos, de modo que una integración opcional inalcanzable no pinta el deployment
como degradado.

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

Solo el dueño del workspace o un usuario con rol `ADMIN` puede eliminar una story; un `MEMBER`
recibe `403 WORKSPACE_OWNER_OR_ADMIN_REQUIRED`. La eliminación es una sola operación: si hay un
vector store configurado, primero quita de él los puntos de la story; después borra la story y
escribe, en una misma transacción, un registro de auditoría con los números de versión que
destruyó. Si el vector store no responde, la operación se aborta con
`503 VECTOR_STORE_UNAVAILABLE` y la story, sus versiones y sus tareas quedan intactas para
reintentar.

### Import de user stories (scoped a workspace)

| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/workspaces/{wsId}/stories/import` | Importar historias desde un CSV (`multipart/form-data`: `project_id` y `file`) |

El archivo se valida **completo antes de escribir nada**. Con al menos una fila con error responde
`422` con `error_code: "IMPORT_VALIDATION_FAILED"`, `created: 0` y el detalle por línea, y **no se
crea ninguna historia**: no existe el estado a medias. Las filas que duplican una historia ya
existente —o una fila anterior del mismo archivo— se **omiten y se reportan**, nunca bloquean, así
que volver a subir el mismo archivo es idempotente (`201` con `created: 0`). Como el `project_id`
viaja en el cuerpo, el proyecto se verifica contra el workspace del path: un proyecto de otro
workspace responde `403`.

Topes: **2 MB** y **1000 filas**. Formato: encabezado autodetectado, `actor,feature,benefit` (con
`raw_text` opcional) o una sola columna `story` / `input` / `raw_text`; delimitador leído del
encabezado; UTF-8 con BOM tolerado.

```json
{
  "detail": {
    "detail": "The file has rows that must be fixed.",
    "created": 0,
    "total_rows": 44,
    "errors": [
      { "line": 7,  "reason": "missing_field", "field": "feature" },
      { "line": 19, "reason": "too_long", "field": "benefit", "length": 340, "max": 300 },
      { "line": 31, "reason": "field_count_mismatch", "observed": 4, "expected": 3 },
      { "line": 40, "reason": "parts_look_like_a_full_story" }
    ],
    "duplicates": [
      { "line": 88, "reason": "duplicate", "existing_story_id": "..." },
      { "line": 91, "reason": "duplicate_in_file", "first_line": 12 }
    ]
  },
  "error_code": "IMPORT_VALIDATION_FAILED"
}
```

Estos tres códigos siguen el sobre canónico descrito en §Errores: `error_code` viaja
siempre al **nivel superior** del cuerpo y la carga estructurada (los campos de la
tabla siguiente) vive **dentro** de `detail`, junto al texto legible.

| `error_code` | HTTP | Campos (dentro de `detail`) |
|--------------|------|--------|
| `IMPORT_VALIDATION_FAILED` | 422 | `created`, `total_rows`, `errors[]`, `duplicates[]` |
| `IMPORT_FILE_REJECTED` | 422 | `reason`: `invalid_encoding`, `header_unrecognized`, `too_many_rows`, `malformed_csv`, `empty_file` |
| `IMPORT_FILE_TOO_LARGE` | 413 | `size`, `max` |

Razones bloqueantes de una fila: `missing_field`, `empty_field`, `too_long`, `unparsable_story`,
`field_count_mismatch`, `parts_look_like_a_full_story`. Los duplicados no son errores: viajan en
`duplicates` con `reason` `duplicate` (más `existing_story_id`) o `duplicate_in_file` (más
`first_line`).

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

### Exportación de archivos (scoped a workspace)

`GET /api/v1/workspaces/{wsId}/export/tasks` serializa tareas a un archivo
adjunto (`Content-Disposition`). Tres formatos, con `?format=`:

| `format` | Cuerpo | Filename |
|--------|------|--------|
| `json` (default) | Array JSON de tareas | `tasks-export-{wsId}.json` |
| `markdown` | Documento con una sección por historia | `tasks-export-{wsId}.md` |
| `csv` | Una fila por tarea (ver contrato de columnas) | `tasks-export-{wsId}.csv` |

Cualquier otro valor responde `400 UNSUPPORTED_EXPORT_FORMAT`.

**Alcance — un target, nunca dos.** Los query parameters `project_id` y
`user_story_id` estrechan la exportación al proyecto o a la historia nombrada;
sin targets exporta todo el workspace. Es la misma regla que resuelve el
disparo de Trello (`resolve_export_scope`, en
`domain/services/export_scope.py`): los dos targets a la vez responden `422
REQUEST_VALIDATION_FAILED`. Un target debe existir y pertenecer al workspace
del path: uno de otro workspace responde `403`, uno inexistente `404`.

**Versión.** Sin `extraction_id`, se exporta la versión actual de cada
historia (la de número más alto entre las corridas `completed`) — el filtro
viaja en la propia sentencia de lectura, así que las tareas de una versión
sustituida nunca se cuelan en el archivo. Con `extraction_id` **y**
`user_story_id`, se exportan las tareas de esa versión aunque una corrida
posterior la haya sustituido — la versión se nombra por su id de extracción,
nunca por su número de versión, que es una posición en una historia que la
siguiente corrida mueve. Un `extraction_id` sin `user_story_id` responde `422`:
una versión pertenece a una historia, y una versión pedida a nivel de proyecto
o de workspace es una pregunta sin respuesta.

**Vista previa.** `?preview=true` devuelve exactamente el mismo cuerpo —el mismo
endpoint, los mismos parámetros, un solo camino de código— pero **sin** el header
`Content-Disposition`, así que el navegador lo muestra en vez de guardarlo. Una
serialización, dos disposiciones: lo que una vista previa muestra no puede
diferir de lo que la descarga guarda, porque son los mismos bytes.

**Contrato de columnas CSV.** Una fila por tarea, con las columnas en este
orden exacto:

```
story, version, title, description, status, priority, labels, dependencies
```

`story` es el texto crudo de la historia y `version` el número de versión de
la corrida que produjo la tarea. Las celdas multivalor (`labels`,
`dependencies`) van unidas con `;`. El archivo se escribe con el módulo `csv`
de Python, así que una descripción con saltos de línea o comas viaja
entrecomillada y sobrevive al round trip. El orden de columnas es un
contrato, no una elección: un archivo que la gente parsea deja de ser libre
de reordenarse — agregar una columna después es compatible; renombrar o
reordenar una, no.

### Exportación a Trello (scoped a workspace)

La exportación a Trello es asíncrona como la extracción (D5): `POST` crea un job
persistido en `trello_exports`, despacha el trabajo con `asyncio.create_task` en el
proceso de la API y responde `202` de inmediato. El cliente consulta `GET` hasta que
el job llega a `completed` (con la URL del tablero) o `failed` (con su `error_code`, y
con `board_url` también cuando el tablero quedó a medias — un fallo posterior a la
creación carga el `board_ref`, así que la mitad construida nunca se esconde).

El alcance es uno de tres, nunca dos (D1): sin targets exporta todo el workspace; con
`project_id` o `user_story_id` exporta ese proyecto o esa historia; con los dos a la
vez responde `422 REQUEST_VALIDATION_FAILED` — la regla que la cascada del Kanban ya
aplica. Solo se exporta la versión actual de cada historia (D8), el mismo filtro que
usa la exportación de archivos.

**Cualquier miembro puede disparar** (D7): lo admin-only son las credenciales
(`/settings/trello`), no la exportación, que lee las mismas tareas que
`GET .../export/tasks` ya deja leer a cualquier miembro. Un workspace sin el par
de credenciales guardado responde `409 TRELLO_CREDENTIALS_MISSING` antes de crear
nada — conflicto de estado, no request malformado, y nunca un `500`.

En cada exportación se crea un tablero nuevo (D3): repetir no sobrescribe, y los
duplicados son aceptados. El tablero tiene las cinco columnas Kanban siempre, en
orden canónico, aunque queden vacías.

**La vista previa del tablero.** `GET /api/v1/workspaces/{wsId}/export/trello/preview`
devuelve el plan del tablero que el disparador enviaría, como JSON: el nombre del
tablero, sus listas en orden Kanban, y cada tarjeta con su título, descripción,
etiquetas y títulos de dependencias ya resueltos. Es el mismo `TrelloBoardPlan`
que construye el runner, por el mismo punto de entrada de la capa de aplicación,
así que la vista previa solo puede mostrar lo que la exportación crearía.

**Describe, no ejecuta.** No escribe ninguna fila en `trello_exports` y nunca lee
las credenciales de Trello del workspace: describir lo que se exportaría no
requiere permiso para crearlo, así que un workspace sin credenciales responde la
vista previa, no `409`. Toma los mismos parámetros de alcance que el disparador,
con las mismas negativas: dos targets `422`, uno de otro workspace `403`, uno
inexistente `404`. La dimensión de versión para Trello llegará después y se
sumará aquí como parámetro que exija `user_story_id` — el emparejamiento que la
exportación de archivos ya aplica.

| Método | Path | Descripción |
|--------|------|-------------|
| POST | `/api/v1/workspaces/{wsId}/export/trello` | Iniciar la exportación a un tablero nuevo (asíncrona: responde `202` con el job) |
| GET | `/api/v1/workspaces/{wsId}/export/trello/preview` | El plan del tablero como JSON: nombre, listas en orden Kanban, tarjetas con etiquetas y dependencias. No crea nada y no pide credenciales |
| GET | `/api/v1/workspaces/{wsId}/export/trello/{exportId}` | Estado del job: `status`, `board_url`, `error_code`, `cards_created` |

Códigos de la familia: `TRELLO_CREDENTIALS_MISSING` (409, sin credenciales),
`TRELLO_EXPORT_NOT_FOUND` (404, job inexistente o de otro workspace), y en el job
fallido `TRELLO_CREDENTIAL_REJECTED`, `TRELLO_SERVICE_UNAVAILABLE`,
`TRELLO_RATE_LIMIT_EXHAUSTED`, `TRELLO_BOARD_REFUSED`, `TRELLO_CARD_REFUSED` — un
código por miembro de la familia tipada `TrelloExportError` — más
`TRELLO_EXPORT_INTERRUPTED`, que no es de la familia tipada: lo escriben el runner
ante una cancelación y el **sweep de arranque**
(`infrastructure/tasks/trello_export_task.py`), que marca en el inicio todo job
`pending` o `running` más viejo que su cota de edad como `failed` con ese código,
para que un job abandonado por un crash responda en vez de dejar al miembro
esperando para siempre. Hereda la limitación del sweep de extracciones: un job
más joven que la cota en el momento del arranque espera al siguiente.

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
regla **antes** de crear la extracción y responde `400` con `error_code:
"LLM_CONFIG_INCOMPLETE"` a nivel superior del cuerpo y la lista `missing` dentro de
`detail` (el sobre canónico de §Errores).

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/workspaces/{wsId}/settings/llm` | Obtener config LLM |
| PUT | `/api/v1/workspaces/{wsId}/settings/llm` | Actualizar config LLM |
| GET | `/api/v1/workspaces/{wsId}/settings/llm/status` | ¿Está completa la config LLM? |
| POST | `/api/v1/workspaces/{wsId}/settings/llm/models` | Modelos disponibles del proveedor |
| POST | `/api/v1/workspaces/{wsId}/settings/llm/test` | Test de conexión LLM |

`POST /settings/llm/models` acepta un body opcional con la selección que el formulario
tiene en pantalla (`provider`, `base_url`, `api_key`), para que la respuesta describa el
proveedor **elegido** y no el que ya estaba guardado. Un body que nombra un proveedor
describe esa consulta por completo: una `api_key` o `base_url` omitida queda *ausente*
para esa consulta y nunca se toma de la fila guardada —tomarla enviaría la credencial de
un proveedor al endpoint de otro—. Sin body (o sin `provider`) se responde por la config
guardada del workspace. Es `POST` y no `GET` con query string porque la selección puede
llevar una API Key, y una query string la escribe en los logs de acceso; `POST
/api/v1/workspaces/{wsId}/settings/llm/test` transporta credenciales pendientes de la
misma forma. Como toda escritura del módulo de settings, depende de `require_admin`:
exige pertenencia al workspace y rol de administrador, y la verificación ocurre antes
de construir ningún adaptador. Si falla, la respuesta nombra al proveedor y una razón
clasificada (un código HTTP, o que no se pudo alcanzar al proveedor); el texto de la
excepción original va al log, nunca al cuerpo de la respuesta.

### Credenciales de Trello (scoped a workspace)

`GET` y `PUT /settings/trello` requieren admin. El `PUT` guarda el par que el admin
pega (clave y token de Trello), **cifrado en reposo**: el repositorio cifra al
escribir y descifra al leer, de modo que ningún llamador maneja ciphertext y la
columna nunca guarda el plaintext. El `GET` devuelve el par descifrado — la misma
convención de `/settings/llm` — y responde campos en `null` para un workspace sin
fila. Un valor en blanco se guarda como `None`, y un campo omitido conserva el valor
almacenado.

`GET /settings/trello/status` es la excepción legible por cualquier miembro:
responde `{configured, missing}` con los **nombres de los campos** que faltan
(`api_key`, `token`) y nunca con la credencial, porque el miembro que no puede leer
las credenciales es justamente quien lanza la exportación que depende de ellas.

Si el servidor no tiene clave maestra configurada, escribir responde `500` con
`error_code: "ENCRYPTION_KEY_MISSING"` y leer una fila ya cifrada responde `500` con
`"CREDENTIAL_UNDECRYPTABLE"` — el sobre canónico de §Errores, no un crash.

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/api/v1/workspaces/{wsId}/settings/trello` | Obtener las credenciales de Trello (descifradas) |
| PUT | `/api/v1/workspaces/{wsId}/settings/trello` | Guardar las credenciales de Trello (cifradas en reposo) |
| GET | `/api/v1/workspaces/{wsId}/settings/trello/status` | ¿Tiene el workspace credenciales de Trello? |

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
(`__add_custom_provider__`); un `providerId` de otro workspace responde `403`. Al renombrar
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

Todo error con código de aplicación usa **un único sobre**: `error_code` a nivel superior
del cuerpo y `detail` con el texto legible. Cuando el error lleva carga estructurada
(errores de importación, transición de estado inválida, config LLM incompleta), esa carga
viaja **dentro** de `detail`, como objeto; el código nunca se anida dentro de `detail`.

```json
{
  "detail": "Project with id '...' not found",
  "error_code": "ENTITY_NOT_FOUND"
}
```

| `error_code` | HTTP Status |
|------|-------------|
| `ENTITY_NOT_FOUND` | 404 |
| `DUPLICATE_ENTITY` | 409 |
| `RATE_LIMIT_EXCEEDED` | 429 |
| `REPOSITORY_ERROR` | 500 |
| `INTERNAL_ERROR` | 500 |

El límite de tasa por usuario (`slowapi` en la aplicación) responde `429` con `RATE_LIMIT_EXCEEDED`
cuando un bucket se agota; el cuerpo no lleva `Retry-After`, así que la instrucción es reintentar
más tarde sin prometer un tiempo. Las rutas de salud (`/health`, `/health/ready`,
`/health/services`) están exentas.

Los errores de validación de cuerpo de FastAPI (`422` por cuerpo malformado o campos
inválidos) también llevan código de aplicación: `REQUEST_VALIDATION_FAILED`. El `detail`
se mantiene en la forma por defecto de FastAPI —una lista de `{type, loc, msg, input}`—
porque el frontend ya la parsea (`buildErrorMessage` lee `first.msg`); el código se agrega
a nivel superior, sin tocar la lista:

```json
{
  "detail": [
    { "type": "missing", "loc": ["body", "name"], "msg": "Field required", "input": {} }
  ],
  "error_code": "REQUEST_VALIDATION_FAILED"
}
```

Los nombres de código viven en un único registro,
`backend/src/storico/api/error_codes.py`, revisado como una sola lista.

**Contrato de existencia (404 vs 403).** En los recursos con alcance de workspace la regla es
explícita y uniforme: **404** cuando la fila no existe, **403** cuando existe pero no es alcanzable
para quien consulta (membresía o contención). Está implementada y razonada en
`backend/src/storico/api/routes/projects.py:95-101`,
`backend/src/storico/api/routes/extraction.py:134-139` y
`backend/src/storico/api/routes/workspace_settings.py` (el handler `rename_custom_provider`):
la existencia y la contención son hechos distintos y se reportan distinto. Eso implica que un id de
otro workspace se puede distinguir de un id inexistente. Es un comportamiento **elegido**, no una
inconsistencia por arreglar — el mismo trade-off que ya aplicaba `extraction.py` —: unificarlo al
revés, 404 para todo, sería una decisión de contrato de API, no un fix, porque cambiaría códigos que
el cliente ya recibe y que hoy nadie ramifica.

Hasta el 2026-09-24 (issue #5) el proveedor propio era la excepción:
`rename_custom_provider` respondía **404** cuando el `providerId` pertenecía a otro workspace, así
que ese id **no** se distinguía de uno inexistente — la lectura anti-probing era deliberada. El
operador la retiró a propósito y alineó la ruta con el resto; el costo aceptado es que un id de otro
workspace ahora es distinguible de uno inexistente.

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
ruta responde `400` con `error_code: "LLM_CONFIG_INCOMPLETE"` a nivel superior del
cuerpo y la lista `missing` dentro de `detail` (el sobre canónico de §Errores), **sin
crear ninguna extracción**.

Además, iniciar una extracción exige ser el dueño del workspace o un miembro con rol
`admin`: un miembro con rol `member` recibe `403` con `error_code:
"WORKSPACE_OWNER_OR_ADMIN_REQUIRED"`, y quien no pertenece al workspace recibe `403`
con `"NOT_A_WORKSPACE_MEMBER"`. En ambos casos no se crea ninguna extracción. La
lectura de estado (`GET .../status/{extractionId}`) sigue abierta a cualquier miembro
del workspace.

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
