# Storico

> LLM-powered tool that automates decomposing natural language user stories into structured Kanban tasks.

Storico is a thesis project for the Master's in Software Engineering at **Universidad Tecnológica de la Mixteca (UTM)**, Oaxaca, México.

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/install/)
- [Python](https://www.python.org/) 3.12+ (for backend development outside Docker)
- [Node.js](https://nodejs.org/) 20+ (for frontend development)

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
- Docker Compose orchestration with 5 services
- LLM integration (Ollama first, OpenAI/Anthropic later)

## Environment Variables

| Variable                  | Default                                                           | Description                  |
| ------------------------- | ----------------------------------------------------------------- | ---------------------------- |
| `STORICO_DATABASE_URL`    | `postgresql+asyncpg://storico:storico_dev@localhost:5432/storico` | PostgreSQL connection string |
| `STORICO_QDRANT_URL`      | `http://localhost:6333`                                           | Qdrant vector store URL      |
| `STORICO_REDIS_URL`       | `redis://localhost:6379`                                          | Redis connection string      |
| `STORICO_OLLAMA_BASE_URL` | `http://localhost:11434`                                          | Ollama LLM API URL           |
| `STORICO_DEBUG`           | `true`                                                            | Enable debug mode            |
| `STORICO_APP_NAME`        | `Storico API`                                                     | Application name             |

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
├── docker-compose.yml   # 5 services: API, Ollama, Postgres, Qdrant, Redis
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

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

### Frontend (outside Docker)

```bash
cd frontend
npm install
npm run dev        # http://localhost:4321
npm run build      # Production build
```

## License

MIT — Angel Luis Valdés Sánchez, Universidad Tecnológica de la Mixteca (2026)
