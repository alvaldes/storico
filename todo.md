# Storico — Backlog

> **Última actualización**: 2026-09-17 (8) — **ciclo cerrado**: todos los items accionables de “Próximo a
> tratar” y “Limpieza menor” que se podían cerrar sin otro feature quedaron cerrados. En esta pasada:
> `storyStore.error` eliminado (nadie lo leía, junto con los tipos y el helper que solo él usaba), 8 tests
> que fijan el invariante `currentWorkspace.id === scopedWorkspaceId` por cada camino del switch, variantes
> con `scopeAtCall` **observado**, los dos `renderBoldMarkup` consolidados en uno con tests de la propiedad
> anti-XSS, tipos muertos borrados, seedings duplicados consolidados en `seed_workspace` (con diff de
> aserciones: **una sola cambió, y es un renombre**), test del caso `None` explícito del adapter, `design.md`
> realineado contra el código real, `apply-progress.md` registrado honestamente (sin inventar un log TDD), y
> el backend reformateado entero con `ruff format --check` a**gregado al CI**. Verificado: backend **428/1/0**,
> frontend **23 archivos / 189**, `tsc` limpio, `ruff check` y `ruff format --check` en cero.
> Última actualización previa: 2026-09-17 (7) — alineado el contrato de autorización: **404** = “esa fila no
> existe”, **403** = “existe pero no es alcanzable por vos”, uniforme en todo el backend. `projects.py`
> dejó de devolver 404 para contención y los dos strings distintos de membresía colapsaron en uno. +10
> tests que lo fijan (7 probados por mutación), y se cubrieron la rama `project is None` del walk y la
> rama sólo-icono del onboarding. Verificado: backend **427 passed / 1 skip / 0 failed**, `ruff` en cero,
> frontend sin tocar.
> Última actualización previa: 2026-09-17 (6) — cerrados `TaskService` (opción (a): el único sitio de decisión
> de la transición es `TaskService.ensure_transition_allowed` y la ruta solo **traduce** el error de dominio a
> un 400 byte a byte idéntico) y la deuda de lint: `ruff check src tests` de **145 → 0**, más
> `.github/workflows/ci.yml` con dos jobs (backend: `ruff check` bloqueante + `pytest`; frontend: `tsc` +
> `vitest`). Verificado: backend **417 passed / 1 skip / 0 failed**, frontend **22 archivos / 162**, `tsc`
> limpio, y cada comando del workflow corrido localmente.
> Última actualización previa: 2026-09-17 (5) — barrido de “Próximo a tratar” y “Limpieza menor”. Cerrados:
> el `catch` inalcanzable de `handleExtract` (con el toast de 504 preservado, que ahora aparece de verdad),
> el test de componente que faltaba para la equivalencia `missing` ≡ `idle`, `ApiClient.startExtraction`,
> el bloque no-op de `tasks-api.ts`, las 7 claves i18n muertas, el último `dangerouslySetInnerHTML` y el
> alias identidad de `--color-border`; más el scope obligatorio de `VectorStorePort.search_similar` con
> fail-closed. **Dos correcciones de encuadre**: la fuga de RAG era **latente** (ningún caller de producción
> omitía el scope) y `TaskService` **no** es código muerto (lo usa un test de integración) — lo que hay ahí
> son dos autoridades de la regla de transición. Verificado: backend **416/1/0**, frontend **22 archivos /
> 162**, `tsc` limpio.
> Última actualización previa: 2026-09-17 (4) — cerrado el gap de autorización de `POST /tasks/` y, con
> él, la clase entera: el walk `story → project → workspace → membresía` estaba copiado **cinco**
> veces y ahora es una sola implementación (`api/dependencies.py::require_story_workspace_access`),
> `create_task` autoriza antes de construir el `Task` (y perdió el `# noqa: ARG001`), y
> `GET /workspaces/{ws}/extract/status/{id}` (que validaba la membresía del path pero **nunca** que
> la extracción perteneciera a ese workspace) ahora exige contención. De paso se arreglaron los 10
> tests que estaban rojos por fixtures. Verificado **ejecutando**, y con los tres cruces
> reconstruidos en `/tmp`: tests de `HEAD` × `src/` de `HEAD` = los 10 rojos, tests nuevos × `src/`
> viejo = exactamente los 4 tests de seguridad, todo junto = **415 passed / 0 failed / 1 skip**.
> Última actualización previa: 2026-09-17 (3) — cerrada la clase completa del banner de `error`: los
> cuatro `catch` de `updateProject` / `deleteProject` / `updateStory` / `deleteStory` ahora gatean el
> banner por scope — `isScopedWorkspace(ws.id)` en proyectos, que ya llevan su workspace id en el
> request, e `isScopeUnchanged(scopeAtCall)` en stories, que no lo llevan — y liberan `saving` fuera
> de la guarda. 8 tests nuevos, 4 de ellos falsables. Verificado **ejecutando**: 21 archivos / **159**
> tests, `tsc` limpio, `pnpm build` verde. La verificación destapó que `projectStore.saving` /
> `storyStore.saving` **no tienen ningún consumidor** en producción y que `storyStore.error` se
> escribe y nadie lo lee: ver 🧹 Limpieza menor.
> Última actualización previa: 2026-09-17 (2) — cerrados tres de los cuatro residuos del cambio de
> workspace: `resetExtraction` borra la clave en lugar de escribir un placeholder `idle`,
> `pollExtraction` chequea el scope **antes** del refresh de tasks, y el banner de `error` se escribe
> gateado por scope en `createProject` / `createStory` vía el nuevo `isScopeUnchanged`. El cuarto
> punto se cerró fijando el invariante con un test de regresión, no con código. La verificación
> destapó además que **la misma clase sigue viva** en `updateProject` / `deleteProject` /
> `updateStory` / `deleteStory`, y que el `catch` de `handleExtract` es código muerto: los dos están
> al inicio de este archivo. Estado verificado **ejecutando**: 21 archivos / 151 tests, `tsc` limpio,
> `pnpm build` verde.
> Última actualización previa: 2026-09-17 — cierre del bug de cambio de workspace en el frontend
> (crear o cambiar de workspace dejaba datos del workspace anterior en pantalla: la página
> `/workspaces/{id}/settings` se ataba a la URL y guardaba en el workspace equivocado, y
> `/stories` listaba historias de todos los workspaces). La clase de bug está cerrada y
> verificada; quedan cuatro residuos menores, listados al inicio de este archivo.
> Última actualización previa: 2026-09-15 — auditoría de los fallos preexistentes del backend. Se
> corrigieron 4 de los 14 y se re-diagnosticaron los 10 restantes: su causa es que **predatan el
> scoping por workspace**, no el `.value` sobre `status` que se creía. Apareció además un gap de
> autorización en `POST /tasks/`. Estado verificado **ejecutando la suite**, no leyendo documentos.
> Última actualización previa: 2026-09-14 (2) — se cerraron por SDD dos changes: `few-shot-qdrant`
> (few-shot automático desde Qdrant + `EmbeddingPort` cloud) y `us-decomposition`
> (Kanban / Task Editor / Export; 4 blockers + 3 warnings de fidelidad corregidos).

---

## 🔜 Próximo a tratar — verificación que falta

Los puntos de “código muerto” que estaban en esta sección se cerraron el 2026-09-17 (ver ✅ Completado). Lo
que queda no es código: es verificación que sólo un navegador o un test que todavía no existe pueden darnos.

### 1. El toast de fallo asume que el render de `pending` se observó antes de asentarse

**Estado**: la autoridad única del toast de fallo es el `useEffect` de `StoryDetail`, y dispara sólo si
`prevExtractionStatus === 'pending'` cuando la extracción se asienta. El test de componente nuevo arma esa
secuencia a mano (render `pending` → asentar). En producción el rechazo del POST pasa por I/O, así que React
flushea el render de `pending` primero; pero con updates completamente batcheados el toast no saldría, y
**ningún test cubre el caso colapsado**. Es preexistente: el `catch` que se borró era inalcanzable, así que
tampoco lo cubría.

### 2. Falta de verificación end-to-end

**Estado**: todo el cambio está verificado con vitest + jsdom y APIs mockeadas (22 archivos / **162**
tests en verde, `tsc` limpio, `pnpm build` verde). No hay ejecución en navegador: `playwright` no está
instalado y los specs de `frontend/e2e/` no son ejecutables.

- **Pendiente**: confirmar el orden real de montaje/desmontaje de las islas con View Transitions en
  un navegador. Tampoco hay test que cubra el CSS compilado: el fix de `--color-border` se validó compilando
el CSS por fuera de la suite.

---

## 🔴 Bloqueantes de producción

### 1. Verificar extracción cloud en prod (código listo)

**Estado**: los adapters existen y están cableados — `OllamaAdapter`, `GeminiAdapter`,
`OpenAIAdapter`, `AnthropicAdapter` (`8b51819`, `27d200e`). `extraction_task._run_extraction`
rutea por provider y exige API key por workspace. El gap de código está **cerrado**.

- **Pendiente**: probar end-to-end con API key real en Vercel (Gemini / OpenAI / Anthropic).
- Parámetros de referencia: `temperature=0.1`, `max_tokens=2048`.

### 2. Qdrant Cloud + embeddings cloud en prod

**Estado**: implementado el `EmbeddingPort` con adapters Ollama / Google / OpenAI (768d) y
factory `STORICO_EMBEDDING_PROVIDER` (`14d659b`). El vector store quedó workspace-scoped
(`workspace_id` en payload + filtro + índice, `AsyncQdrantClient` / `query_points`) en `8ae9f2a`.

- **Pendiente runtime** (hoy solo se testeó con SDKs mockeados):
  - validar `dimensions` del provider contra el `vector_size` de la colección;
  - correr el seed real `python -m storico.cli.seed_few_shot`;
  - llamadas reales a embeddings cloud (Google / OpenAI).
- **Pendiente config**: `STORICO_EMBEDDING_PROVIDER`, `STORICO_GOOGLE_API_KEY` /
  `STORICO_OPENAI_API_KEY`, `STORICO_QDRANT_URL` / `STORICO_QDRANT_API_KEY` (Cloud, free tier 1GB).

### 3. Migración follow-up: dropear `few_shot_examples`

`workspace_prompts.few_shot_examples` quedó read-only como fuente del seed job. Una vez corrido el
seed en prod (item 2), dropear la columna en una migración aparte.

---

## 🟡 Importantes

### 4. Vercel env audit

Comparar las env vars de ambos proyectos (frontend + backend) contra `.env.example` /
`backend/.env.example`. Prestar atención a: `STORICO_AUTH_INTERNAL_TOKEN` (mismo valor en
ambos), `AUTH_SECRET` (mismo en ambos, distinto del dev), `API_URL` del frontend, y
`STORICO_CORS_ORIGINS` / `STORICO_AUTH_ALLOWED_ORIGINS` → `https://storico.vercel.app`.

### 5. Error monitoring (Sentry)

Backend: `sentry-sdk` inicializado en `app.py` (FastAPI integration incluida).
Frontend: `@sentry/astro` en `astro.config.mjs`. Free tier: 5k events/mes.

### 6. Conector Trello

Hoy el valor `'trello'` ya no existe: se retiró del enum `ExportFormat`, del schema Pydantic y
de la opción del selector, junto con la clave `export_format_trello` de i18n — no hay adapter.
Sigue pendiente el copy de la landing en i18n (`en.json`/`es.json`), que todavía promete
exportación a Trello.
Reutilizar la lógica probada de `csv2trello/core/` (autenticación, boards/listas/cards):
crear `ExportPort` + `TrelloAdapter`, endpoint `POST /api/v1/export/trello`, y conectar
`ExportPanel`.

### 7. Juicio de expertos (tesis)

Evaluación experimental con 6 expertos (Scrum Masters + POs). Métricas: TCR / TAS / IFI.
**Depende de**: extracción funcionando en prod (item 1) + exportación (item 6).

---

## 🟤 Bajos / V2

- **Dominio propio** — comprar, configurar en Vercel, actualizar OAuth redirects.
- **Rate limiting** — Vercel WAF (sin código) o `slowapi` (serverless).
- **Batch asíncrono con Redis** — la extracción *individual* ya es asíncrona
  (`asyncio.create_task` + polling); esto es el procesamiento de lotes.
- **Jira + export CSV/XML** — post-evaluación de la tesis.
- **Dashboard de admin con métricas**.
- **`@playwright/test` como devDependency** — Chromium ya está instalado; con la dependencia
  y un backend corriendo, los specs de `e2e/` pasan de excluidos a ejecutables.
- **`navigate()` de Astro en lugar de `window.location.assign`** — las 5 redirecciones
  restantes son internas por construcción (`localizedPath` clampea, UUIDs); migrar a SPA nav
  mejoraría la UX y silenciaría el scanner de open-redirect.

---

## 🧹 Deuda conocida y notas aceptadas

Todo lo accionable de esta sección se cerró el 2026-09-17 (ver ✅ Completado). Lo que queda son notas
aceptadas o deuda que necesita otro feature, no trabajo pendiente de esta lista.

- **Ruido heurístico de pi-lens en la capa de datos** — marca *Potential SQL injection sink* en cualquier
  `session.execute(...)` y `Cannot access attribute "rowcount" for class "Result[Any]"`. Verificado uno por
  uno: `workspaces.py:290` es una llamada a un *use case* con UUIDs (cero SQL, no hay statement), y los
  repositorios pasan `select(...)` / `delete(...)` de SQLAlchemy construidos con `==`, o sea parametrizados;
  `rowcount` sí existe en runtime (`CursorResult`), es un hueco de los stubs. El diff de esos archivos es
  **puro rewrap** de `ruff format`: un formateador no puede crear un error de SQL ni de tipos. No están en el
  gate (no hay mypy ni pyright configurados) y arreglarlos pediría `cast` / `type: ignore`, que es ruido, no
  seguridad. **No re-investigar sin decidir antes si el backend tiene type-check.**

- **El oráculo de existencia es ahora un contrato, no una inconsistencia** — después de la alineación, la
  regla es uniforme en todo el backend: **404** cuando la fila no existe, **403** cuando existe pero no es
  alcanzable por vos (membresía o contención). Eso implica que un id de otro workspace se puede distinguir
  de un id inexistente. Es el comportamiento **elegido** (el mismo trade-off que ya hacía `extraction.py`),
  y unificarlo al revés —404 para todo— es una decisión de contrato de API, no un fix: cambiaría códigos
  que el cliente ya recibe y que hoy nadie ramifica.
- **`pytest-cov` NO es confiable en este entorno** — reporta como faltantes líneas que un
  `sys.settrace` ve ejecutar (p. ej. `dependencies.py:259-270`, contradiciendo tests que pasan).
  Repro: `COVERAGE_FILE=/tmp/x python -m pytest tests/test_api/test_stories.py --cov=storico.api`. No hay
  `COVERAGE_*` ni `.coveragerc`. Cross-checkear con tracer antes de concluir algo por coverage.
- **Falso positivo de pyright en `users.py` (atribución corregida)** — el diagnóstico real es
  `users.py:101:34` sobre `OnboardingRequest()` (campos con default en `schemas/user.py`, así que la llamada
  es válida), **no** sobre `RenameWorkspaceUseCase`, que la nota anterior culpaba por error: el checker ve
  una firma stale. No hay defecto de producción y no se agregó ninguna supresión. La rama sólo-icono del
  onboarding (`users.py:126-129`), que estaba sin cubrir, ya tiene test.
- **El primer run del CI puede salir rojo por infraestructura, no por código**:
  `tests/test_integration/test_projects_integration.py` se saltea **localmente** porque el daemon de Docker no
  responde, y en los runners de GitHub Docker sí está, así que va a intentar levantar
  `PostgresContainer("postgres:16-alpine")`: el total esperado ahí es 418, o un fallo de pull de imagen. La
  condición del skip no se tocó a propósito para no maquillar el resultado.
- **Warning flaky preexistente**: `PytestUnraisableExceptionWarning` (`coroutine 'Connection._cancel' was
  never awaited`) en `test_project_repo.py`, dependiente de GC y del orden de ejecución. El archivo no está
  tocado por ningún cambio y no se pudo A/B contra el árbol limpio sin stash: latente, sin causalidad
  establecida.
- **22 diagnósticos de tipado preexistentes en `api/app.py`** (rigidez de overloads de FastAPI). No hay mypy
  ni pyright configurados, y ninguno está en el gate. Arreglarlos pide casts o `type: ignore`, o sea cambio
  de lógica: quedan reportados.
- **Las migraciones no las cubre ningún test** — el sweep las validó compilando en memoria y con `ruff F821`,
  no ejecutándolas. Son 50 archivos de alembic.

---

## ✅ Completado (referencia — items eliminados del backlog)

- **Cierre del ciclo de limpieza** (2026-09-17): `storyStore.error` eliminado —nadie lo leía, y con él se
  fueron `StoryErrorInfo`, `extractStoryErrorInfo` y las 3 escrituras que lo alimentaban; el `saving` se queda
  porque es el contrato de “hay una mutación en vuelo” y es lo que pinnean los tests (7 tests renombrados
  siguen asertando la liberación de `saving`, **ninguno borrado**)—. Se agregaron 8 tests que fijan
  `getScopedWorkspaceId() === currentWorkspace?.id ?? null` en **cada** camino que toca `setScopedWorkspaceId`,
  más variantes con `scopeAtCall` **observado** (antes todas arrancaban de unobserved) en los cuatro guards.
  Los dos `renderBoldMarkup` (uno partía de `<b>`, el otro de `<strong>`) son un helper compartido con tests
  que incluyen un payload `<img onerror>` + `<script>` renderizado como **texto literal**, o sea la propiedad
  que hace segura esa zona después del fix de XSS. Se borraron los tipos muertos `ExtractRequest`,
  `ExtractResponse` y `ExtractionUserStory`. Los seedings duplicados de 4 archivos de test se consolidaron en
  `seed_workspace` —verificado con diff de aserciones: **una sola cambió y es un renombre de identificador**,
  `test_export.py` y `test_workspace_settings_prompts.py` no cambiaron ninguna—. Se agregó el test del caso
  `None` explícito del adapter (el revert que reabriría la fuga), se realineó el `design.md` de
  `us-decomposition` contra lo que el código produce de verdad (`tasks-export-{workspace.id}.{ext}`), y se
  registró la ausencia de `apply-progress.md` **sin fabricar un log TDD**: el documento cita el commit real y
  la evidencia que sí existe, y dice explícitamente qué no puede atestiguar. El backend quedó reformateado
  (`ruff format`, 29 archivos) con `ruff format --check` **agregado al CI**.

- **Contrato de autorización alineado y fijado** (2026-09-17): la misma condición se respondía de cuatro
  formas distintas. Ahora **404** = “esa fila no existe” y **403** = “existe pero no es alcanzable por vos”,
  uniforme en todo el backend: `projects.py` dejó de devolver 404 para la contención (el proyecto existe,
  pero en otro workspace) y pasa a 403 con un string paralelo al de `extraction.py`, que quedó como la forma
  de referencia; y los dos strings distintos de “no sos miembro del workspace dueño de X” colapsaron en uno.
  Antes de tocar el código se auditó el consumidor: las tres rutas de proyecto se llaman desde
  `projects-api.ts` y **todos** sus call sites son agnósticos del status (`.catch` → estado local), así que
  ningún cliente primero depende del 404. Se agregó además la cobertura que faltaba: la rama
  `project is None` del walk compartido (con repos stub, porque por API es inalcanzable), la rama sólo-icono
  del onboarding, y los `detail` de los 403 —que esos sí llevan sólo `detail`, sin `type`: agregar un `type`
  habría sido inventar contrato—. Suite 417 → 427, con 7 de los 10 tests nuevos probados por mutación y los
  otros 3 declarados como pins. **Ningún test existente aseraba los strings viejos**, así que no hubo ninguna
  aserción debilitada.

- **Una sola autoridad para la regla de transición de tasks** (2026-09-17): la regla ya vivía en
  `domain/validators/state_machine.py`, pero **quién decidía y quién construía el error** estaba duplicado:
  `update_task` armaba su propio `HTTPException(400, INVALID_STATE_TRANSITION)` y `TaskService.update_status`
  levantaba `InvalidStateTransition` — y la producción nunca corría el segundo. Se extrajo
  `TaskService.ensure_transition_allowed` como único sitio de decisión, y la ruta pasó a **traducir** el error
  de dominio al payload 400 **byte a byte idéntico** (verificado key por key, incluido el orden de
  `allowed_transitions`). `validate_task_transition` queda con un solo call site fuera del dominio
  (`task_service.py`). Se agregó el test que faltaba del payload 400 (claves, orden y que el rechazo no
  persista). No es una prueba retroactiva de que el payload viejo era igual: es un **pin** del contrato, y
  así está dicho en el commit.
- **Deuda de lint del backend cerrada, y con gate** (2026-09-17): `ruff check src tests` pasó de **145 errores
  a 0**, con autofixes seguros (nunca `--unsafe-fixes`) más 15 arreglos a mano. Se auditó **cada import
  removido** con diff de AST de los nombres importados (26 módulos / 30 símbolos) contra todos los
  importadores: **cero violaciones, cero restauraciones**. El `F841` riesgoso de `test_user_repo.py` tenía un
  `await repo.link_account(...)` con efectos reales: se pelaron solo las asignaciones y las llamadas quedaron.
  Los 10 `F401` del barril `routes/__init__.py` se resolvieron con `__all__` —la convención que ya usaban
  `domain/ports/__init__.py` y `models/__init__.py`— en lugar de borrar el barril. Y se agregó
  `.github/workflows/ci.yml`: backend (`ruff check` bloqueante + `pytest`) y frontend (`tsc` + `vitest`), en PR
  y push a `main`. **No se pudo ejecutar GitHub Actions**: cada comando del workflow se corrió localmente y se
  reportó su salida.

- **Limpieza de código muerto del frontend** (2026-09-17): borrado el `catch` de `handleExtract` (era
  inalcanzable: `extractTasks` se traga sus errores) con el toast de timeout **preservado** enseñándole al
  store el código 504 — o sea que el toast de timeout ahora aparece de verdad, antes no aparecía nunca;
  borrado `ApiClient.startExtraction` (código muerto cuya URL metía un *story id* en el segmento del
  workspace); el bloque no-op de `tasks-api.ts::updateTask`; las 7 claves i18n muertas (de ambos archivos, con
  la paridad verificada por test); el último `dangerouslySetInnerHTML` reemplazado por `renderBoldMarkup` (el
  frontend ya no tiene ninguno); y el alias identidad `--color-border: var(--color-border)` eliminado
  (compilado antes y después con Tailwind: mismo valor resuelto, y el modo de falla pasa de mudo a error de
  compilación). Nuevo `StoryDetail.test.tsx` (2 tests, no vacuos: probados por mutación) que fija la
  equivalencia `missing` ≡ `idle` **en el componente**. Suite FE 159 → 162.
- **`VectorStorePort.search_similar` con scope obligatorio** (2026-09-17): `workspace_id` pasó de opcional a
  requerido keyword-only en el puerto y en el adapter (que ahora arma el filtro de workspace siempre), y
  `_fetch_rag_examples` **falla cerrado** (warning + `[]`) cuando no hay scope, en vez de degradar a una
  búsqueda global. Se reemplazó `test_search_similar_without_workspace_sends_no_filter`, que **aserteaba la
  fuga** (`query_filter is None`), por un test de contrato que detecta si alguien vuelve a poner el default.
  **Corrección de encuadre**: la fuga era **latente**, no viva — `extract_and_persist` no tiene ningún caller
  de producción y el único que llama a `extract()` (`extraction_task.py:330`) siempre pasa el workspace, así
  que el impacto era cero en producción; lo que se gana es el contrato del puerto y el fail-closed para
  llamadas directas. Verificado además que `make test-backend` funciona desde `backend/.venv` (esa deuda ya
  estaba resuelta en el Makefile; el warning de SQLAlchemy delata el path de `.venv`).

- **Clase de autorización del backend cerrada** (2026-09-17, ex Bloqueante #4): `POST /api/v1/tasks/`
  recibía `current_user` con `# noqa: ARG001` y **nunca lo usaba** — creaba el `Task` con el
  `user_story_id` del body y lo guardaba, así que cualquier cliente autenticado podía inyectar tareas en
  un workspace ajeno (la FK no es un control de autorización). Ahora el walk
  `story → project → workspace → membresía` vive **una sola vez**, en
  `api/dependencies.py::require_story_workspace_access`, con `reported_as` para conservar byte a byte el
  `detail` del 404 por entidad cabeza; se colapsaron las **cinco** copias (`tasks.py` en
  `create_task` / `_validate_task_workspace_access` / `list_tasks`, `stories.py` ×3, `extractions.py` en
  `_validate_extraction_workspace_access` / `list_extractions`). Se cerró también el gap hermano de
  lectura: `GET /workspaces/{ws}/extract/status/{id}` validaba la membresía del workspace del path pero
  nunca que la extracción perteneciera a él, así que cualquier miembro podía leer cualquier extracción
  por id. No se convirtió `extraction.py::_validate_story_belongs_to_workspace`: ese es un chequeo de
  **contención** (la story debe vivir en el workspace del path), no de membresía, y reusar el helper de
  membresía ahí habría sido una regresión de seguridad. 6 tests nuevos (4 falsables).
- **Los 10 tests backend rojos por fixtures** (ex deuda de Limpieza menor): `test_extractions.py` (4) y
  `test_tasks.py` (6) fallaban porque `authed_client` siembra **un usuario y cero membresías** mientras
  las rutas resuelven el workspace a través de la story y exigen membresía — de ahí los 404 y los
  listados vacíos. Se agregó `seed_workspace` a `tests/conftest.py` (cadena workspace → project →
  stories + membresía, con knobs `user=` / `stories=` / `member=`), se relocalizaron los helpers
  `_create_story` / `_add_member` de `test_extraction.py`, y ningún assert se debilitó (verificado por
  AST). `TestCreateTask` usaba un `uuid4()` suelto y asertaba 201: **ese test documentaba el bug**, y
  pasó a sembrar una story real. La suite backend pasó de **10 fallando / 399 pasando / 1 skip** a
  **415 pasando / 0 fallando / 1 skip**.

- **Clase completa del banner de `error` en los stores** (2026-09-17): los cuatro `catch` de
  `updateProject` / `deleteProject` / `updateStory` / `deleteStory` gatean el banner por scope y
  liberan `saving` fuera de la guarda. Asimetría deliberada y justificada: los requests de proyecto
  **llevan** su workspace id (`PUT/DELETE /workspaces/{ws}/projects/{id}`), así que reusan
  `isScopedWorkspace(ws.id)`; los de story no llevan ninguno (`PUT/DELETE /stories/{id}`), así que
  muestrean `scopeAtCall` con `isScopeUnchanged`. Los comentarios de los seis sitios se corrigieron
  después de que la verificación mostrara que hablaban de un spinner inexistente. 8 tests nuevos
  (4 falsables).

- **Residuos del cambio de workspace** (2026-09-17): `resetExtraction` borra la clave en lugar de
  escribir `INITIAL_EXTRACTION` (constante eliminada; se apoya en que un entry ausente y uno `idle`
  son equivalentes para todo lector que renderiza); `pollExtraction` chequea el scope **antes** del
  `fetchTasks` de la rama `completed`, no solo después; `isScopeUnchanged(scopeAtCall)` nuevo en
  `lib/workspace-scope.ts`, que además colapsa la comparación duplicada a una sola y ahora gatea el
  banner de `error` en `createProject` / `createStory`; y un test de regresión que fija el no-op de
  `updateTask` / `updateTaskStatus` sobre `workspaceTasks`. Los comentarios desactualizados de
  `setScopeWorkspace` y `resetExtraction` quedaron corregidos. Verificado con RED/GREEN por test
  (12 tests nuevos; 6 de ellos fallan contra el código previo).

- **Few-shot automático desde Qdrant** (`few-shot-qdrant`): reemplaza el editor manual por
  retrieval workspace-scoped desde Qdrant; sección de prompt unificada; config por workspace
  (`enabled` / `limit` / `threshold`); migración 0020; seed job `cli/seed_few_shot`;
  frontend `FewShotConfigEditor`. Archivado en
  `openspec/changes/archive/2026-09-14-few-shot-qdrant/`.
- **`EmbeddingPort` + adapters cloud**: Ollama / Google 768d / OpenAI 768-vía-`dimensions` +
  factory `STORICO_EMBEDDING_PROVIDER`.
- **`us-decomposition` cerrado**: Kanban board (drag-and-drop), Task Editor, Export
  (JSON/Markdown por story), extracción workspace-scoped, 401 como auth failure, kanban lock y
  empty state, dependencias sibling-only. Archivado en
  `openspec/changes/archive/2026-09-14-us-decomposition/`.
- **OpenAI / Anthropic LLM adapters** (8b51819, 27d200e): ruteados en la extracción.
- **Workspaces y permisos** (ex #16): admin crea workspaces, miembros, roles — implementado
  (migraciones + `MemberManagement`).
- **Extracción async individual con polling** (ex `todo.md` completo): `asyncio.create_task`
  en el backend + `pollExtraction` en `taskStore`. La migración a Celery/Redis queda cubierta
  por "Batch asíncrono" arriba.
- **Contrato de transiciones de task**: una sola fuente de verdad (`types/task.ts`), no-op
  válido en BE y FE (antes se impedía guardar sin cambiar el status).
- **SSR restaurado**: las 14 islas vuelven a `client:load`/`client:idle` con theming
  hydration-safe (`useThemeHydration` / `useResolvedTheme`); `client:only` eliminado.
- **Formato normalizado**: `.prettierrc.json` (single quotes, printWidth 100) + 119 archivos;
  el formatter ya no genera churn.
- **pnpm como único package manager**: `bun.lockb` y `package-lock.json` eliminados.
- **`@base-ui` prebundleado**: fin del error `error loading dynamically imported module`.
- **Seguridad**: XSS de `DeleteAccountDialog` (email interpolado en innerHTML) arreglado;
  toasts respetan el tema (`data-theme`).
- **Calidad**: tsc 0 errores, suite FE 55/0, tests de regresión nuevos (KanbanBoard, TaskEditor,
  ExportPanel, contract matrix de transiciones).
