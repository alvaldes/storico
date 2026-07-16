# Deployment

> Guía de despliegue para Storico.
> Última actualización: 2026-07-15

## Desarrollo (Docker Compose)

### Requisitos

- Docker + Docker Compose
- Git

### Inicio rápido

```bash
cp .env.example .env
make build      # Build imágenes
make up         # Start servicios
make ps         # Verificar salud
```

Servicios disponibles:

| Servicio | URL |
|----------|-----|
| API | `http://localhost:8000` |
| Frontend | `http://localhost:4321` |
| PostgreSQL | `localhost:5432` |
| Qdrant | `localhost:6333` |
| Redis | `localhost:6379` |
| Ollama | `localhost:11434` |

### Comandos útiles

```bash
make build         # Build imágenes Docker
make up            # Start servicios (detached)
make down          # Stop servicios
make logs          # Tail logs (make logs storico-api para uno)
make restart       # Restart all
make ps            # Listar servicios activos
make test-backend  # Correr tests backend
make test-frontend # Build check frontend
make shell-api     # Bash dentro del contenedor API
make clean         # Stop + remove volumes (DESTRUCTIVO)
make setup         # Install deps + build imágenes
```

### Desarrollo frontend standalone (sin Docker)

```bash
cd frontend
npm install
npm run dev        # http://localhost:4321
```

### Desarrollo backend standalone (sin Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest -v
```

## Producción (Vercel)

### Stack actual

- **Frontend**: Astro SSR en Vercel
- **Backend**: FastAPI en Vercel (serverless)
- **Base de datos**: PostgreSQL (proveedor pendiente de definir)
- **Vector store**: Qdrant Cloud (free tier 1GB) — pendiente
- **LLM**: OpenAI (pendiente de implementar adapter)

### Variables de entorno requeridas

Ver `.env.example` y `prod.todo.md` para la lista completa.

### CI/CD

Pendiente de definir.

## Roadmap de Producción

El checklist completo está en [`prod.todo.md`](../prod.todo.md). Resumen de prioridades:

| Prioridad | Item | Status |
|-----------|------|--------|
| 🔴 Crítico | OpenAI adapter (extracción en prod sin Ollama) | 🔲 Pendiente |
| 🟡 Medio | Qdrant Cloud + Embedding adapter | 🔲 Pendiente |
| 🟡 Medio | Vercel env audit | 🔲 Pendiente |
| 🟡 Medio | Error monitoring (Sentry) | 🔲 Pendiente |
| 🟡 Medio | Trello connector | 🔲 Pendiente |
| 🟡 Medio | Juicio de expertos (evaluación tesis) | 🔲 Pendiente |
| 🟤 Bajo | Custom domain | 🔲 Pendiente |
| 🟤 Bajo | Rate limiting | 🔲 Pendiente |
| 🟤 Bajo | Batch processing (Redis/Celery) | 🔲 Pendiente |
