# Storico — Backlog

> **Última actualización**: 2026-09-17 (4) — cerrado el gap de autorización de `POST /tasks/` y, con
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

## 🔜 Próximo a tratar — cierre de la clase “scope” en los stores

Contexto: el cambio de workspace ya es atómico y workspace-scoped, y `lib/workspace-scope.ts` es la
única autoridad del scope. Los tres residuos que quedaban fuera de ese cambio, y después la misma
clase completa en los cuatro `catch` de `update*` / `delete*`, se cerraron el 2026-09-17 (ver
✅ Completado). Lo que sigue es lo que esos cierres **dejaron al descubierto**, más la verificación que
sigue faltando.

### 1. `StoryDetail.handleExtract`: el `catch` es código muerto (preexistente)

**Estado**: `taskStore.extractTasks` **se traga sus propios errores** — su `catch` marca la extracción
como `failed` / `unauthorized` y no tiene `throw` — así que `await extractTasks(...)` nunca rechaza y
el `catch` de `handleExtract` (`StoryDetail.tsx:170-190`) no se ejecuta nunca; con él, su
`toast.error` y su `resetExtraction(storyId)`. No es un bug visible: el toast de fallo llega igual por
el `useEffect` que observa `extractions[storyId].status`. Pero implica que el cleanup de desmontaje es
la **única llamada viva** de `resetExtraction`, y que hay ~20 líneas de manejo de errores por status
HTTP (401 / 400 / 504) que no cubren nada.

- **Decisión pendiente**: ¿el store re-lanza para que el componente maneje los status, o el componente
  suelta ese `catch` y se queda con el toast del efecto?

### 2. La equivalencia `missing` vs `idle` está verificada por lectura, no por test de componente

**Estado**: el fix de `resetExtraction` se apoya en que un entry ausente y uno con `status === 'idle'`
toman la misma rama en cada lector que **renderiza** (botón de extraer, spinner, `disabled`). Está
verificado leyendo `StoryDetail` y fijado por un test de store; no por un test de componente, porque
no existe `StoryDetail.test.tsx` y montarlo pide mockear el store, el router y el layout. El único
lector que los distingue es el `useEffect` del toast (salta `setPrevExtractionStatus`), y no puede
observar la diferencia porque el cleanup de desmontaje es la única llamada viva (ver punto 1).

- **Pendiente**: un test de componente de `StoryDetail` que fije las dos ramas. Es la única parte de
  este cierre apoyada en lectura en lugar de ejecución.

### Falta de verificación end-to-end

**Estado**: todo el cambio está verificado con vitest + jsdom y APIs mockeadas (21 archivos / **159**
tests en verde, `tsc` limpio, `pnpm build` verde). No hay ejecución en navegador: `playwright` no está
instalado y los specs de `frontend/e2e/` no son ejecutables.

- **Pendiente**: confirmar el orden real de montaje/desmontaje de las islas con View Transitions en
  un navegador. Es lo que deja abierta la clase “residuo invisible” del punto 2.

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

Hoy sólo existe el valor `'trello'` en el enum `ExportFormat` y en i18n — no hay adapter.
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

## 🧹 Limpieza menor / deuda pendiente

- **`projectStore.saving` / `storyStore.saving` son estado muerto** — ningún componente los lee: todos
  los `saving` de la UI son `useState` locales (`StoryForm`, `ProjectForm`, `TaskEditor`,
  `ProjectsList.deleteSaving`). Los stores los escriben y los liberan, lo cual es correcto como
  contrato, pero hoy no mueven nada. Decidir: cablearlos a los forms o eliminarlos.
- **`storyStore.error` se escribe y nadie lo lee** — los `catch` de `createStory` / `updateStory` /
  `deleteStory` escriben un campo sin consumidor (a diferencia de `projectStore.error`, que
  `ProjectsList.tsx:43` sí consume vía `setLocalError`). El gating por scope de esos tres caminos es
  correcto como contrato del store, pero **su valor visible hoy es cero**; el del lado de proyectos sí
  llega a pantalla.
- **Invariante no asertado: `currentWorkspace.id === scopedWorkspaceId`** — la guarda
  `isScopedWorkspace(ws.id)` de `projectStore` lo asume, y `workspaceStore.fetchWorkspaces` compara
  `nextWorkspace.id` contra `persisted.id` (o sea, contra `currentWorkspace`) en lugar de contra el id
  scoped. Hoy se cumple en los caminos que llaman a `setScopedWorkspaceId`, pero nada lo fija por test
  y el modo de falla es un banner **suprimido**, que es la dirección silenciosa. Un test que asiente la
  equivalencia en cada camino del switch lo cerraría.
- **Cobertura: `scopeAtCall` observado en las mutaciones de story** — los tests nuevos arrancan de
  `resetScopedWorkspace()`, así que `scopeAtCall` es siempre `undefined`. Las variantes “muestreé un id
  real y me quedé” / “…y me moví” no están ejercitadas (equivalentes hoy, pero es el caso que el
  helper existe para cubrir).
- **Seedings duplicados que quedaron fuera del cierre** — `test_stories.py::_seed_workspace_and_project`,
  `test_export.py::_create_workspace` / `_create_story` / `_create_tasks` y
  `test_workspace_settings_prompts.py::_add_member` hacen lo mismo que el nuevo `seed_workspace` de
  `conftest.py`. Consolidarlos suma 3 archivos de test al scope; no se hizo para no inflar el diff.
- **403/404 y `detail` inconsistentes en la misma condición** — conviven cuatro formas:
  `"Not a member of this workspace"` (el walk compartido), `"Not a member of this project's
  workspace"` (`stories.py::create_story` / `list_stories`), `"This user story does not belong to the
  specified workspace"` (`extraction.py`) y `projects.py::_verify_project_belongs_to_workspace`, que usa
  **404** donde `extraction.py` usa **403**. Preexistente; unificarlo es una decisión de contrato de API,
  no un fix.
- **Oráculo de existencia** — un miembro del workspace B distingue 404 ("no existe") de 403 ("existe
  pero no es tuyo"). Preexistente en `GET /stories|tasks|extractions/{id}`; en el status route fue
  mejora neta, porque antes devolvía el payload completo a cualquier miembro de cualquier workspace.
- **Rama no ejercitada en el walk compartido** — `dependencies.py` `project is None` nunca se ejecuta en
  `tests/test_api` (medido con `sys.settrace`). Inalcanzable por las FKs; valor bajo.
- **Los 403 nuevos sólo fijan el status** — no pinnean `detail` ni `type`, a diferencia del 404, que sí
  fija `type == "entity_not_found"`. Los strings de 403 quedan sin contrato fijado por test.
- **`pytest-cov` NO es confiable en este entorno** — reporta como faltantes líneas que un
  `sys.settrace` ve ejecutar (p. ej. `dependencies.py:259-270`, contradiciendo tests que pasan).
  Repro: `COVERAGE_FILE=/tmp/x python -m pytest tests/test_api/test_stories.py --cov=storico.api`. No hay
  `COVERAGE_*` ni `.coveragerc`. Cross-checkear con tracer antes de concluir algo por coverage.
- **`frontend/src/lib/api.ts` `ApiClient.startExtraction` es código muerto con la URL mal armada** —
  arma `/api/v1/workspaces/${data.user_story_id}/extract/`, o sea mete un **story id** en el segmento del
  workspace. Nadie lo llama (`taskStore` importa `@/lib/tasks-api`, no `@/lib/api`), pero quien lo use
  pega en la ruta equivocada. Eliminarlo o arreglarlo.
- **`TaskService` es código muerto y duplica un contrato** — `application/services/task_service.py`
  nunca se instancia (fuera de `application/__init__.py` no hay referencias) y su `update_status`
  reimplementa el chequeo de transición que `update_task` hace inline, con otro tipo de error
  (`InvalidStateTransition` vs `HTTPException(400, INVALID_STATE_TRANSITION)`); además referencia
  `InvalidStateTransition` antes de definirlo en el mismo módulo. No tiene `create`, así que no es el seam
  de `POST /tasks/`.
- **`VectorStorePort.search_similar`** — `workspace_id` quedó opcional; apretar a requerido
  (el path end-to-end siempre lo pasa). Recomendado en follow-up.
- **`us-decomposition` `design.md`** — nombra el filename viejo `storico-tasks-{id}.{ext}` vs
  el implementado `tasks-export-{workspace.id}.{ext}`; el spec canónico no lo manda, pero el
  design hay que realinearlo.
- **`apply-progress.md` ausente** en `us-decomposition` (strict TDD) — excepción registrada
  (artefactos e implementación aterrizaron juntos históricamente).
- **i18n keys muertas** del `FewShotExamplesEditor` eliminado — quedan **7** sin ningún uso en
  `src/`: `fewShotDesc`, `fewShotTitle`, `fewShotTasksLabel`, `fewShotTasksMin`,
  `fewShotUserStoryLabel`, `fewShotUserStoryMin`, `fewShotUserStoryPlaceholder` (en `en.json` y
  `es.json`). Las de `fewShotEnabledOn` / `fewShotEnabledOff` ya se eliminaron.
- **146 errores de `ruff check src tests` (preexistentes)** — eran 151; los archivos tocados en la
  última pasada quedaron limpios (incluidos imports muertos que el autofix eliminó y `HEAD` sí tenía:
  `stories.py` E402/F401 e `extraction.py` I001 + 2×F401). El resto es deuda general. **No hay CI
  que corra ruff ni pytest** (`.github/workflows/` sólo tiene `deploy-backend.yml`), así que esta
  deuda crece sin freno.
- **`globals.css`: `--color-border: var(--color-border)` es autorreferente** — está en el bloque
  `@theme inline`. Hoy no rompe porque el `@theme` posterior redefine `--color-border` y gana la
  cascada, pero si ese bloque se reordena o se elimina, `border-border` (aplicado a `*` en
  `@layer base`) queda inválido y **desaparecen todos los bordes**. Debería apuntar directo al
  token de diseño.
- **Makefile**: `test-backend` apunta a `backend/.venv/bin/pytest` pero ese venv no traía pytest
  — los tests corrían con el conda env `storico`. **Resuelto en la práctica**: se instaló el extra
  `dev` ya declarado (`pytest`, `pytest-asyncio`, `pytest-cov`, `aiosqlite`, `httpx`, `ruff`) en
  `backend/.venv`, que reproduce el baseline documentado con SQLite in-memory y sin Docker. Queda
  decidir si se oficializa `.venv` (portátil) y se retira la dependencia del conda env.
- **Falso positivo stale de pyright en `users.py`** — `lens_diagnostics` reporta
  `RenameWorkspaceUseCase` sin `workspace_name` / `workspace_icon` en `PATCH /users/me/onboarding`.
  El constructor sólo recibe `ws_repo` y `execute()` sí acepta `new_name` / `new_icon`;
  `test_users.py` pasa 8/8. Ignorar salvo que ese código cambie.
- **`StoryForm.tsx:515`**: último `dangerouslySetInnerHTML` del frontend — renderiza
  `t.stories.story_format_hint` (string i18n estático, seguro por contenido). Mismo patrón
  ya eliminado en `DeleteAccountDialog` con `renderBoldMarkup()`.
- **`tasks-api.ts` `updateTask`**: bloque muerto — *"We need the current status - fetch it
  first"* sin hacer nada. Implementar o eliminar.

---

## ✅ Completado (referencia — items eliminados del backlog)

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
