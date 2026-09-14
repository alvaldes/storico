# Storico — Backlog

> **Última actualización**: 2026-09-14 — unificado desde `todo.md` y `prod.todo.md` tras la arc de
> deuda técnica (12 commits, `41cddae..b982c4d` en `origin/main`). Los items ya implementados se
> eliminaron y quedan listados al final como referencia.
>
> Estado verificado contra el código en esa fecha, no contra lo que decían los documentos viejos.

---

## 🔴 Bloqueantes de producción

### 1. Extracción en prod con LLM cloud

**Estado verificado**: `backend/src/storico/infrastructure/llm/` tiene `ollama_adapter.py` y
`gemini_adapter.py`. **No existe `openai_adapter.py`**, aunque el select del frontend
(`LLMConfigEditor`) ya ofrece OpenAI / Gemini / Anthropic.

- **Camino inmediato (cero código nuevo)**: verificar la extracción con **Gemini** en Vercel —
  el adapter ya existe. Puede desbloquear prod sin construir nada.
- **Si se quiere OpenAI**: crear `openai_adapter.py` (implementando el port `LLMPort`),
  agregar `openai` a `pyproject.toml`, `STORICO_OPENAI_API_KEY` / `STORICO_OPENAI_MODEL` en
  `settings.py`, y el switch en `get_llm_port()` (`dependencies.py`).
- Parámetros de referencia: `temperature=0.1`, `max_tokens=2048` (vienen de `LLMConfig`).

### 2. Qdrant Cloud + embeddings cloud

- El embedding service usa `nomic-embed-text` vía Ollama — no corre en Vercel.
- `EmbeddingService` → adapter cloud (`text-embedding-3-small`, 768 dim compatible con el schema),
  `STORICO_QDRANT_CLOUD_URL` / `STORICO_QDRANT_CLOUD_API_KEY` en settings, colección con
  `vector_size=768` + Cosine. Free tier: 1GB.
- **Depende de** tener la extracción funcionando en prod (item 1).

---

## 🟡 Importantes

### 3. Vercel env audit

Comparar las env vars de ambos proyectos (frontend + backend) contra `.env.example` /
`backend/.env.example`. Prestar atención a: `STORICO_AUTH_INTERNAL_TOKEN` (mismo valor en
ambos), `AUTH_SECRET` (mismo en ambos, distinto del dev), `API_URL` del frontend, y
`STORICO_CORS_ORIGINS` / `STORICO_AUTH_ALLOWED_ORIGINS` → `https://storico.vercel.app`.

### 4. Error monitoring (Sentry)

Backend: `sentry-sdk` inicializado en `app.py` (FastAPI integration incluida).
Frontend: `@sentry/astro` en `astro.config.mjs`. Free tier: 5k events/mes.

### 5. Conector Trello

Hoy sólo existe el valor `'trello'` en el enum `ExportFormat` y en i18n — no hay adapter.
Reutilizar la lógica probada de `csv2trello/core/` (autenticación, boards/listas/cards):
crear `ExportPort` + `TrelloAdapter`, endpoint `POST /api/v1/export/trello`, y conectar
`ExportPanel`.

### 6. Juicio de expertos (tesis)

Evaluación experimental con 6 expertos (Scrum Masters + POs). Métricas: TCR / TAS / IFI.
**Depende de**: extracción funcionando en prod (item 1) + exportación (item 5).

---

## 🟤 Bajos / V2

- **Dominio propio** — comprar, configurar en Vercel, actualizar OAuth redirects.
- **Rate limiting** — Vercel WAF (sin código) o `slowapi` (serverless).
- **Batch asíncrono con Redis** — la extracción *individual* ya es asíncrona
  (`asyncio.create_task` + polling); esto es el procesamiento de lotes.
- **Jira + export CSV/XML** — post-evaluación de la tesis.
- **Dashboard de admin con métricas**.
- **`@playwright/test` como devDependency** — Chromium ya está instalado; con la dependencia
  y un backend corriendo, los specs de `e2e/` pasan de excluidos a ejecutables.
- **`navigate()` de Astro en lugar de `window.location.assign`** — las 5 redirecciones
  restantes son internas por construcción (`localizedPath` clampea, UUIDs); migrar a SPA nav
  mejoraría la UX y silenciaría el scanner de open-redirect.

---

## 🧹 Limpieza menor

- **Makefile**: `test-backend` apunta a `backend/.venv/bin/pytest` pero ese venv no tiene
  pytest — los tests corren con el conda env `storico`. Decidir: instalar pytest en `.venv`
  (portátil) o apuntar al conda (machine-specific).
- **`StoryForm.tsx:515`**: último `dangerouslySetInnerHTML` del frontend — renderiza
  `t.stories.story_format_hint` (string i18n estático, seguro por contenido). Mismo patrón
  ya eliminado en `DeleteAccountDialog` con `renderBoldMarkup()`.
- **`tasks-api.ts` `updateTask`**: bloque muerto — *"We need the current status - fetch it
  first"* sin hacer nada. Implementar o eliminar.

---

## ✅ Completado (referencia — estos items se eliminaron del backlog)

- **Workspaces y permisos** (ex #16): admin crea workspaces, miembros, roles — implementado
  (migraciones + `MemberManagement`).
- **Extracción async individual con polling** (ex `todo.md` completo): `asyncio.create_task`
  en el backend + `pollExtraction` en `taskStore`. La migración a Celery/Redis queda cubierta
  por "Batch asíncrono" arriba.
- **Contrato de transiciones de task**: una sola fuente de verdad (`types/task.ts`), no-op
  válido en BE y FE (antes se impedía guardar sin cambiar el status).
- **SSR restaurado**: las 14 islas vuelven a `client:load`/`client:idle` con theming
  hydration-safe (`useThemeHydration` / `useResolvedTheme`); `client:only` eliminado.
- **Formato normalizado**: `.prettierrc.json` (single quotes, printWidth 100) + 119 archivos;
  el formatter ya no genera churn.
- **pnpm como único package manager**: `bun.lockb` y `package-lock.json` eliminados.
- **`@base-ui` prebundleado**: fin del error `error loading dynamically imported module`.
- **Seguridad**: XSS de `DeleteAccountDialog` (email interpolado en innerHTML) arreglado;
  toasts respetan el tema (`data-theme`).
- **Calidad**: tsc 0 errores, suite FE 67/0, transiciones BE 82 passed, tests de regresión
  nuevos (KanbanBoard, contract matrix de transiciones).
