# Testing

> Estrategia de tests para Storico.
> Última actualización: 2026-09-23

## Backend

### Stack

- **Runner**: pytest + pytest-asyncio
- **HTTP client**: httpx (AsyncClient con ASGI transport)
- **Database**: SQLite in-memory via aiosqlite; Postgres 16 real solo en los tests de integración
- **Auth token**: `dev-insecure-token-change-in-production`

### Cómo correr tests

```bash
# Todos los tests
make test-backend

# Tests unitarios (rápidos, sin servicios externos)
cd backend && python -m pytest -v -m unit

# Tests de integración (requieren Docker)
cd backend && python -m pytest -v -m integration

# Tests de API
cd backend && python -m pytest tests/test_api/ -v

# Tests de un archivo específico
cd backend && python -m pytest tests/test_api/test_projects.py -v

# Con cobertura
cd backend && python -m pytest --cov=storico
```

> **Nota**: `pytest-cov` **no es confiable en este entorno** — reporta como faltantes líneas que un
> `sys.settrace` ve ejecutar (p. ej. `dependencies.py:259-270`, contradiciendo tests que pasan). Repro:
> `COVERAGE_FILE=/tmp/x python -m pytest tests/test_api/test_stories.py --cov=storico.api`. No hay
> variables `COVERAGE_*` ni `.coveragerc` que lo expliquen. Cross-checkear con un tracer antes de
> concluir algo por coverage.

### Estructura de tests

```
backend/tests/
├── conftest.py                        # Fixtures globales (app, client, db_session, engine)
├── test_health.py                     # Health check endpoint
├── test_api/                          # Tests de API routes
│   ├── test_auth.py
│   ├── test_projects.py
│   ├── test_stories.py
│   ├── test_tasks.py
│   ├── test_extractions.py
│   ├── test_extraction.py
│   └── test_users.py
├── test_repositories/                 # Tests de repositorios SQLAlchemy
│   ├── test_project_repository.py
│   ├── test_task_repository.py
│   ├── test_user_repository.py
│   ├── test_user_story_repository.py
│   └── test_extraction_repository.py
├── test_services/                     # Tests de servicios
│   └── test_extraction_service.py
├── test_integration/                  # Tests contra servicios reales (Docker)
│   └── test_projects_integration.py   # Postgres 16 en testcontainer
└── test_unit/                         # Tests unitarios
    ├── test_embedding_service.py
    ├── test_ollama_adapter.py
    ├── test_prompt_manager.py
    ├── test_task_parser.py
    └── test_vector_store.py
```

### Fixtures principales (conftest.py)

| Fixture | Descripción |
|---------|-------------|
| `app` | Instancia de FastAPI via `create_app()` |
| `test_engine` | SQLite in-memory, create_all + drop_all |
| `async_client` | httpx AsyncClient con ASGI transport + DB overrides |
| `db_session` | AsyncSession para setup de datos en tests |

### Marcadores

| Marker | Propósito |
|--------|-----------|
| `unit` | Tests rápidos sin dependencias externas |
| `integration` | Tests que requieren DB u otros servicios |

### Tests de integración (Docker)

`tests/test_integration/` levanta servicios reales con `testcontainers`. Se
ejecutan solos cuando hay un daemon de Docker accesible: en GitHub Actions el
runner lo tiene, así que **corren en CI**; en una máquina sin Docker el módulo se
salta (no falla) según `_docker_reachable()`. Que se salten en tu máquina es
normal y también significa que un error ahí solo aparece en CI.

**El primer run del CI puede salir rojo por infraestructura, no por código.**
`tests/test_integration/test_projects_integration.py` se saltea **localmente** porque el daemon de
Docker no responde, y en los runners de GitHub Docker sí está, así que va a intentar levantar
`PostgresContainer("postgres:16-alpine")`: el total esperado ahí al retirar el backlog (2026-09-23)
era 733 passed, sin skips, o un fallo de pull de imagen. La condición del skip se dejó intacta **a
propósito**, para no maquillar el resultado: un rojo por infraestructura es señal, y esconderla
tocando la condición no lo arregla.

- El contenedor usa su driver **sincrónico** y el test convierte la URL a
  `postgresql+asyncpg` por su cuenta. Las versiones de `testcontainers` que
  verifican readiness con un engine síncrono de SQLAlchemy se rompen
  (`MissingGreenlet`) si el contenedor recibe un driver async.
- Los fixtures async de scope `module` declaran `loop_scope="module"` (igual que
  el marker del test que los usa), porque pytest-asyncio le da un event loop
  nuevo a cada test y las conexiones de asyncpg quedan atadas a un loop muerto.
- SQLite **no** hace cumplir las foreign keys (el `PRAGMA foreign_keys` viene
  apagado), así que un dato sembrado que no respeta una FK pasa en los 730 tests
  y falla en Postgres. Para reproducirlo localmente sin Docker, corré el cuerpo
  del test contra `sqlite+aiosqlite://` con un listener `connect` que ejecute
  `PRAGMA foreign_keys=ON`; el error aparece idéntico.
- Los tipos enum de Postgres los crea Alembic (`0016`, `0017`) y los modelos los
  declaran con `create_type=False`, así que un esquema armado con `create_all`
  necesita crearlos antes: eso hace `_create_pg_enum_types` en el fixture.

### Convenciones

- `asyncio_mode = auto` — funciones async se detectan automáticamente
- Tests de API usan `db_session` para setup + `async_client` para requests
- Cada archivo de test cubre un recurso (projects, stories, tasks, etc.)
- Happy path + error path por endpoint

### Warnings de la suite

La suite completa emite **un** `RuntimeWarning` — `coroutine 'Connection._cancel' was never awaited` — y su
conteo no es una propiedad del árbol: cuatro corridas seguidas hoy dieron 1, 1, 1 y 1, y una medición
anterior del mismo árbol dio 1, 1, 1 y 2. Lo que sí es estable es el test al que se atribuye
(`test_repositories/test_custom_provider_repo.py::test_list_is_empty_for_a_fresh_workspace`); lo que se
mueve es el frame de SQLAlchemy que lo reporta (`orm/loading.py` en una corrida, `sql/compiler.py` en las
otras tres). Para comparar un candidato contra su base, entonces, el conteo de warnings **no sirve como
instrumento**.

Eso importa por una razón concreta: **nada gatea sobre los warnings**. `backend/pytest.ini` no declara
`filterwarnings`, CI corre `pytest -q` sin `-W error`, y ningún script compara el conteo. Un warning nuevo
no rompe ningún gate: el único instrumento que lo ve es leer la salida. Si querés que un warning nuevo
frene algo, hay que agregar el gate, que hoy no existe.

Y hay una trampa al atribuirlo a un cambio: el mismo árbol, corrido con el `.env` presente (que apunta a la
base remota) y sin él, no siempre reporta lo mismo. Compará candidato y base en el mismo entorno.

## Frontend

### Stack

- **Runner**: Vitest
- **Testing library**: @testing-library/react + jest-dom
- **Setup**: `src/test/setup.ts` (importa jest-dom matchers)

### Cómo correr tests

```bash
# Tests unitarios (Zustand stores y componentes)
cd frontend && pnpm exec vitest run

# Tests con watch
cd frontend && pnpm exec vitest

# Build check (smoke test)
cd frontend && pnpm run build
```

### Tests existentes

- `src/stores/__tests__/authStore.unit.test.ts` — Tests del store de autenticación
- `src/components/**/__tests__/*.test.tsx` — Tests de componentes React con
  Testing Library (`@testing-library/react` + `jest-dom`, ya en `devDependencies`)

### Pendiente

- Testing de stores Zustand adicionales
- E2E automatizado en CI: el guion manual existe (abajo) y se ejecutó una vez, pero no hay runner en el repo

#### Brechas de verificación abiertas (medidas, no opiniones)

1. **El toast de fallo asume que el render de `pending` se observó antes de asentarse.** La autoridad
   única del toast de fallo es el `useEffect` de `StoryDetail`, que dispara sólo si
   `prevExtractionStatus === 'pending'` cuando la extracción se asienta. El test de componente arma esa
   secuencia a mano (render `pending` → asentar). En producción el rechazo del POST pasa por I/O, así
   que React flushea el render de `pending` primero; pero con updates completamente batcheados el toast
   no saldría, y **ningún test cubre el caso colapsado**. Es preexistente: el `catch` que se borró era
   inalcanzable, así que tampoco lo cubría. **Actualización 2026-09-24:** el render de `pending` sí se
   observó en un navegador real (paso 7 del guion), así que el orden que asume el `useEffect` ocurre en
   la práctica; el caso colapsado sigue sin cobertura de test.
2. **La verificación end-to-end es manual, no automatizada.** Todo el frontend está verificado con
   vitest + jsdom y APIs mockeadas, y **no hay ejecución en navegador en CI**. Los specs de
   `frontend/e2e/` no eran ejecutables (`@playwright/test` nunca fue dependencia) y se retiraron el
   2026-09-24: además de no correr, manejaban un editor de ejemplos few-shot que ya no existe. El
   2026-09-24 esa brecha se cubrió **a mano, una vez**, con el guion de abajo. Lo que sigue abierto:
   que eso corra en CI, más de un navegador o viewport, y el camino de fallo de la extracción.

## Estrategia General

| Area | Enfoque | Prioridad |
|------|---------|-----------|
| Backend API | Integración con httpx + SQLite in-memory | ✅ Implementado |
| Backend repositorios | Unitarios con SQLAlchemy | ✅ Implementado |
| Backend servicios | Unitarios con mocks | ✅ Implementado |
| Backend unitarios | Tests aislados sin DB | ✅ Implementado |
| Frontend stores | Unitarios con Vitest | 🔶 Parcial |
| Frontend componentes | Testing Library | ✅ Implementado |
| E2E | ego-browser, guion manual | 🔶 Guion documentado y ejecutado una vez (2026-09-24); sin runner en CI |

## Verificación en navegador real (ego-browser)

Guion manual, ejecutado completo el **2026-09-24** contra el servidor de desarrollo. No es
automatizable tal cual: necesita una sesión real de OAuth y el navegador de ego-browser. Reemplaza al
spec de Playwright que se retiró.

### Preparación

```bash
# Backend. El basicConfig no es decorativo: con uvicorn pelado, los logger.info de la
# aplicación se descartan y no se ve, por ejemplo, la inyección del few-shot.
cd backend && set -a; . ../.env; set +a
python -c "
import logging, uvicorn
logging.basicConfig(level=logging.INFO, format='%(levelname)s %(name)s %(message)s')
uvicorn.run('storico.api.app:create_app', factory=True, host='127.0.0.1', port=8000)
"

# Frontend
cd frontend && pnpm dev
```

Precondiciones: base en `alembic head`, Ollama arriba con `nomic-embed-text` (los embeddings de dev
salen de ahí) y el `.env` fijando `STORICO_QDRANT_COLLECTION=storico_extractions_dev`.

### Los pasos

| # | Paso | Qué prueba |
| --- | --- | --- |
| 1 | Abrir `/en/dashboard` sin sesión | Redirige a `/en/login` |
| 2 | Iniciar sesión con Google o GitHub | OAuth real contra el backend |
| 3 | `/en/dashboard` | Hidratación de islas + datos reales de la API (workspace, rol, métricas, historia reciente) |
| 4 | Navegar Dashboard → Stories → Dashboard → Kanban → Settings por el sidebar | View Transitions: las islas se desmontan y remontan; títulos y URLs correctos |
| 5 | Settings del workspace | Config de LLM (proveedor, modelo, temperatura, tokens, base URL) y Prompt Configuration con **Automatic few-shot examples** (máximo de ejemplos, umbral) |
| 6 | Abrir una historia | Lista y detalle: estado, historia completa y partes (Actor / Feature / Benefit) |
| 7 | **Extract Tasks** | `202` → `Extracting...` → `Extracted`, tareas renderizadas y un punto nuevo en Qdrant |
| 8 | Kanban: arrastrar una tarjeta desde el handle | Drag & drop persistido (`PUT /api/v1/tasks/<id>` → `200`) y sobrevive a una recarga completa |
| 9 | `/en/status` y `/es/status` **sin sesión** | El documento de diagnósticos completo: banner, las **5** filas (`API Server`, `LLM Runner`, `Database`, `Database schema`, `Vector Store`) y "Última actualización". Un SSR roto en Astro **no** muestra error: la página queda con la navbar y sin cuerpo (ver trampas) |
| 10 | `/en/api` y `/es/api` **sin sesión** | Cada path listado existe en el backend: `curl -X POST -o /dev/null -w '%{http_code}' <path>` da `401`, nunca `404` |

### Trampas medidas

| Trampa | Qué pasa realmente |
| --- | --- |
| **El drag & drop "no funciona"** | El handle es el **ícono de grip de 16×16** de la esquina superior izquierda: `KanbanCard.tsx` aplica `dragHandleProps` ahí, no al cuerpo. Arrastrar el cuerpo no hace nada y parece un defecto. Hacen falta además un micro-movimiento inicial y pasos lentos |
| El detalle de la historia aparece vacío | Es **latencia**, no un fallo. En dev, las llamadas por el proxy de Astro tardan entre 1,7 s y 31,8 s. Esperá y volvé a mirar antes de concluir nada |
| "Loading settings..." eterno | Ídem: la página sondea los modelos del proveedor (`POST …/settings/llm/models`) antes de pintar |
| `text=Extract Tasks` matchea dos elementos | El botón y el párrafo del estado vacío. Usá `loc=role:button[name="Extract Tasks"]` |
| `loc=href:/en/stories` matchea dos | El link del sidebar y el del encabezado de "Recent stories". Usá `>> nth=0` |
| Cada llamada de lista cuesta un `307` | El frontend pide `/api/v1/stories?page=1` sin barra final y FastAPI redirige a `/api/v1/stories/`. Duplica los viajes en un dev ya lento |
| El tablero se corta a la derecha | Es scroll horizontal: con un viewport de 1340 px la columna `Done` queda fuera de pantalla |
| **Una página pública "se ve vacía"** | Antes de culpar a la latencia, distinguí un SSR truncado: en dev Astro streamea y corta en el punto exacto donde revienta, **sin marca de error**. `curl -s http://localhost:4321/en/status | grep -c '</html>'` da `0` cuando el render murió y `1` cuando está sano. `/en/status` estuvo roto así del 2026-09-20 al 2026-09-24 |
| `curl \| grep 'TypeError'` no encuentra nada | Por lo mismo: el error viaja por el canal de errores de Vite (WebSocket), no en el HTML. Buscalo en la consola del navegador o en la terminal de `pnpm dev` |

### Qué NO cubre

- No corre en CI ni en ningún runner: es un guion manual.
- Un solo navegador (ego-browser, Chromium 152) y un viewport.
- El camino de fallo de la extracción, y por lo tanto el toast de fallo.
- El bundle de producción: se ejercitó el servidor de desarrollo. CI corre `pnpm build` como gate, pero
  el artefacto no se probó acá.

Los pasos 9 y 10 se agregaron el 2026-09-24, después de encontrar `/en/status` roto desde el
2026-09-20: las tres superficies públicas (`/status`, `/api` y la versión del documento OpenAPI)
mentían y **ninguna** aparecía en este guion ni en el CI. `tsc`, `vitest` y `astro build` pasaban
con las tres presentes. Un `TypeError` dentro de un `.astro` que rompe la página entera no lo ve
ninguna de esas tres gates; sí lo ve el paso 9.
