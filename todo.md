# Storico — Backlog

> **Última actualización**: 2026-09-17 — cierre del bug de cambio de workspace en el frontend
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

## 🔜 Próximo a tratar — residuos del cambio de workspace

Contexto: el cambio de workspace ya es atómico y workspace-scoped (`workspaceStore.switchWorkspace`
/ `clearWorkspaceScopedState`, `lib/workspace-scope.ts` como única autoridad del scope, guardas de
token + scope en `projects` / `stories` / `workspaceTasks` / `extractions`). Los cuatro puntos
siguientes son residuos que quedaron fuera de ese cambio: ninguno deja datos del workspace anterior
en las slices workspace-scoped, y ninguno tiene síntoma visible hoy.

### 1. `resetExtraction(storyId)` deja una entrada `idle` después de un cambio de workspace

**Estado**: `taskStore.resetExtraction` (lo llama el cleanup de desmontaje de `StoryDetail`) escribe
`extractions[storyId] = INITIAL_EXTRACTION` sin chequeo de scope. Si el cambio de workspace borró las
slices antes de que corra ese cleanup, la slice nueva gana una entrada con todos los campos en null
para el story id del workspace abandonado. Verificado: es **invisible** — el único lector de
`extractions` es `StoryDetail` para el story que está renderizando, y `!extraction` y
`status === 'idle'` rinden idéntico.

- **Fix sugerido**: borrar la clave en lugar de escribir `INITIAL_EXTRACTION`, o gatear el cleanup
  con el scope. Es del lado del store: el componente no tiene acceso al scope.
- **Ojo**: el comentario de `setScopeWorkspace` dice “the single place a switch resets
  `extractions`”, que no es exacto justamente por este camino.

### 2. `pollExtraction` lee antes de chequear el scope

**Estado**: en la rama `completed`, `await get().fetchTasks(storyId)` corre **antes** del primer
chequeo de scope, así que un poll de un workspace descartado igual dispara
`GET /stories/{id}/tasks` y escribe las slices keyed por story/task (`tasks`, `allowedTransitions`).
No toca `workspaceTasks` ni `extractions`, que son las workspace-scoped.

- **Fix sugerido**: mover ese `await` debajo del chequeo `isScopedWorkspace(workspaceId)`.

### 3. El `error` global se escribe sin chequeo de scope

**Estado**: el `catch` de `projectStore.createProject` (y el patrón equivalente de
`storyStore.createStory`) hace `set({ error: message, saving: false })` sin comparar el scope. Un
error de un request del workspace abandonado puede quedar como banner transitorio en el workspace
nuevo. No es dato del workspace anterior, es un string global.

- **Fix sugerido**: aplicar la misma comparación `getScopedWorkspaceId() === scopeAtCall` al escribir
  `error`, o mover el `error` de las slices globales.

### 4. `updateTask` / `updateTaskStatus` sin fence de scope

**Estado**: verificado que **no hay fuga** — sólo hacen `map` sobre `tasks` (keyed por story, se
conserva a propósito) y sobre `workspaceTasks`, que queda vacío tras un cambio de workspace, así que
el `map` es un no-op. Se deja anotado como deuda de consistencia, no como bug.

### Falta de verificación end-to-end

**Estado**: todo el cambio está verificado con vitest + jsdom y APIs mockeadas (21 archivos / 139
tests, `tsc` limpio, con sondeos de falsificación en cuatro rondas). No hay ejecución en navegador:
`playwright` no está instalado y los specs de `frontend/e2e/` no son ejecutables.

- **Pendiente**: confirmar el orden real de montaje/desmontaje de las islas con View Transitions en
  un navegador. Es lo único que deja abierto la clase “residuo invisible” de los puntos 1 y 2.

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

### 4. `POST /api/v1/tasks/` no valida workspace (gap de autorización)

`create_task` (`api/routes/tasks.py:87`) recibe `current_user` con `# noqa: ARG001` y **nunca lo
usa**: crea el `Task` con el `user_story_id` que venga en el body, sin resolver story → project →
workspace ni verificar membresía. Cualquier usuario autenticado puede inyectar tareas en un
workspace ajeno, y esas tareas después aparecen en el listado de sus miembros.

Contraste: `GET /tasks/` **sí** está scoped (story → project → workspace + membresía). Lo
documenta `test_create_task`, que pasa creando una tarea con un `user_story_id` random sin story ni
workspace detrás.

- **Fix**: validar la story y la membresía antes del `save()`, con el mismo patrón que
  `extractions.py::_validate_extraction_workspace_access`, y eliminar el `noqa`.
- **Decisión previa**: ¿crear tareas sueltas sigue siendo una operación soportada, o el único
  camino debería ser la extracción desde una story?

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

- **10 tests backend fallando (preexistentes)** — `test_extractions.py` (4) y `test_tasks.py` (6).
  **Causa real: los tests predatan el scoping por workspace.** Siembran filas cuyo
  `user_story_id` es un `uuid4()` sin story / project / workspace reales y nunca crean membresía,
  mientras los routes resuelven el workspace **a través de la story** y exigen membresía: de ahí
  los `404` y los listados vacíos (`total == 0`).
  - **Corrección al diagnóstico anterior**: el `.value` sobre un `status` que ya es `str` **no** es
    la causa. El patrón existe en `task_repository._to_orm_kwargs:91` pero no falla, porque
    `Task.status` sí es enum. El `.value` que rompía estaba en
    `extraction_repository._to_response`, y sólo afectaba a 3 tests de status.
  - **Los 4 ya corregidos** (`acf33dc`): `test_extract_success` asertaba `model_used` /
    `confidence_score` / `created_at` — campos que `ExtractResponse` no tiene — sobre un
    `get_extract_use_case` que ningún route usa; `test_extract_llm_error` decía cubrir el fallo del
    LLM pero sólo asertaba `202`, imposible para un endpoint fire-and-forget (se movió al task,
    que es quien lo posee); y 3 tests de status pasaban strings donde va `ExtractionStatus`.
  - **Fix de los 10**: que cada test siembre story → project → workspace + membresía. Los helpers
    `_create_story` / `_add_member` de `test_extraction.py` sirven de modelo.
  - **Verificación**: la suite quedó en 10 fallando / 399 pasando / 1 skip (baseline: 14 / 395 / 1).
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
- **151 errores de `ruff check src tests` (preexistentes)** — 48 `UP007`, 39 `I001`, 24 `F401`,
  16 `UP035`, 14 `UP017`, 5 `F841`, 3 `UP037`, 1 `E402`, 1 `F811`. 135 son autofixables. Los
  archivos tocados en la última pasada quedaron limpios; el resto es deuda general. **No hay CI
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
