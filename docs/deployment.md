# Deployment

> Guía de despliegue para Storico.
> Última actualización: 2026-09-25

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
pnpm install
pnpm run dev       # http://localhost:4321
```

### Desarrollo backend standalone (sin Docker)

```bash
# entorno canónico: conda `storico` (bootstrap y comandos en AGENTS.md)
conda activate storico
cd backend
python -m pip install -e ".[dev]"
python -m pytest -v
```

## Producción

### Stack actual

- **Frontend**: Astro SSR en Vercel
- **Backend**: FastAPI en un contenedor Docker sobre una VM de Oracle. El host no se escribe acá: el workflow lo toma del secret `DEPLOY_HOST`.
- **Base de datos**: PostgreSQL en Neon. **Dev y prod no comparten base:** dev corre local contra Supabase.
- **Vector store**: **Qdrant Cloud**, un solo cluster, usado por dev y por prod. Cada entorno escribe en **su propia colección** (ver abajo).
- **Embeddings**: **globales, no por workspace**. Dev usa Ollama local (`nomic-embed-text`); producción usa **Google `gemini-embedding-001`**, porque la VM no tiene Ollama y el modelo de chat no puede embeber.
- **LLM de extracción**: lo configura cada workspace (Ollama, OpenAI, Anthropic, Gemini o un proveedor propio compatible con OpenAI).

### Una colección por entorno

Una colección pertenece al modelo de embeddings que la llena: los vectores de dos modelos
distintos son **incomparables aunque tengan las mismas dimensiones**, así que compartir una
colección devuelve vecinos con una similitud que no significa nada — y sin ningún error visible.

| Entorno | Colección | Embeddings |
|---------|-----------|------------|
| Dev | `storico_extractions_dev` | Ollama / `nomic-embed-text` |
| Prod | `storico_extractions_prod` | Google / `gemini-embedding-001` |

La colección se crea sola en el primer uso, con las dimensiones de `STORICO_EMBEDDING_DIMENSIONS`
y su índice `workspace_id`.

**Dev tiene que fijar el nombre a mano.** El default de `STORICO_QDRANT_COLLECTION` es
`storico_extractions`, que no es ninguna de las dos: sin esa variable, un backend de dev escribe en una
tercera colección y el nombre "de prod" queda libre para que cualquiera lo use con otro modelo de
embeddings. La línea va en el `.env` de la raíz del repo:

```bash
STORICO_QDRANT_COLLECTION=storico_extractions_dev
```

Medido el 2026-09-24: el `.env` local no la tenía, y el cluster tenía `storico_extractions` (19 puntos
de verificación) y `storico_extractions_prod` (1 punto) — `storico_extractions_dev` **no existía**.

### Variables de entorno requeridas

Ver `.env.example` y `prod.todo.md` para la lista completa. En producción el contrato vive en
`/home/ubuntu/storico/backend/.env` en la VM, que está fuera del control de versiones: el workflow
de despliegue no lo toca, así que una variable que falte no rompe el despliegue, falla en silencio
cuando el proceso la necesita.

Para que el RAG funcione en producción, ese archivo necesita además:

| Variable | Valor | Por qué |
|----------|-------|---------|
| `STORICO_EMBEDDING_PROVIDER` | `google` | La VM no tiene Ollama y no se instala uno |
| `STORICO_GOOGLE_API_KEY` | la credencial de Google AI | Es la única credencial nueva que pide prod |
| `STORICO_GOOGLE_EMBEDDING_MODEL` | `gemini-embedding-001` | `text-embedding-004` está **retirado**: la API responde `404 models/text-embedding-004 is not found` |
| `STORICO_EMBEDDING_DIMENSIONS` | `768` | Debe coincidir con el tamaño de la colección |
| `STORICO_QDRANT_URL` | el cluster cloud | Sin esto el cliente apunta a `localhost:6333` y no hay nada ahí |
| `STORICO_QDRANT_API_KEY` | la key del cluster | El cluster es gestionado |
| `STORICO_QDRANT_COLLECTION` | `storico_extractions_prod` | Para no mezclar espacios con dev |

**Cuidado con el nombre de la variable del modelo:** `STORICO_EMBEDDING_MODEL` aplica **solo a
Ollama**. Cada proveedor cloud lee la suya (`STORICO_GOOGLE_EMBEDDING_MODEL`,
`STORICO_OPENAI_EMBEDDING_MODEL`), y el mapeo tiene un solo hogar en el código
(`embedding_model_for()` en `infrastructure/vector/__init__.py`).

Una variable que falte en ese archivo **no falla en el deploy**: la extracción completa, y el punto
del RAG no se guarda. Desde este lote ese fallo se registra en `ERROR` (`reason=empty_embedding`,
`client_unavailable` o `upsert_failed`) en vez de desaparecer, y `GET /api/v1/health/services`
expone un probe de `embeddings` que reporta proveedor, modelo, dimensiones y si de verdad puede
embeber. **Ese endpoint es la forma corta de saber si prod quedó configurado.**

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

**El despliegue aplica las migraciones dentro de una ventana de mantenimiento**, entre parar el
contenedor viejo y arrancar el nuevo. La razón es que no hay ninguna otra posición que sirva: `0022` y
`0024` piden el código nuevo vivo **antes** de correr (una release vieja malinterpretaría el esquema
nuevo) y `0023` pide la columna existente **antes** de que el código nuevo la lea. Cada peligro
necesita un release vivo del lado equivocado, así que una ventana **sin ningún release vivo** los
elimina a la vez. Por eso el paso no se puede mover arriba del `docker stop`.

El comando que corre el workflow — el mismo que un operador usa a mano:

```bash
docker run --rm \
  --network host \
  --env-file /home/ubuntu/storico/backend/.env \
  storico-api \
  alembic upgrade head
```

Se ejecuta desde la imagen recién construida, porque la revisión que se aplica es la de ese commit, y
con el **mismo** `--env-file` que el contenedor: ahí viven `STORICO_DATABASE_URL` y
`STORICO_ENCRYPTION_KEY`, que toda actualización que cruce `0024` necesita. Y con el mismo archivo, la
migración no puede alcanzar una base distinta de la que usa la aplicación. La configuración de Alembic
usa `%(here)s`, así que el comando funciona desde cualquier directorio; la imagen incluye
`alembic.ini` y los scripts viajan dentro de `src/`.

**Las consecuencias, dichas de frente:**

- Hay una **ventana de indisponibilidad** entre el `docker stop` y el arranque del contenedor nuevo,
  que incluye la migración. En las revisiones actuales son segundos.
- Si la migración falla, `set -e` aborta el job y **la API queda abajo**. Es deliberado: lo alternativo
  es servir con un esquema que no coincide con el código, que es el incidente del 2026-09-20. La
  recuperación es **hacia adelante** — arreglar la causa y volver a correr el workflow — y los guardas
  de idempotencia de `0022` y `0024` hacen que re-correr sea seguro.
- El deploy deja la imagen anterior taggeada como `storico-api:previous`, porque hasta ahora no había
  ninguna vuelta atrás: el build sobrescribía el único tag que tenía la release anterior. Ese tag
  devuelve la release anterior **sólo mientras el esquema siga siendo compatible con ese código**; con
  una migración aplicada a medias, el camino correcto es hacia adelante y no volver.
- El gate de readiness que corre después deja de detectar drift: pasa a ser la **prueba** de que la
  migración quedó aplicada, porque exige que `alembic_version` sea igual al head empacado con el
  código. Un gate rojo con la migración en verde ya no apunta al esquema, sino al contenedor o a su
  entorno.
- Los deploys están **serializados** (`concurrency` en el workflow): dos a la vez competirían por el
  swap y por la migración.

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
| 🟡 Medio | Vercel env audit | ✅ Hecho (2026-09-24) |
| 🟡 Medio | Error monitoring (Sentry) | 🔲 Pendiente |
| 🟡 Medio | Trello connector | 🔲 Pendiente |
| 🟡 Medio | Juicio de expertos (evaluación tesis) | 🔲 Pendiente |
| 🟤 Bajo | Custom domain | 🔲 Pendiente |
| 🟤 Bajo | Rate limiting | 🔲 Pendiente |
| 🟤 Bajo | Batch processing | ✅ Cerrado por decisión (2026-09-25): no hay endpoint de lote y no se va a implementar. Cada extracción es una historia y corre en segundo plano en el proceso de la API |
