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
| Auditoría de variables de entorno | ✅ | Son **dos** lugares, no uno: el `.env` del backend en la VM (`/home/ubuntu/storico/backend/.env`, fuera del control de versiones) y los proyectos de Vercel, que solo llevan variables del frontend. **Cerrada el 2026-09-24**, medida contra la Vercel CLI, el `.env` de dev del repo y el `.env` de la VM por SSH: los valores se compararon por hash SHA-256 y ninguno se imprimió (los que hizo falta descifrar se volcaron a un directorio temporal `0700` y se borraron). **VM:** las 11 variables enumeradas por nombre, ninguna vacía. **Vercel `storico-frontend`** (el front de producción, `storico.vercel.app`): 7 variables, todas en scope Production, ninguna vacía; `API_URL` apunta al host de la VM y `AUTH_URL` a `https://storico.vercel.app`; Preview y Development no tienen ninguna variable real. El par que la documentación exige que coincida **coincide**: `AUTH_SECRET` del front == `STORICO_AUTH_JWT_SECRET` de la VM. Dos observaciones medidas y **sin remediar, por decisión del operador**: ese valor de `AUTH_SECRET` es el mismo del `.env` de dev, o sea que dev y prod comparten el secreto de firma, y el cliente OAuth de Google también es el mismo en los dos entornos (el de GitHub sí está separado). **Vercel `storico-api`:** proyecto en desuso —su URL responde 404 y no es el endpoint— pero linkeado a `main`, así que deploya en cada push; tiene 9 variables en Production **y** Preview, entre ellas la misma `STORICO_DATABASE_URL` de Neon de producción y el `STORICO_AUTH_ALLOWED_ORIGINS` de prod, mientras que su `STORICO_QDRANT_URL` apunta a `localhost` y su par `AUTH_SECRET`/`STORICO_AUTH_JWT_SECRET` no coincide entre sí. El operador decidió el 2026-09-24 conservar ese proyecto como señal de que el build pasa y no remediar lo demás. Procedimiento, trampas de método y los lugares donde vive el secreto de firma en la nota "Auditoría de variables de entorno del deploy de Storico" del vault. La fila decía solo "en Vercel", donde el backend no está. |
| Rotación de la clave maestra | ✅ | **No se hace**, decidido por el operador el 2026-09-24: con una sola credencial de workspace cifrada en producción, rotar no hacía falta. El prefijo `v1:` del ciphertext queda en pie — es lo que la haría posible más adelante — y la herramienta sigue sin escribirse (`odd/tasks/encrypt-workspace-api-keys.md`). Si algún día se rota, el procedimiento no está escrito en ninguna parte: `docs/security.md` no menciona la rotación. El ítem llevaba un guión blando (U+00AD) en "Rotación", que hacía que `grep 'Rotación'` no lo encontrara. |
| `POST /api/v1/llm/test` ecoa el error de transporte | 🔲 | Sus cinco ramas devuelven `{e}`; admin-only, pero es la misma forma que se corrigió en el probe de modelos. Ver `odd/tasks/llm-probe-credential-leak.md`. |

## Observabilidad

| Ítem | Estado | Detalle |
|------|--------|---------|
| Monitoreo de errores (Sentry) | 🔲 | **Diferido a `0.8.0`**, la versión dedicada a observabilidad, decidido por el operador el 2026-09-24. El alcance reunido — lo que falta, las variables previstas y las decisiones por tomar — está en la nota "Sentry y correlation IDs en Storico — alcance de 0.8.0" del vault. |
| Campos estructurados en los logs | ✅ | 28 llamadas a `logger.*` pasan `extra=`, así que un fallo llega con sus datos y no solo con un texto. |
| Correlation IDs para trazabilidad | 🔲 | **No existen.** `AGENTS.md` los anunciaba en su tabla de features y se corrigió ahí; un request no lleva identificador que lo siga de punta a punta. **Diferido a `0.8.0`** junto con Sentry. |

## Infraestructura y costos

| Ítem | Estado | Detalle |
|------|--------|---------|
| Qdrant Cloud + adaptador de embeddings | ✅ | **Configurado y medido en producción el 2026-09-24**: `GET /api/v1/health/services` sobre el endpoint de prod devuelve `qdrant: ok` (465 ms) y `embeddings: ok` → `google` / `gemini-embedding-001` / 768 dims, con `vector_length: 768`. El cluster tiene `storico_extractions_prod` con 1 punto (la extracción real de la confirmación) y `storico_extractions` con 19 puntos de verificación. Decidido por el operador: **Google `gemini-embedding-001`** en prod, **sin fallback** en runtime y **una colección por entorno**. Ver `docs/deployment.md` y `odd/tasks/rag-per-environment.md`. |
| Dominio propio + SSL | ✅ | **No se hace**, decidido por el operador el 2026-09-23: producción ya sirve HTTPS sobre los dominios en uso —front `storico.vercel.app`, API en el contenedor de la VM— así que se sigue con lo que hay y no se compra dominio. El proyecto de Vercel `storico-api` existe y deploya en cada push, pero no es el endpoint en uso. |
| CI que construya el frontend | ✅ | `.github/workflows/ci.yml` corre `pnpm build` en el job del frontend, después de `tsc` y de `vitest`, así que un build roto frena el pull request. Medido antes de agregarlo: el build pasa sin `.env` y con el entorno pelado, porque el módulo de configuración del frontend se evalúa por request y no en build. Cuesta la corrida del build nada más — el job ya instalaba, tipaba y testeaba — y el artefacto viejo reutilizado en un despliegue manual queda fuera de su alcance, que es lo que advierte `docs/deployment.md`. |

## Producto (después de la evaluación)

| Ítem | Estado | Detalle |
|------|--------|---------|
| Conector Trello | 🔲 | **El conector no existe.** No hay adaptador de exportación ni paquete de conector: `backend/src/storico/infrastructure/` contiene solo `cache, crypto, database, llm, tasks, vector`, y `trello` sobrevive únicamente como cadena de formato. La opción "Trello" seleccionable en la página de Configuración se retira en la mitad de código de este lote: el esquema de la API la aceptaba pero el endpoint de exportación la rechazaba con 400. |
| Conectores Jira / GitHub Projects / Azure DevOps | 🔲 | V2/V3. |
| Adaptador de OpenAI con tests de construcción positiva | ✅ | El adaptador existe y la extracción lo construye por dos ramas: `openai` y proveedor personalizado (`backend/src/storico/infrastructure/tasks/extraction_task.py`). El test de construcción es `backend/tests/test_unit/test_llm_port_selection.py::TestKnownCloudProviders::test_openai_with_key_forwards_base_url`, que verifica el tipo del adaptador y que el `base_url` configurado llega a él. |

## Tesis

| Ítem | Estado | Detalle |
|------|--------|---------|
| Juicio de expertos (n=6) | 🔲 | Scrum Masters y Product Owners; métricas TCR/TAS/IFI. |
| Comparativa manual vs automática | 🔲 | |

---

Este archivo lo mantiene quien despliega. Si un ítem se cierra, se marca acá y se deja el detalle en
el documento que le corresponda — no se abre una segunda lista.
