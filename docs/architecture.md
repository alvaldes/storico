# Architecture

> Decisiones arquitectónicas de Storico, extraídas de `AGENTS.md`.
> Última actualización: 2026-07-15

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
| Modelos LLM cloud | OpenAI (GPT-4o-mini), Anthropic (Claude) |
| Modelos LLM local | Ollama (LLaMA 3.2, Mistral) |
| Base de datos relacional | PostgreSQL 16 |
| Base de datos vectorial | Qdrant |
| Procesamiento async | Celery + Redis |
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
│  │  LLM Adapters | DB | Qdrant | Redis | Export Adapters            │    │
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

**Decisión**: Primero Ollama (local), luego OpenAI y Anthropic.

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
- Redis solo como broker de Celery
- No hay caché semántico automático — siempre se llama al LLM con más contexto

### ADR-005: Despliegue

**Status**: 🔴 Pendiente (producción)

**Decisión**: Docker Compose para desarrollo. Producción sin definir.

**Contexto**: Desarrollo con Docker Compose (PostgreSQL, Qdrant, Redis, API). Producción pendiente.

**Preguntas abiertas**: Proveedor cloud? Serverless o contenedores? Modelos LLM locales vs cloud?

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
