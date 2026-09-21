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

## Producción

### Stack actual

- **Frontend**: Astro SSR en Vercel
- **Backend**: FastAPI en un contenedor Docker sobre una VM de Oracle. El host no se escribe acá: el workflow lo toma del secret `DEPLOY_HOST`.
- **Base de datos**: PostgreSQL en Neon
- **Vector store**: Qdrant contratado, todavía no configurado en producción
- **LLM**: OpenAI (adapter implementado)

### Variables de entorno requeridas

Ver `.env.example` y `prod.todo.md` para la lista completa. En producción el contrato vive en
`/home/ubuntu/storico/backend/.env` en la VM, que está fuera del control de versiones: el workflow
de despliegue no lo toca, así que una variable que falte no rompe el despliegue, falla en silencio
cuando el proceso la necesita.

### CI/CD

Existe y corre con cada push:

| Workflow | Qué hace |
|----------|----------|
| `.github/workflows/ci.yml` | Backend: `ruff check`, `ruff format --check`, `pytest -q`. Frontend: `pnpm exec tsc --noEmit`, `pnpm vitest run`. |
| `.github/workflows/deploy-backend.yml` | Despliegue del backend en la VM. |

El despliegue del backend entra por SSH a la VM, hace `git fetch origin main`, resetea el árbol de
trabajo a `origin/main`, reconstruye la imagen, detiene y elimina el contenedor anterior y arranca
uno nuevo con `docker run --network host --env-file /home/ubuntu/storico/backend/.env`.

### Migraciones

**El despliegue no corre migraciones de Alembic.** Una revisión de esquema puede quedar desplegada
sin su migración aplicada, y ese es exactamente el incidente del 2026-09-20: el esquema quedó en
`0021` contra un head `0024` y la extracción falló 56 veces con
`column extractions.completed_at does not exist`. `prod.todo.md` lleva el paso de migración como
ítem abierto. La política de migraciones es una decisión aparte y no se define en este documento.

### Artefactos de build del frontend

`frontend/dist/` y `frontend/.vercel/output/` son **salidas**, no fuentes: están en
`.gitignore`, nada en el repositorio **los** lee (ni el `Makefile` ni ningún otro paso: el workflow
de CI los **escribe** al construir, no los consume), y las produce `pnpm run build`:
`@astrojs/vercel` vacía y reescribe `.vercel/output/` durante el build, además de escribir `dist/`.

**Regenera los artefactos antes de desplegar; no reutilices una salida existente.** El riesgo es
concreto y ya se materializó una vez: quedaron en disco bundles anteriores a un cambio de copy y el
texto retirado seguía dentro de ellos. Un deploy que reutilice `.vercel/output` sin reconstruir
sirve el bundle viejo aunque el código diga otra cosa. Antes, nada lo detectaba: el frontend no se
construía en CI y las pruebas no lo miraban. Desde que `.github/workflows/ci.yml` corre `pnpm build`,
un build roto frena el pull request; lo que el gate **no** puede ver es un artefacto viejo
reutilizado en un despliegue manual, que es justo lo que esta sección advierte. Borrar los
directorios es seguro en cualquier momento — se recrean en el siguiente build — y es la forma más
simple de no partir de un estado viejo.

## Roadmap de Producción

El checklist completo está en [`prod.todo.md`](../prod.todo.md). Resumen de prioridades:

| Prioridad | Item | Status |
|-----------|------|--------|
| 🔴 Crítico | OpenAI adapter (extracción en prod sin Ollama) | ✅ Implementado |
| 🟡 Medio | Qdrant Cloud + Embedding adapter | 🔲 Pendiente |
| 🟡 Medio | Vercel env audit | 🔲 Pendiente |
| 🟡 Medio | Error monitoring (Sentry) | 🔲 Pendiente |
| 🟡 Medio | Trello connector | 🔲 Pendiente |
| 🟡 Medio | Juicio de expertos (evaluación tesis) | 🔲 Pendiente |
| 🟤 Bajo | Custom domain | 🔲 Pendiente |
| 🟤 Bajo | Rate limiting | 🔲 Pendiente |
| 🟤 Bajo | Batch processing (Redis/Celery) | 🔲 Pendiente |
