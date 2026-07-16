# Testing

> Estrategia de tests para Storico.
> Última actualización: 2026-07-15

## Backend

### Stack

- **Runner**: pytest + pytest-asyncio
- **HTTP client**: httpx (AsyncClient con ASGI transport)
- **Database**: SQLite in-memory via aiosqlite
- **Auth token**: `dev-insecure-token-change-in-production`

### Cómo correr tests

```bash
# Todos los tests
make test-backend

# Tests unitarios (rápidos, sin servicios externos)
cd backend && .venv/bin/pytest -v -m unit

# Tests de integración (requieren DB)
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

### Convenciones

- `asyncio_mode = auto` — funciones async se detectan automáticamente
- Tests de API usan `db_session` para setup + `async_client` para requests
- Cada archivo de test cubre un recurso (projects, stories, tasks, etc.)
- Happy path + error path por endpoint

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
