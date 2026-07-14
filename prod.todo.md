# Storico — Production TODO

> Estado: items 1–4 completados (tokens + OAuth redirects).
> Próximo paso recomendado: OpenAI adapter (bloqueante para extracción en prod).

---

## ☁️ Cloud LLM — Extracción en producción

Estos items están acoplados. El orden importa.

### 6 🔴 — OpenAI adapter

**Qué**: Crear `OpenAIAdapter` que implemente `LLMPort.generate()`.

**Dónde**: `backend/src/storico/infrastructure/llm/openai_adapter.py`

**Dependencias**:
- `pyproject.toml` → agregar `openai>=1.0.0`
- `settings.py` → agregar `STORICO_OPENAI_API_KEY`, `STORICO_OPENAI_MODEL` (default: `gpt-4o-mini`)
- `dependencies.py` → `get_llm_port()` debe elegir entre `OpenAIAdapter` y `OllamaAdapter` según si hay API key configurada

**Contexto del código**:
- `LLMPort.generate(prompt, config)` devuelve `str` raw — el adapter mapea la API de OpenAI a eso
- El system prompt está hardcodeado en `OllamaAdapter._build_payload()` → moverlo a un shared constant o pasarlo desde `PromptManager`
- `temperature=0.1`, `max_tokens=2048` vienen de `LLMConfig`

**Verificación**: `POST /api/v1/extract` con una user story real devuelve tareas en Vercel.

---

### 5 🔴 — Ollama no funciona en Vercel (bloqueante documentado)

**Qué**: El `POST /extract` falla en prod porque Ollama no corre en Vercel. Se resuelve implementando #6. Una vez que #6 está, el endpoint funciona con OpenAI.

**Acción**: Ninguna directa — desbloqueado por #6.

---

### 7 🟡 — Qdrant Cloud + Embedding adapter

**Qué**: Migrar Qdrant a cloud (qdrant.tech free tier: 1GB) y crear un adaptador de embeddings cloud.

**Depende de**: #6 (el embedding service actual usa Ollama — `nomic-embed-text`).

**Qué incluye**:
- `EmbeddingService` → crear `OpenAIEmbeddingAdapter` que use `text-embedding-3-small` (dimensiones 768 → compatible con el schema actual)
- `settings.py` → agregar `STORICO_QDRANT_CLOUD_URL`, `STORICO_QDRANT_CLOUD_API_KEY`
- `dependencies.py` → `get_embedding_service()` debe elegir según config
- Crear colección en Qdrant cloud con `vector_size=768`, `distance=Cosine`
- `QdrantAdapter` ya soporta URL configurable — solo apuntar a cloud

**Costo**: Gratis (1GB, suficiente para miles de extracciones).

---

## 🚀 Infraestructura

### 11 🟡 — Vercel env audit

**Qué**: Verificar que ambos proyectos (frontend + backend) en Vercel tengan todas las env vars necesarias.

**Cómo**:
1. `vercel env pull` en cada proyecto o dump manual desde dashboard
2. Comparar contra `.env.example` y `backend/.env.example`
3. Prestar atención a:
   - `STORICO_AUTH_INTERNAL_TOKEN` — debe ser el mismo en frontend y backend
   - `AUTH_SECRET` — mismo en ambos, distinto del dev
   - `API_URL` en frontend → `https://storico-api.vercel.app` (o la URL del backend)
   - `STORICO_DATABASE_URL` en backend → apuntar a la DB de prod
   - `STORICO_CORS_ORIGINS` → `https://storico.vercel.app`
   - `STORICO_AUTH_ALLOWED_ORIGINS` → `https://storico.vercel.app`

**Nota**: `.env` está en `.gitignore` ✅ — los secrets de dev no se fueron al repo.

---

### 10 🟡 — Error monitoring (Sentry)

**Qué**: Conectar Sentry en backend (FastAPI) y frontend (Astro).

**Backend**:
- `pip install sentry-sdk`
- Inicializar en `app.py` con `dsn` + `traces_sample_rate`
- FastAPI integration ya viene incluida en `sentry-sdk`

**Frontend**:
- `npm install @sentry/astro`
- Agregar integración en `astro.config.mjs`
- Configurar `dsn` + `environment`

**Costo**: Gratis (Sentry Developer plan: 5k events/mes, suficiente para arrancar).

---

### 9 🟤 — Custom domain

**Qué**: Configurar un dominio lindo (ej. `storico.app`) en vez de `storico.vercel.app`.

**Pasos**:
1. Comprar dominio en Namecheap/DominiosGoogle/Cloudflare
2. Agregar en Vercel Dashboard → Project → Settings → Domains
3. Configurar DNS (vercel提供 nameservers o CNAME)
4. Actualizar OAuth redirect URIs con el nuevo dominio
5. Actualizar `allowedDomains` en `astro.config.mjs`

**Prioridad**: Baja — functional con `storico.vercel.app`.

---

### 12 🟤 — Rate limiting

**Qué**: Proteger endpoints de extracción contra abuso.

**Opciones**:
- **Vercel WAF** (nativo, configurable en dashboard) → más simple, sin código
- **`slowapi`** (FastAPI middleware) → más control, pero corre en serverless

**Prioridad**: Baja — solo necesario si la app se abre al público sin auth.

---

### 8 🟤 — Redis/Celery (Batch processing)

**Qué**: Procesamiento asíncrono de lotes de user stories.

**Servicio**: Redis Cloud (gratis 30MB).

**Prioridad**: Baja — el MVP usa extracción sincrónica (`POST /extract`). Pateable hasta que haya demanda de batch.

---

## 📤 Exportación — Conectores

### 13 🟡 — Conector Trello (MVP)

**Status en código**: No implementado. Existe en schema (`ExportFormat = 'trello' | 'json' | 'markdown'`) y en i18n, pero no hay adaptador.

**Qué hacer**:
- Reutilizar lógica de `csv2trello/core/` (repo existente de la tesis) — autenticación, creación de boards/listas/cards
- Crear `TrelloAdapter` implementando un nuevo `ExportPort`
- Endpoint `POST /api/v1/export/trello`
- UI: conectar `ExportPanel` con el endpoint

**Referencia**: `csv2trello` repo tiene la lógica de Trello API ya probada.

---

### 14–15 🟤 — Conector Jira + Export CSV/XML

**Prioridad**: V2 del roadmap. Pateable hasta después de la evaluación de la tesis.

---

## 👥 Permisos y Workspaces

### 16 🟤 — Permisos y workspaces (V2)

**Qué**: Modelo Admin → Workspace → Equipos → Usuarios. Solo admins crean workspaces y asignan miembros.

**Dependencias**:
- Tablas `workspaces`, `team_members` (ya hay `users` y `user_preferences`)
- Endpoints CRUD de workspaces
- Filtro por workspace en todas las queries

**Prioridad**: V2. Hoy cualquier usuario logueado puede usar la app.

---

## 📊 Dashboard de Admin

### 17 🟤 — Dashboard de admin con métricas

**Prioridad**: V2 — post-evaluación.

---

## 🧪 Evaluación (Tesis)

### 18 🟡 — Juicio de expertos

**Qué**: Evaluación experimental con 6 expertos (Scrum Masters + PO).

**Métricas**: TCR, TAS, IFI.

**Depende de**: #6 (extracción funcionando en prod), #13 (exportación a Trello para el flujo Kanban).

**Timeline**: Después de que los items bloqueantes estén en prod.

---

## Resumen de dependencias

```
#6 OpenAI adapter ─┬──> #7 Qdrant Cloud (needs embeddings)
                   ├──> #13 Trello connector (needs extraction working)
                   └──> #18 Juicio de expertos (needs extraction + Trello)
```

Items independientes (orden no estricto): #9, #10, #11, #12, #8, #14, #15, #16, #17.
