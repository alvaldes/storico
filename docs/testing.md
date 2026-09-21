# Testing

> Estrategia de tests para Storico.
> Última actualización: 2026-07-15

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
cd backend && .venv/bin/pytest -v -m unit

# Tests de integración (requieren Docker)
cd backend && .venv/bin/pytest -v -m integration

# Tests de API
cd backend && .venv/bin/pytest tests/test_api/ -v

# Tests de un archivo específico
cd backend && .venv/bin/pytest tests/test_api/test_projects.py -v

# Con cobertura
cd backend && .venv/bin/pytest --cov=storico
```

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
# Tests unitarios (Zustand stores)
cd frontend && npx vitest run

# Tests con watch
cd frontend && npx vitest

# Build check (smoke test)
cd frontend && npm run build
```

### Tests existentes

- `src/stores/__tests__/authStore.unit.test.ts` — Tests del store de autenticación

### Pendiente

- Testing de componentes React (Vitest + Testing Library)
- Testing de stores Zustand adicionales
- E2E testing (Playwright o similar — futuro)

## Estrategia General

| Area | Enfoque | Prioridad |
|------|---------|-----------|
| Backend API | Integración con httpx + SQLite in-memory | ✅ Implementado |
| Backend repositorios | Unitarios con SQLAlchemy | ✅ Implementado |
| Backend servicios | Unitarios con mocks | ✅ Implementado |
| Backend unitarios | Tests aislados sin DB | ✅ Implementado |
| Frontend stores | Unitarios con Vitest | 🔶 Parcial |
| Frontend componentes | Testing Library | 🔲 Pendiente |
| E2E | Playwright | 🔲 V2 |
