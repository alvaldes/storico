<p align="center">
  <img src="frontend/public/favicon.svg" alt="Storico" width="80" />
</p>

<h2 align="center">Storico</h2>

<p align="center">
  <strong>LLM-powered tool that automates decomposing natural language user stories into structured Kanban tasks.</strong><br>
  Built with FastAPI (hexagonal), Astro + React islands, and Ollama. Thesis project at UTM, Oaxaca.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License" />
  <img src="https://img.shields.io/badge/python-3.12%2B-blue" alt="Python" />
  <img src="https://img.shields.io/badge/Astro-5.x-blueviolet" alt="Astro" />
  <img src="https://img.shields.io/badge/status-thesis-yellow" alt="Status" />
</p>

---

## Project Status

> **MVP stage — experimental evaluation pending.** Storico is a thesis research project in active development. The core extraction pipeline works (Ollama → prompts validated with LocalLLM-DataForge), but the formal evaluation — expert judgment with 6 Scrum Masters/POs and TCR/TAS/IFI metrics — is yet to be conducted. Expect rough edges, missing features, and breaking changes as the research progresses.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/install/)
- [Python](https://www.python.org/) 3.12+ (for backend development outside Docker)
- [Node.js](https://nodejs.org/) 20+ and [pnpm](https://pnpm.io/) 10+ (for frontend development — pnpm is the only package manager this repo uses)

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env

# 2. Build and start all services
make build
make up

# 3. Verify services are healthy
make ps

# 4. Run backend tests
make test-backend

# 5. Run frontend build check
make test-frontend
```

The API will be available at **<http://localhost:8000>** and the frontend at **<http://localhost:4321>**.

## Architecture

See [AGENTS.md](./AGENTS.md) for the full project definition, including:

- Hexagonal architecture (backend)
- Astro + React islands with View Transitions (frontend)
- Docker Compose orchestration with 4 services
- LLM integration (Ollama, OpenAI, Anthropic, Gemini, and custom OpenAI-compatible endpoints)

## Environment Variables

| Variable                         | Default                                                       | Description                                   |
| -------------------------------- | ------------------------------------------------------------- | --------------------------------------------- |
| `STORICO_DATABASE_URL`           | `postgresql+asyncpg://storico:storico@localhost:5432/storico` | PostgreSQL connection string (asyncpg driver) |
| `STORICO_LOG_LEVEL`              | `INFO`                                                        | Root logging level for application logs       |
| `STORICO_QDRANT_URL`             | `http://localhost:6333`                                       | Qdrant vector store URL                       |
| `STORICO_QDRANT_API_KEY`         | (unset)                                                       | Qdrant API key for a managed cluster          |
| `STORICO_QDRANT_COLLECTION`      | `storico_extractions`                                         | Collection holding extraction vectors. **Set one per environment** — a collection belongs to the embedding model that fills it (dev `storico_extractions_dev`, prod `storico_extractions_prod`) |
| `STORICO_OLLAMA_HOST`            | `http://localhost:11434`                                      | Ollama host used by the default provider      |
| `STORICO_EMBEDDING_PROVIDER`     | `ollama`                                                      | Embedding backend: ollama, google or openai   |
| `STORICO_EMBEDDING_MODEL`        | `nomic-embed-text`                                            | Embedding model. **Only the Ollama provider reads this** — google and openai have their own variables below |
| `STORICO_EMBEDDING_DIMENSIONS`   | `768`                                                         | Vector size; must match the embedding model and the collection |
| `STORICO_GOOGLE_EMBEDDING_MODEL` | `gemini-embedding-001`                                        | Embedding model for the google provider. `text-embedding-004` is retired and answers 404 |
| `STORICO_OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small`                                      | Embedding model for the openai provider       |
| `STORICO_GOOGLE_API_KEY`         | (unset)                                                       | Google API key for the google provider        |
| `STORICO_OPENAI_API_KEY`         | (unset)                                                       | OpenAI API key for the openai provider        |
| `STORICO_AUTH_JWT_SECRET`        | `dev-insecure-token-change-in-production`                     | Secret used to verify proxy-generated JWTs    |
| `STORICO_AUTH_ALLOWED_ORIGINS`   | `http://localhost:4321`                                       | Comma-separated allowed CORS origins          |
| `STORICO_ENCRYPTION_KEY`         | (no default)                                                  | Required to store workspace credentials       |

## Project Structure

```
storico/
├── backend/             # FastAPI hexagonal architecture
│   ├── src/storico/     # Application source
│   │   ├── api/         # API routes and middlewares
│   │   ├── application/ # Use cases
│   │   ├── domain/      # Entities, ports, services
│   │   ├── infrastructure/  # Adapters (DB, LLM, etc.)
│   │   └── config/      # Settings
│   └── tests/           # Pytest suite
├── frontend/            # Astro + React islands
│   ├── src/
│   │   ├── layouts/     # MainLayout, AuthLayout
│   │   ├── components/  # React islands + Astro components
│   │   ├── pages/       # Astro routes
│   │   ├── stores/      # Zustand state
│   │   ├── lib/         # Utilities (api, cn)
│   │   └── types/       # TypeScript interfaces
│   └── public/          # Static assets
├── docker-compose.yml   # 4 services: API, Ollama, Postgres, Qdrant
├── Makefile             # build, up, down, logs, test targets
└── .env.example         # Environment variable template
```

## Development

### Makefile targets

```bash
make build         # Build all Docker images
make up            # Start all services (detached)
make down          # Stop all services
make logs          # Tail logs (make logs storico-api for one service)
make restart       # Restart all services
make ps            # List running services
make test-backend  # Run pytest
make test-frontend # Run frontend build check
make shell-api     # Bash inside the API container
make clean         # Stop + remove volumes (destructive)
make setup         # Install all deps + build images
```

### Backend (outside Docker)

The canonical environment is the conda env `storico` (Python 3.12). There is no
`.venv` in this repository; see `AGENTS.md` for the full contract.

```bash
# Bootstrap, once, from the repo root
conda create -n storico python=3.12 -y
conda activate storico

cd backend
python -m pip install -e ".[dev]"

# Canonical commands, from backend/ with the environment active
python -m pytest -v                       # full suite
python -m pytest -v -m unit               # unit tests (fast, no external services)
python -m uvicorn storico.api.app:create_app --factory --port 8000   # dev server

# Environment not active (agents, scripts)
make test-backend PYTHON="conda run -n storico python"
```

### Frontend (outside Docker)

```bash
cd frontend
pnpm install
pnpm run dev       # http://localhost:4321
pnpm run build     # Production build
```

## Documentation

For detailed technical documentation, see the [`docs/`](./docs/) folder:

- [Architecture](./docs/architecture.md) — ADRs, stack, diagrama de capas
- [Database](./docs/database.md) — Schema, tablas, migraciones
- [API Reference](./docs/api.md) — Endpoints REST
- [Testing](./docs/testing.md) — Estrategia de tests
- [Frontend State](./docs/frontend-state.md) — Stores Zustand
- [Deployment](./docs/deployment.md) — Docker Compose + producción
- [i18n](./docs/i18n.md) — Internacionalización
- [Security](./docs/security.md) — Auth y permisos

## License

MIT — Angel Luis Valdés Sánchez, Universidad Tecnológica de la Mixteca (2026)
