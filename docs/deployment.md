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

### La base de datos de desarrollo (Supabase)

Dev corre contra un proyecto de **Supabase** (`aws-0-us-east-1.pooler.supabase.com:5432`, Postgres 17.6),
no contra Neon. Esa es la única separación física que hay entre entornos: **el clúster de Qdrant es
compartido** y lo que separa un entorno del otro es sólo el nombre de la colección, como se documenta más
abajo.

Estado medido el **2026-09-30**, después del reset de `odd/tasks/dev-reset-0028.md`: `alembic_version =
0028`, las **doce** tablas de negocio en **0** filas. Antes de ese reset estaba en `0027` con 422 filas
reales — 38 `extractions`, 230 `tasks`, 76 `user_stories`, 3 `users`, 12 `workspace_llm_configs` — y por eso
hizo falta la purga: `0028` **se niega** a correr sobre `extractions`/`tasks` con filas (D11, ver la sección
de producción más abajo). El mismo bloqueo que frenó a producción frenó a dev, y el remedio fue el mismo
orden: **primero purgar, después migrar.**

Tres cosas que hay que saber para usar dev hoy:

1. **No hay config de LLM.** `workspace_llm_configs` está vacío, así que `resolve_llm_config`
   (`api/routes/workspace_settings.py:121-129`) cae a `provider = "ollama"`. Para extraer hace falta una de las
dos: prender Ollama en `localhost:11434`, o crear un config con clave real en Configuración.
2. **Conviene prender Ollama de todos modos.** El default de `STORICO_EMBEDDING_PROVIDER` es `ollama`
   (`nomic-embed-text`, 768 dims) y el `.env` de dev no lo pisa: sin Ollama, el paso de RAG no tiene
   dónde embeber, con datos o sin datos.
3. **El primer login no alcanza para volver a un proveedor propio.** Crea usuario, workspace, membresía
   `admin` y `workspace_prompts` (`api/routes/auth.py:119-126`), pero **no** toca `workspace_llm_configs`
   ni `custom_providers`: un proveedor como `NaN` se re-crea a mano.

El andamiaje que ejecutó el reset vive fuera del repo, en `~/storico-ops/` (`dev_purge_0028.py` con tres
guardas y dry-run por defecto, `dev_verify_0028.py` read-only); el procedimiento y la evidencia, acá.

### Estado de las dos bases, lado a lado

**Este es el lugar canónico donde se comparan los dos entornos** (decisión del owner del 2026-09-30, que
también decidió **no** tocar `prod.todo.md`: ese archivo sigue siendo la lista única de pendientes de
producción, y el detalle de cada reset vive en su doc de feature).

| | **dev** — Supabase | **prod** — Neon |
| --- | --- | --- |
| endpoint | `aws-0-us-east-1.pooler.supabase.com:5432` (session mode) | `ep-damp-sea-at0qjzd2…neon.tech` |
| rol conectado | `postgres` | `neondb_owner` |
| **motor (medido)** | **Postgres 17.6** | **Postgres 18.6** |
| `alembic_version` | **0028** | **0028** |
| tablas de negocio | **13** (12 + `task_invalidations`), todas en **0** | **13**, todas en **0** |
| purga | 2026-09-30: **12 tablas / 422 filas**, sin respaldo (`odd/tasks/dev-reset-0028.md`) | 2026-09-30 ~04:28 UTC: **11 tablas / 90 filas**, sin respaldo (`prod.todo.md`, D-a-3) |
| credenciales de LLM | **0** — se perdió 1 `api_key` única (`NaN/gemma4`) | **0** — se perdieron 2 `api_key` únicas |
| ¿extrae hoy? | **no**: sin config y **sin Ollama en esta máquina** | **no**: sin config y sin Ollama en la VM |
| acceso a la base | `asyncpg` **sin `ssl`**: el pooler de Supabase presenta cadena auto-firmada y `ssl=True` falla con `SSLCertVerificationError` | `asyncpg` con **`ssl=True`**: Neon presenta cadena válida |
| embeddings | default `ollama` / `nomic-embed-text` / 768 dims — requiere un Ollama corriendo | `google` / `gemini-embedding-001` / 768 dims |
| colección Qdrant | `storico_extractions_dev` (0 puntos) | `storico_extractions_prod` (0 puntos) |

Las dos celdas de "¿extrae hoy?" son idénticas por razones distintas de las que habla cualquier migración:
**ninguno de los dos entornos puede extraer hasta que alguien cree un config de LLM en Configuración**, y
`resolve_llm_config` cae a `provider = "ollama"` sin avisar.

#### Los motores no coinciden entre sí, y ninguno es el de CI

Medido en esta sesión: **CI y los tests de integración corren en Postgres 16**
(`PostgresContainer("postgres:16-alpine")`, y `docs/database.md:8` y `docs/architecture.md:21` declaran
"PostgreSQL 16"), **dev está en 17.6** y **producción en 18.6**. O sea que `0028` se validó en un motor, se
aplicó en producción sobre otro major, y acaba de aplicarse en dev sobre un tercero.

Esto no rompió nada: la verificación de forma de dev se hizo **leyendo el motor real de dev**, no el de CI,
y coincide objeto por objeto. Pero es exactamente la lección que D-a-3 ya dejó escrita —"CI había probado en
su Postgres pero no en el de producción"— y sigue vigente para la próxima revisión: **una migración que CI
prueba en 16 puede comportarse distinto en 17 y en 18, y la prueba que vale es la que se lee contra la base
real.** La decisión de alinear versiones (subir CI, o fijar 17 en los dos entornos) es del owner, no de esta
sesión, y no la tomé: cambiar el motor de producción es un incidente en potencia.

## Producción

### Stack actual

- **Frontend**: Astro SSR en Vercel
- **Backend**: FastAPI en un contenedor Docker sobre una VM de Oracle. El host no se escribe acá: el workflow lo toma del secret `DEPLOY_HOST`.
- **Base de datos**: PostgreSQL en Neon. **Dev y prod no comparten base:** dev corre contra Supabase (ver "La base de datos de desarrollo" arriba).
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

**Re-medido el 2026-09-30: hoy existen las tres.** `storico_extractions_prod` 1 punto,
`storico_extractions_dev` **1** punto (apareció: el `.env` de esta máquina ya tenía la variable puesta),
y `storico_extractions` 19 puntos. Consecuencia que hay que leer sin eufemismos: **dev y prod comparten
cluster**, y lo único que los separa es el nombre de colección; la colección legado de 19 puntos existe
porque el default del adaptador (`qdrant_adapter.py:39`) es `storico_extractions` y esa fue la época en
que el `.env` no declaraba colección. "Una colección por entorno" es separación lógica, no física. El hallazgo y su pendiente de diseño están en
`odd/tasks/prod-purge-d-a-3.md` — era el pendiente de la sección D-a-3 de `prod.todo.md`, movida allí el
2026-10-07 con una redirección en el lugar original; el ítem vivo sigue listado en `prod.todo.md`.

**Riesgo aceptado el 2026-10-07, por decisión del owner: la separación entre dev y producción es
lógica y se documenta, no se separa físicamente.** Las tres cosas que los dos entornos comparten,
medidas: (1) el cluster de Qdrant, donde el nombre de la colección es el único separador; (2) el
valor de `AUTH_SECRET` del frontend de producción, que es el mismo del `.env` de desarrollo y el
mismo `STORICO_AUTH_JWT_SECRET` de la VM — o sea que **un token firmado en desarrollo es válido en
producción**; y (3) el cliente OAuth de Google, que es el mismo en los dos entornos (el de GitHub
sí está separado). No se crearon entornos separados de verdad —cluster y API key de Qdrant propios,
cliente OAuth propio— porque el costo es trabajo en las consolas de Google y Qdrant más rehacer la
auditoría de variables de entorno, y el riesgo se consideró aceptable para el estado actual del
proyecto. Queda escrito para que la próxima persona lo herede sabiéndolo en vez de descubriéndolo:
lo que la separación de nombre no protege es (2), y ningún cambio de documentación lo cambia.

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
- El deploy **reclama disco de forma acotada**, después del gate de readiness: borra las imágenes sin
  tag y el build cache de más de una semana (`docker builder prune --filter until=168h`). Medido el
  2026-09-25: el disco de la VM es de 45 GB y estaba al **69 %**, con **25.71 GB** de build cache (207
  registros) y 8 imágenes huérfanas — cada `docker build` dejaba su caché y **nada** la podaba. Ninguna
  de las dos cotas es decorativa: sin `-a`, `docker image prune` borra sólo lo que no tiene tag, así
  que `storico-api:previous` sobrevive por construcción; y el caché se conserva una semana porque es
  lo que evita reconstruir la capa de dependencias entera en cada deploy. Corre **después** del gate a
  propósito: `set -e` aborta antes cuando el deploy falla, así el re-intento conserva su caché. El
  invariante está pinneado en `backend/tests/test_unit/test_deploy_workflow_contract.py`.
- Los deploys están **serializados** (`concurrency` en el workflow): dos a la vez competirían por el
  swap y por la migración.

### Una revisión que se niega a correr sobre datos: `0028` (bloqueo **D-a-3**, 2026-09-30 — **cerrado el mismo día**)

El punto anterior asume que toda migración puede aplicarse a la base de producción. `0028` —el
versionado de extracciones del slice (a) de 0.9.0— está escrita para **negarse**: lee
`SELECT count(*) FROM extractions` y `FROM tasks` antes de tocar el esquema y lanza `RuntimeError` si
alguna de las dos tiene una sola fila. Es la decisión D11 del diseño: no se hace backfill.

Consecuencia directa sobre el mecanismo de esta sección, **que era el bloqueo hasta el 2026-09-30**: como
`deploy-backend.yml` corre `alembic upgrade head` en **todo** despliegue, y producción tenía filas reales,
**mergear esa rama a `main` dejaba la API abajo**. No era un fallo del workflow — es exactamente la
política de "antes abajo que servir con un esquema que no coincide" de la que habla el bloque de arriba —
pero tampoco era un despliegue.

**Como quedó resuelto, y por qué la regla sigue vigente:** primero la purga (once tablas de negocio y las
tres colecciones de Qdrant, detrás de un interlock que comparó cada conteo con el inventario commiteado y
negó a borrar ante cualquier diferencia), después el merge (`1dcc716`), después el deploy
(`36675276096`), que corrió `0028` sobre bases vacías y pasó la guarda. Verificado leyendo Neon:
`alembic_version = 0028` con las restricciones y los índices de la feature presentes. **El bloqueo se pagó
con datos; la mecánica no cambió: una migración que se niega ante datos existentes sigue necesitando su
plan de datos en `prod.todo.md` antes de llegar a `main`.** (El registro D-a-3 con ese plan, su runbook,
su inventario y su verificación vive desde el 2026-10-07 en `odd/tasks/prod-purge-d-a-3.md`;
`prod.todo.md` conserva una redirección en el lugar original.)

**Medido en la base de producción el 2026-09-30, en lectura y solo con `count(*)`:**
`alembic_version = 0027`, **17** filas en `extractions` (11 `failed`, 6 `completed`, span
2026-08-03 → 2026-09-24) y **42** en `tasks`, todos en `backlog`. Hasta este día la prueba citada era la
colección de **Qdrant** `storico_extractions_prod`, que es otra tienda: la guarda lee Postgres. La
conclusión no cambió, pero ahora la sostiene el dato de la columna que la guarda consulta.

**Decidido y EJECUTADO el 2026-09-30: ventana de purga, merge y deploy.** El runbook, el inventario y la
verificación paso a paso están en `odd/tasks/prod-purge-d-a-3.md` — era el ítem *"Bloqueo de
despliegue"* de `prod.todo.md`, movido allí el 2026-10-07 sin editar su contenido y con una redirección en
el lugar original. Resumen de lo real:

1. **Purga** (~04:28 UTC) detrás de un interlock que negó a ejecutar el `TRUNCATE` si los once conteos,
   `alembic_version` y los tres conteos de Qdrant no coincidían con el inventario commiteado. Una
   transacción `RESTART IDENTITY CASCADE` sobre las once tablas del esquema de negocio, `points/delete`
   en las tres colecciones. Verificado desde un proceso aparte: todo en 0, `alembic_version` aún `0027`.
2. **Merge** de PR #30 a `main` (`1dcc716`), con **merge commit** y no squash: la convención de `main` son
   merge commits (`#24`-`#29`), y squashar habría colapsado los doce work-unit commits que son la unidad
   revisable de esta rama.
3. **Deploy** `run 36675276096` → `success` en 2m1s. Como `0028` corrió sobre bases vacías, la guarda no
   disparó.
4. **Verificación en el Neon de producción, en lectura:** `alembic_version = 0028`, `task_invalidations`
   existe, `fk_task_invalidations_revoked_by_users` con `ON DELETE RESTRICT` (la corrección de la task 4.4,
   que CI había probado en su Postgres pero nunca en éste), `uq_extractions_story_version`,
   `uq_task_invalidations_active_task`, `tasks.extraction_id NOT NULL`, once tablas en 0, y
   `/api/v1/health` → `ok`.

**El efecto secundario que ninguna migración avisa:** con `workspace_llm_configs` vacío,
`resolve_llm_config` (`api/routes/workspace_settings.py:121-129`) cae a `provider = "ollama"` y al host de
Ollama, que no existe en producción. La app queda viva pero **incapaz de extraer hasta que se re-creé el
config en Configuración**; las dos `api_key` que había se perdieron a propósito y eran sus únicas copias.
Un plan de purga tiene que nombrar también esto, no sólo las tablas.

La regla general que sale de acá, para cualquier revisión futura con esta forma: **una migración que se
niega ante datos existentes necesita su plan de datos escrito en `prod.todo.md` antes de llegar a
`main`.** (El registro D-a-3 vive desde el 2026-10-07 en `odd/tasks/prod-purge-d-a-3.md`, con
redirección en `prod.todo.md`.) El gate de readiness no protege de esto: con la migración abortada, el job muere antes.

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
| 🟡 Medio | Qdrant Cloud + Embedding adapter | ✅ Operativo — medido en producción el 2026-09-28: `/api/v1/health/services` responde `qdrant: ok` y `embeddings: ok` (`google` / `gemini-embedding-001` / 768). Esta fila contradecía a la línea 73 del mismo archivo |
| 🟡 Medio | Vercel env audit | ✅ Hecho (2026-09-24) |
| 🟡 Medio | Error monitoring (Sentry) | 🔲 Pendiente |
| 🟡 Medio | Trello connector | 🔲 Pendiente |
| 🟡 Medio | Juicio de expertos (evaluación tesis) | 🔲 Pendiente |
| 🟤 Bajo | Custom domain | 🔲 Pendiente |
| 🟤 Bajo | Rate limiting | 🔲 Pendiente |
| 🟤 Bajo | Batch processing | ✅ Cerrado por decisión (2026-09-25): no hay endpoint de lote y no se va a implementar. Cada extracción es una historia y corre en segundo plano en el proceso de la API |
