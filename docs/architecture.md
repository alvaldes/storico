# Architecture

> Decisiones arquitectónicas de Storico, extraídas de `AGENTS.md`.
> Última actualización: 2026-09-28

## Stack

| Capa | Tecnología |
|------|-----------|
| Frontend framework | Astro + React (islas) |
| UI Components | shadcn (Radix UI + Tailwind) |
| Estilos | Tailwind CSS 4 |
| Iconos | Lucide |
| Estado frontend | Zustand 5 |
| Routing frontend | Astro Routing + View Transitions |
| Tema | Claro / Oscuro / Auto |
| Backend API | FastAPI (Python 3.12+) |
| Arquitectura backend | Hexagonal (Ports & Adapters) |
| Modelos LLM cloud | OpenAI (GPT-4o-mini), Anthropic (Claude), Gemini (Gemini 2.0 Flash) |
| Modelos LLM local | Ollama (LLaMA 3.2, Mistral) |
| Base de datos relacional | PostgreSQL 16 |
| Base de datos vectorial | Qdrant |
| Procesamiento async | `asyncio.create_task` en el proceso de la API |
| Autenticación | Auth.js (OAuth) con Google + GitHub |
| Testing | pytest + pytest-asyncio + httpx (backend), Vitest (frontend) |
| Internacionalización | Astro i18n (en/es) |
| Contenedores | Docker / Docker Compose |

## Diagrama de Arquitectura

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            STORICO SYSTEM                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │              FRONTEND (Astro Routing + View Transitions)          │    │
│  │                                                                   │    │
│  │  ┌───────────────────────────────────────────────────────────┐   │    │
│  │  │              Astro (layout, routing, pages)                │   │    │
│  │  │                                                           │   │    │
│  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐       │   │    │
│  │  │  │Dashboard │ │  User    │ │  Kanban  │ │ Config │       │   │    │
│  │  │  │Proyectos │ │  Stories │ │  Board   │ │  LLM   │       │   │    │
│  │  │  └──────────┘ └──────────┘ └──────────┘ └────────┘       │   │    │
│  │  └───────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────┬────────────────────────────────────┘    │
│                                │ HTTP REST + JWT                         │
│                                ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                   API GATEWAY (FastAPI)                           │    │
│  └─────────────────────────────┬────────────────────────────────────┘    │
│                                │                                         │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                 APPLICATION LAYER (Use Cases)                     │    │
│  │  TaskExtractionUseCase | ProjectMgmtUseCase | ExportUseCase      │    │
│  └─────────────────────────────┬────────────────────────────────────┘    │
│                                │                                         │
│  ┌─────────────────────────────▼────────────────────────────────────┐    │
│  │                      DOMAIN LAYER                                │    │
│  │  Services, Entities, Ports (interfaces) — puro negocio           │    │
│  └─────────────────────────────┬────────────────────────────────────┘    │
│                                │                                         │
│  ┌─────────────────────────────▼────────────────────────────────────┐    │
│  │                   INFRASTRUCTURE (Adapters)                       │    │
│  │            LLM Adapters | DB | Qdrant | Export Adapters          │    │
│  └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────┘
```

## Capas y Comunicación

| Capa | Depende de | Comunicación |
|------|-----------|-------------|
| Frontend (Astro) | API Gateway vía HTTP | REST + JSON + JWT |
| API Gateway (FastAPI) | Application Layer | In-process (Python) |
| Application Layer | Domain Layer (ports) | Interfaces/ABC |
| Domain Layer | Nadie (puro negocio) | — |
| Infrastructure | Domain Layer (ports) | Implementa interfaces |

## Decisiones Arquitectónicas (ADRs)

### ADR-001: Frontend Framework

**Status**: ✅ Implementado

**Decisión**: Astro Routing + View Transitions con islas React.

**Contexto**: Astro maneja routing, pages y layout. React se limita a islas de interactividad (formularios, kanban, editores). View Transitions da navegación fluida sin cargar una SPA pesada.

**Consecuencias**:
- Astro maneja todas las páginas y rutas (`src/pages/`)
- View Transitions para navegación fluida entre páginas
- React solo para islas individuales, no como SPA
- Sin React Router — el routing lo resuelve Astro
- Zustand para estado global compartido entre islas

### ADR-002: Estrategia de Modelos LLM

**Status**: ✅ Implementado

**Decisión**: Primero Ollama (local), luego OpenAI, Anthropic y Gemini.

**Contexto**: Modelos locales evitan dependencia de API keys y costos durante desarrollo. La arquitectura hexagonal permite agregar conectores sin modificar el core.

**Consecuencias**: El adaptador LLM debe tener una interfaz genérica desde el día 1 (`LLMPort`).

### ADR-003: Autenticación y Permisos

**Status**: ✅ Implementado

**Decisión**: Auth.js (OAuth) con Google + GitHub. Registro abierto. Workspaces con roles.

**Contexto**: Sin manejo de passwords. Auth.js funciona con Astro. Workspaces con jerarquía Admin → Miembro.

**Consecuencias**:
- Sin registro por email+password — solo OAuth
- Sin recovery de contraseña
- Auth.js maneja sesiones vía JWT
- Modelo de permisos: Admin → Workspace → Miembros
- Solo admins crean workspaces y asignan usuarios

### ADR-004: Base de Datos

**Status**: ✅ Implementado

**Decisión**: PostgreSQL (relacional) + Qdrant (vectorial).

**Contexto**: PostgreSQL para datos relacionales. Qdrant para embeddings del historial de extracciones (RAG).

**Consecuencias**:
- PostgreSQL para todos los datos relacionales
- Qdrant para vectores del historial de extracciones
- Redis y Celery se retiraron: las tareas en segundo plano corren en el bucle de eventos del proceso de la API
- No hay caché semántico automático — siempre se llama al LLM con más contexto

### ADR-005: Despliegue

**Status**: ✅ Implementado (producción en marcha desde 2026-09)

**Decisión**: Docker Compose para desarrollo. Producción: el frontend Astro se sirve desde Vercel, el backend FastAPI corre en un contenedor Docker sobre una VM de Oracle, la base de datos relacional está en Neon y el vector store en Qdrant Cloud —un solo cluster, con una colección por entorno—.

**Contexto**: El backend se despliega con `.github/workflows/deploy-backend.yml`, que entra por SSH a la VM (el host sale del secret `DEPLOY_HOST`), resetea el árbol de trabajo a `origin/main`, reconstruye la imagen y arranca con `docker run --network host --env-file /home/ubuntu/storico/backend/.env`. Las migraciones se aplican en una ventana de mantenimiento, entre el `docker stop` y el `docker run`. El detalle de variables y caminos por entorno está en `docs/deployment.md`, que es la autoridad de despliegue: este ADR sólo registra la decisión.

**Consecuencias**: El archivo de variables vive en la VM y fuera del control de versiones, así que el reset del árbol de trabajo no lo toca: una variable que falte falla en silencio en producción. El despliegue cuesta downtime durante la migración y un fallo deja la API abajo a propósito, que es la lección del incidente del 2026-09-20. Front y API son dos orígenes distintos (`storico.vercel.app` y `storico-api.<vm>.sslip.io`) sin dominio propio, decisión cerrada el 2026-09-23.

**Preguntas abiertas**: Cómo se alojan los modelos LLM locales frente a los cloud. Ollama no corre en producción a propósito: el probe responde `not reachable` y su `scope` es `optional`, así que no degrada el estado del servicio. La habilitación de Qdrant en producción **deja de ser una pregunta abierta**: está operativo y medido el 2026-09-28 desde `/api/v1/health/services` (`qdrant: ok`, `embeddings: ok` con `google` / `gemini-embedding-001` / 768).

### ADR-006: UI Component Library y Estilos

**Status**: ✅ Implementado

**Decisión**: shadcn + Tailwind CSS 4 + Lucide.

**Contexto**: Sistema de componentes consistente, accesible y personalizable. shadcn sobre Radix UI con Tailwind.

**Consecuencias**:
- Componentes instalados vía `npx shadcn add` — se copian a `src/components/ui/`
- Personalización directa sobre el código generado
- Tailwind 4 con CSS-first config (`@theme` directive)
- Lucide como librería única de iconos

### ADR-007: Sistema de Tema

**Status**: ✅ Implementado

**Decisión**: Tema claro y oscuro con shadcn + Tailwind + ThemeProvider.

**Contexto**: shadcn soporta tema oscuro/claro nativamente mediante CSS variables y Tailwind.

**Consecuencias**:
- Variables CSS para colores en `globals.css`
- Toggle de tema en el header
- Persistencia en localStorage
- Modo "auto" (sigue al sistema) + override manual

### ADR-008: Internacionalización

**Status**: ✅ Implementado

**Decisión**: Astro i18n. Español e inglés. User stories solo en inglés.

**Contexto**: Evaluación en español, público objetivo internacional. `astro:i18n` maneja locale routing.

**Consecuencias**:
- `astro:i18n` para routing de locales y detección de idioma
- Archivos de traducción: `en.json` y `es.json`
- User stories SIEMPRE en inglés con formato INVEST
- Labels, botones, mensajes traducibles
- Tareas generadas en inglés (output del LLM)
- Prompts del sistema en español

### ADR-009: Reutilización de Código Existente

**Status**: ✅ Implementado

**Decisión**: Revisar y reutilizar LocalLLM-DataForge y csv2trello antes de escribir código nuevo.

**Contexto**: Dos herramientas funcionales de la investigación contienen lógica ya probada.

**Consecuencias**:
- Motor de extracción basado en prompts validados en LocalLLM-DataForge
- Conector Trello reutiliza lógica de csv2trello
- Parsing de respuestas LLM hereda ExplodeTasks de DataForge
- Validación LLM-as-a-Judge basada en OllamaJudgeStep
- Storico NO copia la arquitectura de pipeline de DataForge

## Flujo de Datos Típico

```
Browser → Astro UI → HTTP POST /extract → FastAPI → TaskExtractionUseCase
  → LLMPort (interfaz) → OllamaAdapter (implementación) → Ollama API
  → respuesta → TaskValidator → persistir en DB + Qdrant → respuesta JSON → Browser
```
