# Checklist de producción

Lo que falta antes y después de poner Storico en producción. **Este archivo es la lista única**: los
pendientes de despliegue estaban en `docs/deployment.md` y los de seguridad en `docs/security.md`, y
las dos listas se superponían en cuatro ítems (rate limiting, monitoreo de errores, auditoría de
variables de entorno y dominio propio). Cada ítem dice dónde está el detalle cuando lo hay.

Estado: 🔲 pendiente · 🟡 parcial · ✅ hecho

## Antes de desplegar

Prerrequisitos que, si faltan, rompen algo en silencio o fallan recién en producción.

| Ítem | Estado | Detalle |
|------|--------|---------|
| `STORICO_ENCRYPTION_KEY` configurada | ✅ | Configurada en el `.env` de la VM de producción y cargada en el contenedor (verificado el 2026-09-20, después del reinicio que la tomó). La revisión `0024` cifró la credencial que estaba en texto plano y el proceso la descifra, así que guardar y leer credenciales de workspace funcionan. Generar la clave con `cryptography.fernet.Fernet.generate_key()` y guardarla fuera del repositorio; **perderla deja ilegibles las credenciales ya guardadas**. En la VM quedó un respaldo del archivo como `.env.bak-20260920233204`. |
| Orden de las migraciones | ✅ | Registro de lo aplicado a mano el 2026-09-20: `0022` y `0023` primero (en `0023` la columna tiene que existir antes de que el código la escriba), después el reinicio del contenedor con la clave cargada, y recién `0024`, que reescribe valores existentes. El esquema quedó en `0024` (head). Ojo: eso fue el orden de esas tres revisiones, no una regla. Los docstrings de las tres piden órdenes distintos, y a propósito: `0022` y `0024` quieren el código primero y `0023` quiere la migración primero, porque el orden correcto es una propiedad de cada revisión y no del deploy. Ver `odd/tasks/schema-drift-gate.md`. |
| El deploy corre las migraciones | ✅ | `.github/workflows/deploy-backend.yml` aplica `alembic upgrade head` en una **ventana de mantenimiento**: entre el `docker stop` y el `docker run`, o sea sin ningún release vivo. Es la única posición que satisface a la vez a `0022` y `0024` (que piden el código nuevo vivo antes de correr) y a `0023` (que pide la columna antes de que el código nuevo la lea), porque cada peligro necesita un release vivo del lado equivocado. Corre desde la imagen recién construida y con el mismo `--env-file`, así que la URL y la clave son las del contenedor. Costo aceptado: hay downtime durante la migración, y si falla la API queda abajo en vez de servir contra un esquema que no coincide. El gate de readiness pasó a ser la prueba de que la migración quedó aplicada, y los deploys quedaron serializados. Ver `odd/tasks/deploy-migration-window.md` y `docs/deployment.md`. |
| Suite de integración contra Postgres real | ✅ | Ya corre en CI en cada push: en la ejecución `35546955633` se ejecutó `tests/test_integration/test_projects_integration.py::test_list_projects_with_counts_latency_under_500ms` y el job terminó con `703 passed`. El salto solo ocurre en una máquina sin daemon de Docker, no en CI: `backend/pytest.ini` registra el marcador `integration` pero no lo deselecciona, `.github/workflows/ci.yml` corre `pytest -q` sin filtro de marcadores, `testcontainers>=4.15.0` es dependencia de desarrollo y los runners de GitHub tienen el daemon de Docker que `_docker_reachable()` sondea. Esa deuda ya se pagó: el import usa el módulo canónico `testcontainers.community.postgres` (`backend/tests/test_integration/test_projects_integration.py`), que es lo que fija el piso declarado en `>=4.15.0`, porque por debajo el módulo canónico no existe y el nombre viejo es un shim detrás de un `DeprecationWarning`. |

## Seguridad

| Ítem | Estado | Detalle |
|------|--------|---------|
| Cifrado en reposo de las API keys | ✅ | Fernet con clave maestra en el entorno; revisión `0024`. Ver `docs/security.md`. |
| Rate limiting | 🔲 | `slowapi` en FastAPI, o un límite de tasa en el Caddy que ya está delante del contenedor. **No** un WAF de Vercel: el backend no está en Vercel (ver `docs/deployment.md`), así que un WAF de Vercel no ve el tráfico de la API. Esta fila decía "Vercel WAF"; esa contradicción es el advisory `R3-waf-3`. |
| Restringir CORS a dominios específicos | ✅ | Medido con una sonda sobre el contenedor de producción en ejecución, que imprimió solo booleanos y nunca los valores de origen: `ORIGENES_DECLARADOS: 1`, `USA_EL_DEFAULT_LOCALHOST: False`, `CONTIENE_LOCALHOST_O_127: False`, `CONTIENE_VERCEL_APP: True`, `CONTIENE_HTTP_SIN_TLS_NO_LOCAL: False`. Producción declara un único origen, es un dominio `https` `*.vercel.app` y no incluye ningún origen de desarrollo. Queda un cabo suelto: `.env.prod.local` en la máquina del operador declara `STORICO_AUTH_ALLOWED_ORIGINS` dos veces, así que el primer valor se ignora en silencio; se reporta, no se corrige. |
| Auditoría de variables de entorno | ✅ | Son **dos** lugares, no uno: el `.env` del backend en la VM (`/home/ubuntu/storico/backend/.env`, fuera del control de versiones) y los proyectos de Vercel, que solo llevan variables del frontend. **Cerrada el 2026-09-24**, medida contra la Vercel CLI, el `.env` de dev del repo y el `.env` de la VM por SSH: los valores se compararon por hash SHA-256 y ninguno se imprimió (los que hizo falta descifrar se volcaron a un directorio temporal `0700` y se borraron). **VM:** las 11 variables enumeradas por nombre, ninguna vacía. **Vercel `storico-frontend`** (el front de producción, `storico.vercel.app`): 7 variables, todas en scope Production, ninguna vacía; `API_URL` apunta al host de la VM y `AUTH_URL` a `https://storico.vercel.app`; Preview y Development no tienen ninguna variable real. El par que la documentación exige que coincida **coincide**: `AUTH_SECRET` del front == `STORICO_AUTH_JWT_SECRET` de la VM. Dos observaciones medidas y **sin remediar, por decisión del operador**: ese valor de `AUTH_SECRET` es el mismo del `.env` de dev, o sea que dev y prod comparten el secreto de firma, y el cliente OAuth de Google también es el mismo en los dos entornos (el de GitHub sí está separado). **Vercel `storico-api`:** proyecto en desuso —su URL responde 404 y no es el endpoint— pero linkeado a `main`, así que deploya en cada push; tiene 9 variables en Production **y** Preview, entre ellas la misma `STORICO_DATABASE_URL` de Neon de producción y el `STORICO_AUTH_ALLOWED_ORIGINS` de prod, mientras que su `STORICO_QDRANT_URL` apunta a `localhost` y su par `AUTH_SECRET`/`STORICO_AUTH_JWT_SECRET` no coincide entre sí. El operador decidió el 2026-09-24 conservar ese proyecto como señal de que el build pasa y no remediar lo demás. **Actualización 2026-09-25:** el proyecto se **borró**, y la razón no fue la seguridad sino la capacidad — consumía **6.94 GB de los 10 GB** de Functions Storage del team, una cuota que se comparte entre proyectos y que al agotarse bloquea los deploys de todos, el front de producción incluido. Con el proyecto se fue la observación más incómoda de la auditoría: la `STORICO_DATABASE_URL` de producción ya no vive en ningún scope Preview. La otra observación sigue en pie a propósito (dev y prod comparten el secreto de firma y el cliente OAuth de Google). Detalle en `odd/tasks/retire-vercel-api-project.md`. **Y una tercera trampa de método, medida el 2026-09-25 al completar la copia local del entorno:** `vercel env pull` escribe `[SENSITIVE]` en los valores de tipo Secret, así que hashearlos compara una redacción y no un secreto — por esa vía el `AUTH_SECRET` del front mide 11 caracteres contra 44 del `STORICO_AUTH_JWT_SECRET` de la VM, un "no coinciden" falso. Lo delata un control de largos: los otros dos secretos del front también miden 11. Consecuencia: el par que esta fila dice que coincide **no es re-verificable por `env pull`**; la prueba válida es un request autenticado de punta a punta, o mirar los 401 del contenedor (0 en las últimas 2 000 líneas medidas ese día). Procedimiento, trampas de método y los lugares donde vive el secreto de firma en la nota "Auditoría de variables de entorno del deploy de Storico" del vault. La fila decía solo "en Vercel", donde el backend no está. |
| Rotación de la clave maestra | ✅ | **No se hace**, decidido por el operador el 2026-09-24: con una sola credencial de workspace cifrada en producción, rotar no hacía falta. El prefijo `v1:` del ciphertext queda en pie — es lo que la haría posible más adelante — y la herramienta sigue sin escribirse (`odd/tasks/encrypt-workspace-api-keys.md`). Si algún día se rota, el procedimiento no está escrito en ninguna parte: `docs/security.md` no menciona la rotación. El ítem llevaba un guión blando (U+00AD) en "Rotación", que hacía que `grep 'Rotación'` no lo encontrara. |
| `POST /api/v1/llm/test` ecoa el error de transporte | 🔲 | Sus cinco ramas devuelven `{e}`; admin-only, pero es la misma forma que se corrigió en el probe de modelos. Ver `odd/tasks/llm-probe-credential-leak.md`. |

## Observabilidad

| Ítem | Estado | Detalle |
|------|--------|---------|
| Monitoreo de errores (Sentry) | 🔲 | **Diferido a `1.0.0`**, la versión dedicada a observabilidad. El operador lo había fijado en `0.8.0` el 2026-09-24, lo corrió a `0.9.0` el 2026-09-25 cuando `0.8.0` se asignó al versionado de extracción, y volvió a correrlo el 2026-09-26: `v0.8.0` se cortó con la landing y el import de CSV, así que el versionado de extracción ocupó `0.9.0` y observabilidad pasó a `1.0.0`. El alcance reunido — lo que falta, las variables previstas y las decisiones por tomar — está en la nota "Sentry y correlation IDs en Storico" del vault. |
| Campos estructurados en los logs | ✅ | 28 llamadas a `logger.*` pasan `extra=`, así que un fallo llega con sus datos y no solo con un texto. |
| Correlation IDs para trazabilidad | 🔲 | **No existen.** `AGENTS.md` los anunciaba en su tabla de features y se corrigió ahí; un request no lleva identificador que lo siga de punta a punta. **Diferido a `1.0.0`** junto con Sentry, por el mismo motivo. |

## Infraestructura y costos

| Ítem | Estado | Detalle |
|------|--------|---------|
| Qdrant Cloud + adaptador de embeddings | ✅ | **Configurado y medido en producción el 2026-09-24**: `GET /api/v1/health/services` sobre el endpoint de prod devuelve `qdrant: ok` (465 ms) y `embeddings: ok` → `google` / `gemini-embedding-001` / 768 dims, con `vector_length: 768`. El cluster tiene `storico_extractions_prod` con 1 punto (la extracción real de la confirmación) y `storico_extractions` con 19 puntos de verificación. Decidido por el operador: **Google `gemini-embedding-001`** en prod, **sin fallback** en runtime y **una colección por entorno**. Ver `docs/deployment.md` y `odd/tasks/rag-per-environment.md`. |
| Dominio propio + SSL | ✅ | **No se hace**, decidido por el operador el 2026-09-23: producción ya sirve HTTPS sobre los dominios en uso —front `storico.vercel.app`, API en el contenedor de la VM— así que se sigue con lo que hay y no se compra dominio. El proyecto de Vercel `storico-api` existe y deploya en cada push, pero no es el endpoint en uso. **Actualización 2026-09-25:** ese proyecto se borró, así que producción se sirve en dos lugares y no en tres. |
| CI que construya el frontend | ✅ | `.github/workflows/ci.yml` corre `pnpm build` en el job del frontend, después de `tsc` y de `vitest`, así que un build roto frena el pull request. Medido antes de agregarlo: el build pasa sin `.env` y con el entorno pelado, porque el módulo de configuración del frontend se evalúa por request y no en build. Cuesta la corrida del build nada más — el job ya instalaba, tipaba y testeaba — y el artefacto viejo reutilizado en un despliegue manual queda fuera de su alcance, que es lo que advierte `docs/deployment.md`. |
| Tests de integración que no corren por defecto | ✅ | **Esta fila estaba MAL y quedó corregida el 2026-09-28.** Había escrito que "CI deselecciona 109 tests `integration`" y que `pytest.ini_options.addopts` trae `-m 'not integration'`. **Nunca abrí el archivo**: `backend/pytest.ini` no tiene `addopts` ni tuvo nunca ninguno (`grep -rn addopts backend/*.ini backend/*.toml` → vacío), y `AGENTS.md` tampoco menciona esa expresión. CI corre `pytest -q` pelado y por eso **ejecuta todo**: el job de backend de `#28` reportó **1004 passed, 18 skipped**. Lo que sí existe es un skip legítimo y autodecidido: 21 tests de `tests/test_integration/` que se saltean solos, 18 por opt-in con variable de entorno (`STORICO_TEST_LIVE_QDRANT` / `STORICO_TEST_LIVE_OLLAMA`, con la regla de que con la bandera puesta un servicio inalcanzable *rompe* la corrida en vez de saltearla) y 3 por Docker indisponible en local — esos 3, incluidos los dos de `test_migration_chain.py`, **corren en CI porque el runner de Ubuntu tiene Docker**. Era además una contradicción interna: la fila de arriba (`Suite de integración contra Postgres real`) ya decía ✅ con run id de evidencia y no la leí antes de escribir la mía. **Lo que sí estaba mal y se arregló en `#29`: 88 tests de `tests/test_api/` llevaban `@pytest.mark.integration` sin tocar ningún servicio.** No los estaba saltando nadie, pero el marker mentía sobre su costo y, peor, los sacaba del guard autouse `_forbid_real_qdrant_clients` (`tests/conftest.py:74-117`) sin necesitarlo: corrían sin la red de seguridad que existe justamente para no escribir en la colección real de Qdrant. Desmarcados archivo por archivo, verificando después de cada uno con `pytest -q` pelado (el comando idéntico de CI) que el guard nunca disparó. Cero tests eliminados: el diff son 29 líneas de decorator. **`test_migration_chain.py` sigue cubierto en CI**, que es lo que preocupaba de verdad.

## Producto (después de la evaluación)

| Ítem | Estado | Detalle |
|------|--------|---------|
| Copy pública que le toca cambiar al versionado de extracción (`0.9.0`) | 🔲 | **Tres claves hoy correctas que esa feature deja de serlo, y que por lo tanto son parte de su alcance, no un descuido posterior.** Decidido por el operador el 2026-09-27 al alinear la landing con la app (ver `odd/tasks/task-control-copy-truth.md`): `landing.faq.q4`/`a4`, `pages.privacy.retention` y `pages.docs.step_6`. La intención de producto que se anotó y **no** se implementó en ese slice es que el `title` y la `description` generados por el LLM dejen de ser editables en la app, que eliminar una tarea se convierta en **marcarla inválida**, y que el export seleccione una versión de la extracción con o sin tareas inválidas. Nada de eso existe hoy: `TASK_STATUSES` (`frontend/src/types/task.ts:1,7`) no tiene estado inválido ni versionado, y la copy corregida en `fix/task-control-copy-truth` describe la app actual a propósito, no el destino. Se registra acá además del documento de la feature porque esas tres claves **son superficie pública deployada**: cuando la feature cambie el comportamiento, la landing, la política de privacidad y la página de docs tienen que cambiar en el mismo release, y si no lo hacen el defecto vuelve por donde vino. |
| Conector Trello | 🔲 | **El conector no existe.** No hay adaptador de exportación ni paquete de conector: `backend/src/storico/infrastructure/` contiene solo `cache, crypto, database, llm, tasks, vector`, y `trello` sobrevive únicamente como cadena de formato. La opción "Trello" seleccionable en la página de Configuración se retira en la mitad de código de este lote: el esquema de la API la aceptaba pero el endpoint de exportación la rechazaba con 400. |
| Conectores Jira / GitHub Projects / Azure DevOps | 🔲 | V2/V3. |
| Adaptador de OpenAI con tests de construcción positiva | ✅ | El adaptador existe y la extracción lo construye por dos ramas: `openai` y proveedor personalizado (`backend/src/storico/infrastructure/tasks/extraction_task.py`). El test de construcción es `backend/tests/test_unit/test_llm_port_selection.py::TestKnownCloudProviders::test_openai_with_key_forwards_base_url`, que verifica el tipo del adaptador y que el `base_url` configurado llega a él. |
| `TaskEditor` mostraba errores de validación en inglés sin traducir | ✅ | **Cerrado el 2026-09-27 en `ca33e76`.** `TaskEditor.tsx:164` asignaba `'Required'` y `:166` armaba `` `Invalid transition from ${task.status} to ${status}` ``, ambos renderizados crudos en `<FieldError>`; el segundo además filtraba slugs de enum (`todo`, `done`) a copy visible. No se inventó ninguna cadena nueva donde ya existía una traducida: `taskEditor.invalid_transition` y `kanban.columns[status]` estaban en los dos catálogos, así que el mensaje se compone con separadores neutros al idioma. Se agregó **una** clave (`taskEditor.title_required`). El tooltip del lápiz reutilizó `taskEditor.title`, que ya era la etiqueta del propio dialog. **Causa raíz, que es lo que realmente se arregló:** los 30 y pico casos de `TaskEditor.test.tsx` renderizaban todos `locale="en"`; nada dibujó nunca el dialog en español, así que la suite no podía ver el defecto. Los dos tests nuevos afirman ausencia del inglés, no solo presencia del español, y se verificó que tienen dientes reintroduciendo cada cadena. |
| El banner de error del `TaskEditor` mostraba inglés construido por código | ✅ | **Cerrado el 2026-09-27 en `130b0dd`.** `TaskEditor.tsx:346` pasaba `friendlyMessage={saveError.message}`, y ese mensaje lo arma `buildErrorMessage` (`lib/api.ts:100`) devolviendo el `detail` del backend **literal**, o el primer `msg` de validación de FastAPI, o el `statusText` HTTP, o `HTTP {status}`. El backend manda prosa en inglés de verdad (`routes/workspaces.py`: `detail="Not a member of this workspace"`). No se inventó ninguna cadena: `taskEditor.error_save` ya estaba traducida en los dos idiomas y **no la consumía nadie** (`grep -rn error_save src/` sólo daba los catálogos). El detalle del servidor no se pierde: `rawDetail` ya se pasaba en `:347` y sigue reachable en el panel expandible. El test lo prueba en las dos direcciones -- afirma el titular español, niega el inglés como titular, y **después** de abrir "Mostrar detalles del error del backend" afirma que la frase inglesa sigue ahí. |
| Los otros 4 banners que muestran el inglés del backend, y el chokepoint que los produce | 🟡 | **Resuelto en mecanismo por `5412bb3`, residual en cobertura (WU3).** Medido antes de reescribir esta fila: de los 7 consumidores de `ErrorDisplay`, **4** pasan prosa del servidor (`ExportPanel.tsx:178`, `ImportStoriesDialog.tsx:374`, `StoryForm.tsx:522`, y `KanbanBoard.tsx:222` vía `extractErrorInfo` en `lib/error-info.ts:41-45`, que para `ApiRequestError` descarta el `fallbackMessage` del caller) y **3** pasan copy traducida. `ErrorDisplay.tsx:160` resultó ser **un chokepoint real**: los 7 meten `friendlyMessage` ahí y el componente ya tomaba `locale`. Así que la traducción se hizo en un lugar, sin tocar los consumidores, y con prioridad `headline por código → friendlyMessage del caller`. **Consecuencia: la pregunta de filosofía que planteaba esta fila ya no depende de decidir frase por frase en 4 pantallas.** Para un error con `error_code` conocido el titular es traducido y específico en las 7 superficies; para los 32 sitios que aún devuelven prosa sin código (401/403 de acceso sobre todo) esos 4 banners siguen mostrando inglés. **Lo que queda es WU3: darles código, no darles copy.** La decisión de fondo del owner quedó ejecutada en `5412bb3`: el detalle específico del servidor sigue alcanzable en el panel de crudo y en la línea de diagnóstico, pero dejó de ser el titular de una app que promete español (ADR-008). |
| El dropdown de estado marca la legalidad con un glifo `✓`/`✗` desnudo | 🔲 | **Mismo archivo, otra capa.** `TaskEditor.tsx:261` (sin cambiar a propósito en `ca33e76`) comunica si una transición es legal con el símbolo solo, dentro de un `<select>`, donde los lectores de pantalla lo anuncian de forma inconsistente y la opción deshabilitada ya hace el trabajo de señalizar. Las etiquetas sí están traducidas (`t.kanban.columns[s]`, `t.taskEditor.invalid_transition`), así que **no es un hueco de i18n**: es un símbolo cargando una distinción sin texto alternativo. |

## Tesis

| Ítem | Estado | Detalle |
|------|--------|---------|
| Juicio de expertos (n=6) | 🔲 | Scrum Masters y Product Owners; métricas TCR/TAS/IFI. |
| Comparativa manual vs automática | 🔲 | |

---

Este archivo lo mantiene quien despliega. Si un ítem se cierra, se marca acá y se deja el detalle en
el documento que le corresponda — no se abre una segunda lista.

## Bloqueo de despliegue (**D-a-3**): la migración `0028` no corre sobre la base de producción

**Descubierto el 2026-09-30, al cerrar el slice (a) de versionado de extracciones (PR #30). Ningún
otro archivo de este repo lo decía.**

`0028_extraction_versioning` lee `SELECT count(*) FROM extractions` y `SELECT count(*) FROM tasks`
antes de tocar el esquema, y **lanza `RuntimeError` si alguna de las dos tablas tiene una fila**
(decisión D11: no se hace backfill). `.github/workflows/deploy-backend.yml:101` ejecuta
`alembic upgrade head` en la ventana de mantenimiento de **todo** despliegue.

**La premisa ahora está medida en el lugar correcto (2026-09-30).** Esta fila afirmaba que producción
tiene datos citando la colección **Qdrant** `storico_extractions_prod`, medida el 2026-09-28. No es la
misma cosa: la guarda de `0028` cuenta las tablas **relacionales** de Neon. Conectando en lectura —solo
`SELECT count(*)`, sin DDL y sin imprimir la cadena de conexión—, medido directamente:

| Medido en producción | Valor |
| --- | --- |
| `alembic_version` | **`0027`** — `0028` es la siguiente y **se va a negar** |
| `extractions` | **17** (11 `failed`, 6 `completed`; span 2026-08-03 → 2026-09-24) |
| `tasks` | **42**, todos en `status = backlog` |
| `user_stories` / `projects` / `users` / `workspaces` | 6 / 3 / 3 / 4 |
| `workspace_llm_configs` | 4, ninguna con `provider` NULL |
| `task_invalidations` | **la tabla no existe** (consecuencia natural de estar en `0027`) |

Cada número salió de dos caminos SQL independientes que coinciden; donde no coincidían, la sonda se
descartó y no se reportó. La primera pasada usó `fetchval` sobre consultas de varias filas y devolvió
solo la primera: reportó `temperature` como reconstruible cuando no lo es.

Consecuencia exacta: **mergear `main` con `0028` dentro deja la API abajo a propósito.** El `docker stop`
ya ocurrió, la migración falla, y el `docker run` no llega — que es el comportamiento diseñado del
workflow (un fallo deja la API abajo antes que servir contra un esquema que no coincide), pero no es
un despliegue: es una caída.

`0028` es correcta como código; lo que faltaba era la decisión operativa. **Elegida el 2026-09-30:
camino 1, ventana de purga.** El merge y la purga siguen siendo dos decisiones ordinarias aparte, y
**ninguna se ejecutó**: nada se borró en producción al escribir esta línea.

Antes de elegir se midió el costo real de cada camino, y dos afirmaciones de este documento estaban
mal: D11 nombraba la columna equivocada y el costo de la purga estaba sobrevendido.

| Campo que una `0029` tendría que rellenar | Estado medido |
| --- | --- |
| `temperature` | clave presente en 17/17 filas pero **valor `null` JSON en 17/17** → no reconstruible. Ojo: `prompt_config ? 'temperature'` (clave) da 17 y `->> 'temperature' IS NOT NULL` (valor) da 0; mirar solo la clave saca la conclusión contraria |
| `provider` | **derivable por fila** por la cadena story → project → workspace → `workspace_llm_configs.provider` (17/17 con config). Es una *suposición*: la config de hoy no es necesariamente la del 3 de agosto |
| `version_number` | derivable ordenando `created_at` dentro de la historia; solo 2 historias tienen más de una extracción (9 y 4) |
| `tasks.extraction_id` | **esto es lo irreductible**: 28 de 42 tasks caen en historias con una sola extracción (derivable); **14 de 42** caen en las dos historias multi-run y no hay registro de qué run los produjo |

Y el costo de la purga era más chico y distinto del escrito: el `id` del punto de Qdrant **es** el
`extraction_id` (`qdrant_adapter.py:255`), y el payload se alcanza solo (`user_story_text`,
`tasks_summary`, `model_used`, `workspace_id`). Purgar no rompe el few-shot: lo que se pierde es
**procedencia**, no funcionamiento. Lo que se purga son 11 runs fallidos y 42 tareas que nunca salieron
de `backlog`.

Los tres caminos, ya evaluados:

1. **Ventana de purga.** ← **ELEGIDO.** Borrar los datos relacionales de `extractions`/`tasks` en Neon —
   y los puntos de Qdrant, extendido el 2026-09-30— antes de mergear, y dejar que `0028` corra sobre el
   par vacío. Es lo que el propio mensaje de la guarda indica. Sin respaldo: se reemplazó por inventario
   (ver el runbook). Corregido por medición: no "pierde la coherencia de los puntos de Qdrant", pierde
   la procedencia de 17 runs de prueba.
2. **Revisión de backfill aparte.** Descartada por costo: habría que afirmar tres cosas —`temperature`
   inventado en las 17 filas, `provider` por hipótesis de config actual, y un run elegido a mano para
   14/42 tasks— sobre datos que la medición describe como tráfico de prueba. Queda disponible si la
   evaluación de la tesis necesita conservar esos runs.
3. **No mergear todavía.** Dejar el PR abierto y que el slice (a) viva en la rama hasta que la
   evaluación de la tesis tenga datos propios que purgar sin costo. Es el camino que el plan de slices
   ya asumía al decir que (a) no está desplegado.

### Runbook del camino 1 (escrito, **no ejecutado**)

**Modificado el 2026-09-30 por decisión del owner: no se toma respaldo.** "No hay nada que salvar", así
que el paso de respaldo se reemplaza por **el inventario de lo que se destruye**, medido en lectura antes
de tocar nada. Es la única forma de que la pérdida quede registrada si alguien la pregunta después.

Inventario medido el 2026-09-30, en lectura, contra la base y el cluster de producción:

| Almacén | Contenido al momento de medir |
| --- | --- |
| `alembic_version` | `0027` |
| `extractions` | **17** — 11 `failed`, 6 `completed`; span 2026-08-03 23:16 → 2026-09-24 20:17 UTC |
| `tasks` | **42** — los 42 con `status = backlog`; ninguno avanzó nunca de ahí |
| `user_stories` / `projects` / `users` / `workspaces` | 6 / 3 / 3 / 4 |
| `workspace_llm_configs` | 4 (una con `provider = 'Nan'`) |
| Qdrant `storico_extractions_prod` | **1** punto, 768 dims |
| Qdrant `storico_extractions_dev` | **1** punto — esta colección **no existía el 2026-09-28**: alguien escribió desde dev contra el cluster de producción |
| Qdrant `storico_extractions` (legado) | **19** puntos |

0. **Ventana.** Avisar: entre el paso 2 y el 5 la API está caída o sirve contra un esquema viejo.
1. **Inventario, no respaldo.** Correr las dos mediciones de arriba y dejar los números acá antes de la
   purga. Sin esto, la destrucción no tiene testigo. (Opción conservadora si cambia el humor: un branch
   de Neon se toma en segundos y no gasta disco local — pero el owner decidió que no hace falta.)
2. **Purga relacional.** Mismo `DATABASE_URL` de la VM, en una sola transacción:
   `TRUNCATE TABLE tasks; TRUNCATE TABLE extractions;` — `tasks` primero porque referencia a
   `user_stories` igual que `extractions`, y ninguna de las dos es referenciada por nada más en `0027`
   (`task_invalidations` todavía no existe). Confirmar contando: ambos `count(*)` deben dar **0**.
2b. **Purga vectorial (nueva, por la misma decisión).** Borrar los puntos de las colecciones que se
   decida limpiar. Con las tres arriba, hay dos lecturas y **el owner tiene que elegir cuál**:
   - **Solo lo que sirve producción:** vaciar `storico_extractions_prod` (1 punto). Lo demás queda.
   - **Slate limpio:** vaciar las tres (`_prod` 1, `_dev` 1, la legado 19). Es lo que implica "limpiar
     Qdrant", y deja el few-shot sin un solo ejemplo hasta que haya runs nuevos.
   Mecanismo: `DELETE /collections/{name}/points` con `"filter": {}` (o `?wait=true`), o
   `client.delete(collection_name, points_selector=... )`. Verificado en esta máquina: la clave de
   `.env.prod.local` **lee** los conteos; si es una clave de sólo lectura, el borrado falla con 403 y
   hay que usar la clave del cluster.
3. **Estado desnormalizado (decisión propia, no obvia).** `user_stories.status` sigue diciendo
   `extracted` / `failed_extraction` sobre historias que se quedaron sin ninguna extracción, y
   `extraction_repository` reescribe ese campo en cada run. Si se quiere coherencia, el mismo
   `TRUNCATE` va acompañado de `UPDATE user_stories SET status = 'pending_extraction'`. Dejarlo como
   está también es una opción: la app muestra la historia sin tareas. Elegir y anotar acá.
4. **Mergear.** Recién con el par vacío: el merge a `main` dispara `deploy-backend.yml`, que corre
   `alembic upgrade head` y `0028` pasa la guarda. El orden es **purgar y después mergear**, nunca al
   revés: mergear primero deja el deploy fallando en cada push hasta que alguien purgue.
5. **Comprobación.** `alembic_version` = `0028`, `task_invalidations` existe, y los puntos de Qdrant
   (`storico_extractions_prod`: 1 punto, `storico_extractions`: 19 — medidos el 2026-09-28, no hoy)
   siguen ahí y siguen sirviendo few-shot: la purga relacional no los toca.

Lo que **no** hace este runbook: no borra `user_stories`, ni `projects`, ni `users`, ni —salvo que se
decida lo contrario en el paso 2b— las colecciones de Qdrant. Y no re-escribe la historia de la feature:
los 17 runs quedan registrados solo en el inventario de arriba.

### Hallazgo del inventario: dev escribe contra el cluster de producción

Medido el 2026-09-30 al contar las colecciones. `storico_extractions_dev` existe con 1 punto y **no
existía el 2026-09-28**. La razón no es un bug del adaptador: el `.env` de desarrollo de esta máquina
apunta `STORICO_QDRANT_URL` al **mismo cluster** que producción, y lo único que separa un entorno del
otro es el nombre de colección (`_dev` vs `_prod`). Con una sola variable mal escrita —o sin escribirla,
cayendo al default `storico_extractions` del adaptador, que es lo que explican los 19 puntos de esa
colección legado— una corrida de desarrollo escribe en el clúster de producción.

Esto no rompe nada hoy, pero acota el sentido de "una colección por entorno" que documenta
`docs/deployment.md`: hay separación lógica, no física. Mientras el plan de aislamiento siga siendo ese,
la purga vectorial tiene que nombrar las tres colecciones explícitamente, no "la de producción".

🔲 **Pendiente (decisión de diseño, no de esta purga):** si los entornos tienen que estar separados de
verdad, o se usa un cluster/API key distinto para dev, o se documenta que la separación es sólo de
nombre y se controla por ahí.

### Hallazgo lateral: un `provider` de producción vale literalmente `'Nan'`

Medido de paso, y verificado por `md5()` + `length()` sin imprimir valores: una de las cuatro filas de
`workspace_llm_configs` tiene `provider = 'Nan'`, y es el config al que caen los 2 runs con
`model_used = qwen3.8-flash`. Alguien guardó un `NaN` stringificado. No lo detecta ningún test: la
columna acepta cualquier string de hasta 50. Queda como pendiente propio, ajeno a `0.9.0`.

🔲 **Pendiente:** validar `provider` contra el enumerado de proveedores en la escritura de
`workspace_llm_configs`, o decidir si `'Nan'` es un valor admisible. Detalle arriba, en el hallazgo
lateral de D-a-3.
