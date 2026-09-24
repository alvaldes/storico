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
| Auditoría de variables de entorno | 🔲 | Son **dos** lugares, no uno: el `.env` del backend en la VM (`/home/ubuntu/storico/backend/.env`, fuera del control de versiones) y el proyecto de Vercel, que solo lleva las variables del frontend. Que ninguna clave de desarrollo quede en ninguno de los dos. La fila decía solo "en Vercel", donde el backend no está. |
| Rota­ción de la clave maestra | 🔲 | El prefijo `v1:` del ciphertext existe para permitirla; la herramienta no está escrita. |
| `POST /api/v1/llm/test` ecoa el error de transporte | 🔲 | Sus cinco ramas devuelven `{e}`; admin-only, pero es la misma forma que se corrigió en el probe de modelos. Ver `odd/tasks/llm-probe-credential-leak.md`. |

## Observabilidad

| Ítem | Estado | Detalle |
|------|--------|---------|
| Monitoreo de errores (Sentry) | 🔲 | |
| Campos estructurados en los logs | ✅ | 28 llamadas a `logger.*` pasan `extra=`, así que un fallo llega con sus datos y no solo con un texto. |
| Correlation IDs para trazabilidad | 🔲 | **No existen.** `AGENTS.md` los anunciaba en su tabla de features y se corrigió ahí; un request no lleva identificador que lo siga de punta a punta. |

## Infraestructura y costos

| Ítem | Estado | Detalle |
|------|--------|---------|
| Qdrant Cloud + adaptador de embeddings | 🔲 | El RAG degrada con gracia si falta; en producción conviene decidir si se usa. |
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
