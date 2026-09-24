# ODD Feature: retire-todo-md

> **Status**: **implementado, árbol sucio a la espera de commit — sin revisión nativa.** Branch
> `fix/prod-honesty-followups`; el commit lo hace el orquestador. No se corrió ninguna suite: el cambio
> es solo documentación y `CONTRIBUTING.md` exige las suites para cambios de código. La verificación
> documental (git status, git diff --stat, grep repo-wide de `todo.md`) está en "Verificación".
> **Created**: 2026-09-23
> **Workflow**: Organic Driven Development (ODD)
> **Issue**: [alvaldes/storico#3](https://github.com/alvaldes/storico/issues/3)

## Problem

`todo.md` era el backlog manual del proyecto: ledger de verificación por ciclo, sección de completados,
bloqueantes de producción, deuda aceptada. Con el tiempo se volvió el punto donde las afirmaciones se
atrasaban respecto del código —el sweep WU4 de `schema-drift-gate` ya corrigió cuatro de sus claims in
situ y el archivo volvió a atrasarse solo— y nada automatizado lo lee. Se retira migrando primero cada
cosa única a su hogar y dejando un puntero corto bajo el mismo nombre, para que las referencias
existentes sigan resolviendo. Ese era el objetivo: que nada se pierda y ninguna referencia quede
colgando. La primera mitad **no se cumplió a la primera**: la verificación independiente de este lote
encontró dos bullets únicos que quedaron fuera de la migración (ver "Corrección post-verificación" más
abajo); se recuperaron del original y ya están en sus hogares.

## Auditoría previa (medida, no supuesta)

- **Nada automatizado lee `todo.md`**: el grep repo-wide sobre archivos trackeados no encuentra ninguna
  mención en `.github/`, `Makefile`, scripts de `package.json`, tests ni hooks. Sus únicos lectores
  eran humanos y otros documentos.
- **Citas al archivo**: 8 citas con número de línea dentro de `odd/tasks/schema-drift-gate.md`
  (`:211` ×3, `:213-215` ×2, `:217`, `:220`, `:220-221`) —más la mención del archivo en la lista de
  archivos del WU4 de ese registro—, y menciones en prosa en `odd/tasks/advisory-closures.md` (2) y
  `odd/tasks/prod-checklist-honesty.md` (**4 líneas / 5 ocurrencias**; el encargo decía 3 — medido con
  `grep -oE '(^|[^.])todo\.md' odd/tasks/prod-checklist-honesty.md | wc -l` = 5 ocurrencias, en las
  líneas 127, 180, 284 y 433). Todas se
  repuntan o se anotan; ninguna queda como cita viva contra el archivo retirado.
- **Los 4 claims stale/falsos** que el sweep WU4 de `schema-drift-gate` corrigió in situ: el total de
  CI ("418"), la atribución del `RuntimeWarning`, los "22 diagnósticos" de `api/app.py` (eran 12) y
  "ningún test cubre migraciones / 50 archivos". Al momento del retiro el archivo estaba otra vez
  atrasado por sí mismo: decía 24 revisiones de Alembic cuando hay 26 medidas
  (`ls backend/src/storico/infrastructure/database/alembic/versions/*.py | wc -l`), y conteos de suite
  viejos (22 archivos / 162 tests contra 37 / 425 en el gate más reciente). Esa es la razón
  estructural del retiro: un backlog manual no puede mantenerse honesto.
- **Las referencias a `prod.todo.md` sobreviven intactas**: este lote no toca ese archivo ni sus citas.
  `prod.todo.md` queda como el checklist único de producción, seguridad y observabilidad; está
  explícitamente **fuera de alcance** para este lote.

## Migración (qué fue a dónde)

| Contenido de `todo.md` | Hogar |
|---|---|
| Bloqueantes de producción, importantes y items V2 (los items numerados y "Bajos / V2") | `prod.todo.md`, que ya los cubre |
| Brecha 1: el toast de fallo asume que el render de `pending` se observó antes de asentarse; brecha 2: falta de verificación end-to-end | `docs/testing.md` (frontend, sección "Pendiente") |
| `pytest-cov` no confiable en este entorno + repro | `docs/testing.md` ("Cómo correr tests", junto al comando de cobertura) |
| Decisión abierta `navigate()` de Astro vs `window.location.assign`, con los 5 call sites medidos | `docs/frontend-state.md` |
| Falso positivo de pyright en `users.py:101:34`; diagnósticos de tipado en `api/app.py`; ruido heurístico de pi-lens en la capa de datos | `docs/known-issues.md` (nuevo), indexado desde `docs/README.md` |
| Regla de existencia 404/403 con su rationale ("el oráculo de existencia es ahora un contrato") | `docs/api.md` (sección "Errores") — recuperado en la corrección post-verificación |
| "El primer run del CI puede salir rojo por infraestructura, no por código", con la decisión deliberada de no tocar la condición del skip | `docs/testing.md` (sección "Tests de integración (Docker)") — recuperado en la corrección post-verificación |
| Ledger de verificación por ciclo (verbatim) | **ANEXO A** de este documento — única copia en el repo |
| Historia de completados con commits, PRs y conteos (verbatim) | **ANEXO B** de este documento |
| Seguimiento a nivel proyecto | fuera del repositorio, en el tablero Kanban del operador |

## Corrección post-verificación (2026-09-23)

La verificación independiente de este retiro encontró un blocker: dos bullets únicos de la sección
"Deuda conocida y notas aceptadas" del original no se habían migrado a ningún lugar del árbol — el
encargo del escritor original los omitió. Son la regla de existencia 404/403 con su rationale, y el
aviso de que el primer run del CI puede salir rojo por infraestructura con la decisión deliberada de
no tocar la condición del skip. Ambos se recuperaron de `git show HEAD:todo.md` y se migraron a sus
hogares (ver la tabla de arriba). El conteo de menciones de `prod-checklist-honesty.md` también
estaba impreciso: son **4 líneas / 5 ocurrencias**, no 4 ocurrencias; la medición está anotada en la
auditoría.

Una **segunda** ronda de verificación sobre esa misma corrección encontró tres defectos más, ya
resueltos. El bullet del primer run del CI había perdido la ruta del test y la causa local —«el daemon
de Docker no responde»—, restituidas en `docs/testing.md`. El párrafo migrado a `docs/api.md`
publicaba la afirmación del original de que la regla 404/403 era **uniforme en todo el backend**, y el
código la contradice en `backend/src/storico/api/routes/workspace_settings.py:356-358`: un
`providerId` de otro workspace responde 404, así que ahí **no** se distingue de uno inexistente. El
párrafo ahora delimita la regla a los recursos con alcance de workspace, nombra la excepción con su
ruta y deja la reconciliación como decisión de contrato abierta, sin decidirla acá. Y el bloque
«Verificación» de este registro declaraba 7 archivos modificados cuando son 8: faltaba `docs/api.md`.

## ANEXO A — ledger de verificación por ciclo

> Copiado **verbatim** de `todo.md` (líneas 3–71 del archivo original) el 2026-09-23 al retirarlo.
> Esta es la única copia de ese ledger en el repositorio: no editar, no resumir, no reordenar.

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

## ANEXO B — completados (referencia — items eliminados del backlog)

> Copiado **verbatim** de `todo.md` (sección `## ✅ Completado`, líneas 232–379 del archivo original)
> el 2026-09-23 al retirarlo, con sus commits, PRs y conteos intactos.

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

## Verificación (observada, 2026-09-23)

- `git status --short`: 8 modificados (`docs/README.md`, `docs/api.md`, `docs/frontend-state.md`,
  `docs/testing.md`, `odd/tasks/advisory-closures.md`, `odd/tasks/prod-checklist-honesty.md`,
  `odd/tasks/schema-drift-gate.md`, `todo.md`) + 2 nuevos sin trackear
  (`docs/known-issues.md`, este registro). Nada tocado fuera de las superficies autorizadas;
  `prod.todo.md`, `AGENTS.md`, `CONTRIBUTING.md` y los manifests de versión intactos.
- `git diff --stat`: 74 inserciones, 394 borrados; `todo.md` pasa de 379 líneas a 7 (el puntero).
- `grep -rn 'todo\.md'` repo-wide: cero citas vivas con número de línea contra el archivo retirado.
  Los hits restantes son o el puntero mismo, o el registro nuevo y sus anexos, o menciones históricas
  anotadas con el retiro en `schema-drift-gate.md` (89, 142, 224, 278, 409–412, 415),
  `advisory-closures.md` (32, 54–55) y `prod-checklist-honesty.md` (127, 180, 284, 433). Todas las
  demás coincidencias del grep son de `prod.todo.md`, archivo distinto y explícitamente fuera de alcance.
- No se corrió ninguna suite: cambio solo documental; `CONTRIBUTING.md` exige las suites para cambios
  de código.
