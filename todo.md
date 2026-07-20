# Storico — Extracción asíncrona con polling

> **Contexto**: El botón "Extract" de descomposición de user stories bloquea la UI mientras el LLM responde (30s–2min). Este documento describe la migración de extracción síncrona a asíncrona con polling, y el plan futuro para migrar a Celery.

---

## Problema

Hoy `POST /api/v1/workspaces/{workspace_id}/extract/` es **síncrono** — el HTTP request se mantiene abierto todo el tiempo que el LLM tarda en responder. El botón se deshabilita con un spinner y el usuario no tiene visibilidad del progreso.

## Solución elegida (iteración 1)

**Opción 3: asyncio `create_task` + polling**

El POST responde **inmediatamente** con `{ extraction_id, status: "pending" }`, lanza la extracción en background con `asyncio.create_task()`, y el frontend **p**olea `GET /status/{extraction_id}` hasta que el estado cambie a `completed` o `failed`.

---

## Plan de implementación

### Fase 1 — Backend: POST asíncrono

**Archivos a modificar:**

| Archivo | Cambio |
|---------|--------|
| `backend/src/storico/api/routes/extraction.py` | El POST ya no llama `await use_case.execute()`. En su lugar: (1) crea un registro `Extraction(status="pending")`, (2) lanza `asyncio.create_task(background_extract(...))`, (3) responde inmediatamente con `{ extraction_id, status: "pending" }` |
| `backend/src/storico/application/extraction/extract_from_story.py` | Opcional: separar `execute` en dos métodos — `create_pending` y `run_extraction` |

**Detalle del cambio en `extraction.py`:**

```python
@extraction_router.post("/", status_code=status.HTTP_202_ACCEPTED)
async def extract_tasks(
    body: ExtractRequest,
    ctx: tuple[Workspace, WorkspaceRole] = Depends(get_workspace_for_user),
    use_case: ExtractFromStoryUseCase = Depends(get_extract_use_case),
    extraction_repo: ExtractionRepoDep = None,
    task_repo: TaskRepoDep = None,
    story_repo: StoryRepoDep = None,
    project_repo: ProjectRepoDep = None,
    llm_config_repo: LLMConfigRepoDep = None,
) -> ExtractResponse:
    workspace, _ = ctx

    # 1. Validate story belongs to workspace
    await _validate_story_belongs_to_workspace(...)

    # 2. Resolve model
    model = body.model or (await llm_config_repo.get(workspace.id)).model

    # 3. Create pending extraction record
    extraction = Extraction(
        user_story_id=body.user_story_id,
        model_used=model,
        raw_response="",
        status="pending",
    )
    extraction = await extraction_repo.save(extraction)

    # 4. Launch background extraction
    asyncio.create_task(
        _run_extraction_background(
            extraction_id=extraction.id,
            use_case=use_case,
            extraction_repo=extraction_repo,
        )
    )

    # 5. Respond immediately
    return ExtractResponse(
        extraction_id=extraction.id,
        status="pending",
        tasks=[],
        model_used=model,
    )
```

**Lo que cambia en el frontend:**

- `taskStore.ts`: `extracting: boolean` → `extractionStatus: Record<string, 'idle' | 'pending' | 'processing' | 'completed' | 'failed'>`
- `extractTasks()`: llama al POST, recibe `extraction_id`, guarda el estado como `pending`, inicia polling
- Nuevo hook/efecto: `useExtractionPolling(extractionId)` que corre cada 2s y actualiza el estado
- `StoryDetail.tsx`: el botón muestra el estado actual (spinner en pending/processing, check en completed, error en failed)

---

## Migración futura a Celery (Opción 2)

Cuando Celery esté configurado en el MVP (Redis ya está en el stack como broker), migrar de `asyncio.create_task` a Celery:

**Qué cambia:**
- `backend/src/storico/infrastructure/tasks/extraction_task.py` — nueva tarea Celery
- `backend/src/storico/api/routes/extraction.py` — el POST encola la tarea Celery en vez de `create_task`
- `backend/src/storico/application/extraction/extract_from_story.py` — se mantiene igual (el use case es reutilizable)
- `docker-compose.yml` — agregar servicio `worker` (Celery)
- `pyproject.toml` — agregar `celery[redis]`

**Por qué migrar a Celery:**
- La extracción survive reinicios del servidor
- Workers separados no compiten con requests HTTP
- Cola FIFO con visibilidad (puedes ver cuántas extracciones están en cola)
- Escalable horizontalmente (múltiples workers)
- Redis ya está en el stack como dependencia

**Cuándo migrar:** Cuando se configure Celery en el MVP (item #8 de `prod.todo.md`). Hasta entonces, `asyncio.create_task` es suficiente.

---

## Frontend — polling

### taskStore.ts

```typescript
interface ExtractionState {
  extractionId: string | null;
  status: 'idle' | 'pending' | 'processing' | 'completed' | 'failed';
  error: string | null;
}

interface TaskState {
  tasks: Record<string, Task[]>;
  extractions: Record<string, ExtractionState>;  // keyed by storyId
  loading: boolean;
  error: string | null;

  extractTasks: (storyId: string, workspaceId: string) => Promise<void>;
  pollExtraction: (storyId: string, extractionId: string) => Promise<void>;
  fetchTasks: (storyId: string) => Promise<void>;
  // ...
}
```

**Polling logic:**

```typescript
extractTasks: async (storyId: string, workspaceId: string) => {
  set((state) => ({
    extractions: {
      ...state.extractions,
      [storyId]: { status: 'pending', error: null },
    },
  }));

  try {
    const result = await api.startExtraction(storyId, workspaceId);
    // result = { extraction_id, status: "pending" }

    // Start polling
    get().pollExtraction(storyId, result.extractionId);
  } catch (err) {
    set((state) => ({
      extractions: {
        ...state.extractions,
        [storyId]: { status: 'failed', error: err.message },
      },
    }));
  }
},

pollExtraction: async (storyId: string, extractionId: string) => {
  const poll = async () => {
    try {
      const status = await api.getExtractionStatus(extractionId);
      if (status === 'completed') {
        // Fetch tasks
        await get().fetchTasks(storyId);
        set((state) => ({
          extractions: {
            ...state.extractions,
            [storyId]: { status: 'completed' },
          },
        }));
      } else if (status === 'failed') {
        set((state) => ({
          extractions: {
            ...state.extractions,
            [storyId]: { status: 'failed', error: 'Extraction failed' },
          },
        }));
      } else {
        // Still pending/processing — poll again after delay
        setTimeout(() => get().pollExtraction(storyId), 2000);
      }
    } catch {
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: { status: 'failed', error: 'Polling failed' },
        },
      }));
    }
  };
```

---

## Archivos a modificar

### Backend

| Archivo | Cambio |
|---------|--------|
| `backend/src/storico/api/routes/extraction.py` | El POST crea `Extraction(status="pending")`, lanza `asyncio.create_task(background_extract(...))`, responde `202 Accepted` con `extraction_id` y `status: "pending"`. Nueva función `_run_background_extraction()` que ejecuta el use case y actualiza el status. |
| `backend/src/storico/application/extraction/extract_from_story.py` | Opcional: separar `execute` en `create_pending` + `run_extraction` para reutilización. |

### Frontend

| Archivo | Cambio |
|---------|--------|
| `frontend/src/lib/tasks-api.ts` | Nuevo método `startExtraction()` que llama al POST y devuelve `{ extractionId, status }`. Nuevo método `getExtractionStatus(extractionId)` que llama a `GET /api/v1/extractions/{extraction_id}`. |
| `frontend/src/stores/taskStore.ts` | `extracting: boolean` → `extractions: Record<string, ExtractionState>`. `extractTasks()` llama a `startExtraction()` e inicia polling. Nuevo método `pollExtraction()`. |
| `frontend/src/components/react/StoryDetail.tsx` | El botón usa `extractions[storyId].status` en vez de `extracting`. Muestra spinner en pending/processing, check en completed, error en failed. |

---

## Estados del botón

| Estado | Botón |
|--------|-------|
| `idle` | `[✨ Extract]` — habilitado |
| `pending` | `[⏳ Queued...]` — deshabilitado, spinner |
| `processing` | `[⏳ Processing...]` — deshabilitado, spinner |
| `completed` | `[✅ Extracted]` — deshabilitado, check |
| `failed` | `[⚠️ Retry]` — habilitado, permite reintentar |

---

## Migración futura a Celery (Opción 2)

Cuando Celery esté configurado en el MVP (item #8 de `prod.todo.md`), migrar de `asyncio.create_task` a Celery:

**Qué cambia:**

| Archivo | Cambio |
|---------|--------|
| `backend/src/storico/infrastructure/tasks/extraction_task.py` | Nueva tarea Celery `extract_from_story_task` que llama a `ExtractFromStoryUseCase.execute()` |
| `backend/src/storico/api/routes/extraction.py` | El POST encola `extract_from_story_task.delay(...)` en vez de `asyncio.create_task(...)` |
| `docker-compose.yml` | Agregar servicio `worker` que corre `celery -A storico.infrastructure.tasks worker` |
| `pyproject.toml` | Agregar `celery[redis]` |
| `backend/src/storico/infrastructure/tasks/__init__.py` | Nuevo módulo de tareas Celery |
| `backend/src/storico/infrastructure/tasks/extraction_task.py` | Definición de la tarea Celery |

**Por qué migrar:**
- La extracción survive reinicios del servidor
- Workers separados no compiten con requests HTTP
- Cola FIFO con visibilidad (puedes ver cuántas extracciones están en cola)
- Escalable horizontalmente (múltiples workers)
- Redis ya está en el stack como broker

**Cuándo migrar:** Cuando se configure Celery en el MVP (item #8 de `prod.todo.md`). Hasta entonces, `asyncio.create_task` es suficiente.

---

## Resumen de cambios

```
Backend:
  ✅ POST /extract/ → responde 202 Accepted inmediatamente
  ✅ GET /extractions/{id} → ya existe, devuelve status
  ✅ asyncio.create_task para background extraction
  ✅ Extraction(status="pending") se persiste antes de lanzar el background task

Frontend:
  ✅ taskStore: extracting boolean → extractionStatus state machine
  ✅ tasks-api: startExtraction() + getExtractionStatus()
  ✅ StoryDetail: botón con estados idle/pending/processing/completed/failed
  ✅ Polling cada 2s hasta que status cambie a completed o failed

Futuro (Celery):
  ⏳ Mover background task a Celery worker
  ⏳ docker-compose: agregar servicio worker
  ⏳ pyproject.toml: agregar celery[redis]
