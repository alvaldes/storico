# Storico — Definición Completa

> **Documento autónomo** — contiene TODO el contexto de la tesis y la definición de la herramienta.
> **Última actualización**: 2026-07-03 — Actualización frontend: Astro Routing + View Transitions, islas React, Tailwind 4, shadcn, Lucide, tema claro/oscuro
>
> Si estás leyendo esto en un proyecto nuevo, el contexto completo está aquí. No necesitas la tesis original.

---

## 📋 Índice

1. [Contexto de la tesis](#1-contexto-de-la-tesis)
2. [Identidad de Storico](#2-identidad-de-storico)
3. [Problema que resuelve](#3-problema-que-resuelve)
4. [Stack tecnológico](#4-stack-tecnológico)
5. [Decisiones arquitectónicas (ADR)](#5-decisiones-arquitectónicas-adr)
6. [Arquitectura de componentes](#6-arquitectura-de-componentes)
7. [Features por módulo](#7-features-por-módulo)
8. [Pipeline de extracción](#8-pipeline-de-extracción)
9. [Modelo de lenguaje](#9-modelo-de-lenguaje)
10. [Framework auxiliar: LocalLLM-DataForge](#10-framework-auxiliar-localllm-dataforge)
11. [Evaluación experimental](#11-evaluación-experimental)
12. [Estructura del frontend](#12-estructura-del-frontend)
13. [Preguntas abiertas](#13-preguntas-abiertas)
14. [Glosario](#14-glosario)
15. [Referencias](#15-referencias)

---

## 1. Contexto de la tesis

### Datos generales

| Campo            | Valor                                                                                                |
| ---------------- | ---------------------------------------------------------------------------------------------------- |
| **Título**       | Identificación automática de tareas a partir de historias de usuario con modelos de lenguaje natural |
| **Autor**        | Ing. Angel Luis Valdés Sánchez                                                                       |
| **Institución**  | Universidad Tecnológica de la Mixteca (UTM), Oaxaca, México                                          |
| **Programa**     | Maestría en Ingeniería en Software                                                                   |
| **Director**     | Dr. Carlos Alberto Fernández y Fernández                                                             |
| **Co-directora** | Dra. Verónica Rodríguez López                                                                        |
| **Año**          | 2026                                                                                                 |

### Resumen de la tesis

> En el desarrollo de software ágil, las historias de usuario son esenciales para capturar requisitos, pero su descomposición manual en tareas es tediosa y propensa a errores. Esta tesis desarrolló una herramienta computacional basada en LLMs para automatizar la identificación de tareas a partir de historias de usuario, integrando la metodología Kanban para la gestión visual. La evaluación —aún pendiente— contempla un análisis comparativo con métodos manuales considerando precisión, claridad, velocidad y satisfacción del usuario. Se espera que la herramienta optimice la gestión de tareas y mejore la calidad de los productos entregados, aunque esto está por validarse.

### Hipótesis

> El uso de modelos de lenguaje natural preentrenados para extraer automáticamente tareas a partir de historias de usuario en proyectos de desarrollo de software ágil, en combinación con tableros Kanban, **reducirá el tiempo** que los equipos dedican a clarificar tareas y **mejorará su comprensión**.

### Metodología

La investigación se enmarca en el paradigma de **Design Science Research** (Hevner et al., 2004), con un ciclo iterativo de construcción-evaluación en 3 etapas:

1. **Etapa 1 — Análisis y fundamentación**: Revisión del estado del arte, recolección y preparación de datos, comparación inicial de modelos LLM
2. **Etapa 2 — Desarrollo e implementación**: Configuración del modelo, construcción de la API, adaptación a formato Kanban
3. **Etapa 3 — Evaluación y validación**: Juicio de expertos (n=6 entre Scrum Masters y Product Owners), comparación manual vs automático, métricas TCR/TAS/IFI

---

## 2. Identidad de Storico

### Nombre

**Storico**

### Descripción ejecutiva

> Storico is an LLM-powered tool that automates decomposing natural language user stories into structured Kanban tasks, exporting directly to project management tools like Trello.
>
> Built on a microservices-based hexagonal architecture with a FastAPI REST API and intuitive web UI, it features configurable connectors for cloud-based and local models via Ollama. Performance is optimized via semantic caching, synchronous/asynchronous batch processing, and an automated LLM-as-a-Judge validation mechanism.
>
> It enables agile teams to reduce planning time, eliminate misinterpretations, and maintain strict traceability from high-level requirements to concrete implementation tasks.

### Audiencia objetivo

- Equipos ágiles de desarrollo de software
- Scrum Masters, Product Owners, Tech Leads
- Equipos que usan Kanban como metodología de gestión

---

## 3. Problema que resuelve

### El problema

- El **66% de los proyectos** de software fallan parcial o totalmente (CHAOS Report 2020)
- El **58% de equipos ágiles** usan historias de usuario como fuente principal de requisitos
- La descomposición **manual** de historias en tareas es inconsistente, tediosa y propensa a errores
- No existen **datasets públicos** con historias de usuario descompuestas en tareas (ground truth)

### La solución

Storico automatiza el paso de "requisito expresado en lenguaje natural" → "tareas técnicas estructuradas" → "tablero Kanban listo para ejecución", cerrando la brecha entre el análisis de requisitos y la planificación operativa.

---

## 4. Stack tecnológico

| Capa                       | Tecnología                                  | Status         | Notas                                                                     |
| -------------------------- | ------------------------------------------- | -------------- | ------------------------------------------------------------------------- |
| **Frontend framework**     | **Astro** + **React** (islas)               | ✅ Decidido    | Astro maneja routing y pages; React solo para islas interactivas          |
| **UI Components**          | **shadcn**                                  | ✅ Decidido    | Sistema de componentes sobre Radix UI                                     |
| **Estilos**                | **Tailwind CSS 4**                          | ✅ Decidido    | Utility-first CSS con nueva engine                                        |
| **Iconos**                 | **Lucide**                                  | ✅ Decidido    | Iconos open-source consistentes                                           |
| **Estado frontend**        | **Zustand**                                 | ✅ Decidido    | Manejo de estado global liviano para islas React                          |
| **Routing frontend**       | **Astro Routing** + **View Transitions**    | ✅ Decidido    | Routing nativo de Astro con transiciones fluídas entre páginas           |
| **Tema**                   | Claro / Oscuro                              | ✅ Decidido    | Soporte nativo con shadcn + Tailwind                                      |
| **API Client**             | **fetch** nativo                            | ✅ Decidido    | Abstracción intercambiable para migrar a Axios si es necesario            |
| **Backend API**            | **FastAPI** (Python 3.9+)                   | ✅ De la tesis | Async, tipado fuerte, OpenAPI automático                                  |
| **Arquitectura**           | **Hexagonal** (Ports & Adapters)            | ✅ De la tesis | Separación dominio / aplicación / infraestructura                         |
| **Modelos LLM cloud**      | OpenAI (GPT-3.5, GPT-4), Anthropic (Claude) | 🔜 Post-MVP    | A través de API key                                                       |
| **Modelos LLM local**      | **Ollama** (LLaMA 3.2, Mistral, etc.)       | ✅ MVP         | Prioridad inicial                                                         |
| **Base de datos relacional** | **PostgreSQL**                              | ✅ Decidido    | Datos de proyectos, user stories, tareas, usuarios                        |
| **Base de datos vectorial** | **Qdrant**                                 | ✅ Decidido    | Historial de extracciones para contexto de LLM (RAG)                      |
| **Procesamiento async**    | Celery + Redis                              | ✅ De la tesis | Workers para batch processing                                             |
| **Autenticación**          | **Auth.js** (OAuth)                          | ✅ Decidido    | Login con Google y GitHub. Registro abierto, sin passwords                 |
| **Testing**                | pytest                                      | ✅ De la tesis | Unitarias, integración. Sin E2E por ahora (se puede agregar futuro)       |
| **Internacionalización**   | **Astro i18n**                              | ✅ Decidido    | Español e inglés. User stories solo en inglés                             |
| **Fuentes tipográficas**   | **Google Fonts** (variable fonts)           | ✅ Decidido    | Para identidad visual de Storico                                           |
| **Contenedores**           | Docker / Docker Compose                     | Asumido        | Desarrollo y producción                                                   |

### Selección del modelo LLM (de la tesis) ⏳ PENDIENTE

> **⚠️ Nota**: Esta evaluación no se ha realizado aún. La tabla siguiente es un **ejemplo ilustrativo** del tipo de datos que se espera obtener —los valores son referenciales y no representan resultados reales. Esta sección se actualizará cuando la evaluación esté completa.

| Modelo            | Precisión | Consistencia | Velocidad | Costo                |
| ----------------- | --------- | ------------ | --------- | -------------------- |
| **GPT-4**         | —         | —            | —         | $0.03/1K tokens      |
| **GPT-3.5-turbo** | —         | —            | —         | **$0.002/1K tokens** |
| Claude-3          | —         | —            | —         | $0.015/1K tokens     |
| LLaMA-2-70B       | —         | —            | —         | $0 (infra propia)    |
| Mistral-7B        | —         | —            | —         | $0 (infra propia)    |

> **📋 Plan de evaluación**: Se probarán los mismos 5 modelos con un conjunto de ~50 historias de usuario. Las métricas a medir incluyen precisión, consistencia, velocidad de respuesta, y costo por extracción. Los resultados reemplazarán los guiones en la tabla.

**Estrategia**: MVP con Ollama (modelos locales), luego agregar OpenAI y Anthropic.

---

## 5. Decisiones arquitectónicas (ADR)

### ADR-001: Frontend Framework

- **Status**: ✅ Decidido
- **Decisión**: **Astro Routing + View Transitions con islas React**
- **Contexto**: Se evaluaron Angular, React, Vue. Se eligió **Astro** como framework principal que maneja routing, pages y layout, con **React** limitado a islas de interactividad donde se necesita estado complejo (formularios, kanban, editores). Astro Routing + View Transitions da navegación fluida sin cargar una SPA pesada. Esto evita JavaScript innecesario en páginas estáticas y da lo mejor de ambos mundos: renderizado del lado servidor con transiciones client-side suaves.
- **Consecuencias**:
  - Astro maneja **todas las páginas y rutas** (`src/pages/`)
  - View Transitions para navegación fluida entre páginas sin recarga completa
  - React solo para **islas individuales** (componentes interactivos), no como SPA
  - Sin React Router — el routing lo resuelve Astro nativamente
  - Zustand para estado global compartido entre islas React
  - Carga inicial más liviana: cada página solo envía el JS de sus islas

### ADR-002: Estrategia de modelos LLM

- **Status**: ✅ Decidido
- **Decisión**: **Primero Ollama (local)**, luego OpenAI y Anthropic
- **Contexto**: Empezar con modelos locales evita dependencia de API keys y costos durante desarrollo. La arquitectura hexagonal permite agregar conectores sin modificar el core.
- **Consecuencias**: El adaptador LLM debe tener una interfaz genérica desde el día 1.

### ADR-003: Autenticación y Permisos

- **Status**: ✅ Decidido
- **Decisión**: **Auth.js (OAuth) con Google + GitHub. Registro abierto. Admins pueden crear workspaces y asignar usuarios a equipos.**
- **Contexto**: Se necesita un sistema de autenticación que no requiera manejo de passwords. Auth.js es la evolución de NextAuth.js y funciona con cualquier framework (incluyendo Astro). Soporta múltiples proveedores OAuth, sesiones JWT, y callbacks para control de acceso. Para permisos, se definió un modelo de workspaces y equipos donde solo admins pueden crear workspaces y administrar membresías.
- **Consecuencias**:
  - Sin registro por email+password — solo OAuth (Google, GitHub)
  - Sin recovery de contraseña (no aplica)
  - Auth.js maneja sesiones vía JWT o base de datos
  - Modelo de permisos: Admin → Workspace → Equipos → Usuarios
  - Solo admins pueden crear workspaces y asignar usuarios a equipos
  - Usuarios regulares pueden pertenecer a múltiples equipos/workspaces

### ADR-004: Base de Datos

- **Status**: ✅ Decidido
- **Decisión**: **PostgreSQL (relacional) + Qdrant (vectorial)**
- **Contexto**: Necesitamos persistencia relacional para proyectos, user stories, tareas y usuarios, más almacenamiento vectorial para el historial de extracciones. PostgreSQL es la opción más madura para datos relacionales. Qdrant almacena los embeddings de las extracciones previas para que el LLM pueda consultar contextos similares en ejecuciones futuras (patrón RAG — Retrieval-Augmented Generation), sin reemplazar la llamada al modelo.
- **Consecuencias**:
  - PostgreSQL para todos los datos relacionales de la aplicación
  - Qdrant para vectores del historial de extracciones — el LLM consulta contexto previo relevante antes de extraer
  - No hay "caché semántico" automático — siempre se llama al LLM, pero con más contexto
  - Redis queda solo como broker de Celery para procesamiento asíncrono

### ADR-005: Despliegue

- **Status**: 🔴 **PENDIENTE** (producción)
- **Decisión**: **Docker Compose para desarrollo.** Producción sin definir.
- **Contexto**: Para desarrollo se usará Docker Compose con los servicios necesarios (PostgreSQL, Qdrant, Redis, API). Para producción queda pendiente definir el proveedor cloud y la estrategia de despliegue.
- **Preguntas**: Proveedor cloud? Serverless o contenedores? Cómo se alojan los modelos LLM locales vs cloud?

### ADR-006: UI Component Library y Estilos

- **Status**: ✅ Decidido
- **Decisión**: **shadcn + Tailwind CSS 4 + Lucide icons**
- **Contexto**: Se necesita un sistema de componentes consistente, accesible y personalizable. shadcn provee componentes sobre Radix UI (accesibles, headless) con styling via Tailwind. No es una dependencia npm — los componentes se copian al proyecto y se personalizan directamente.
- **Consecuencias**:
  - Componentes instalados vía `npx shadcn add` — se copian a `src/components/ui/`
  - Personalización directa sobre el código generado
  - Tailwind 4 con nueva engine (CSS-first config, `@theme` directive)
  - Lucide como librería única de iconos (consistencia visual)
  - Sin dependencias UI pesadas (no Material UI, no Ant Design)

### ADR-007: Sistema de Tema (Claro / Oscuro)

- **Status**: ✅ Decidido
- **Decisión**: **Tema claro y oscuro con shadcn + Tailwind + `next-themes` (o equivalente)**
- **Contexto**: shadcn soporta tema oscuro/claro nativamente mediante CSS variables y Tailwind. Se usará un `ThemeProvider` que detecte preferencia del sistema y permita toggle manual.
- **Consecuencias**:
  - Variables CSS para colores definidas en `globals.css`
  - Toggle de tema en el header de la app
  - Persistencia de preferencia en localStorage
  - Modo "auto" (sigue al sistema) + override manual

### ADR-008: Internacionalización

- **Status**: ✅ Decidido
- **Decisión**: **Astro i18n. Español e inglés. User stories solo en inglés.**
- **Contexto**: La herramienta será evaluada en español (tesis, juicio de expertos) pero el público objetivo son equipos ágiles internacionales. Con Astro manejando routing y pages, su sistema de i18n nativo (`astro:i18n`) es la opción correcta — maneja locale routing, detección de idioma y traducciones a nivel de página/layout. Las islas React reciben el locale como props, sin necesidad de un sistema de i18n separado en React. Las user stories como insumo deben estar en inglés porque los modelos LLM fueron entrenados predominantemente en ese idioma y su rendimiento es superior. La UI debe soportar ambos idiomas para cubrir ambos casos de uso.
- **Consecuencias**:
  - `astro:i18n` para routing de locales y detección de idioma
  - Archivos de traducción: `en.json` y `es.json`
  - Detección de idioma por preferencia del navegador + override manual
  - Las user stories ingresadas por el usuario SIEMPRE en inglés con la estructura "As a(n) [role], I want [feature], so that [benefit]" — validación en el formulario
  - Labels, botones, mensajes de error, tooltips traducibles
  - Las tareas generadas y etiquetas técnicas se devuelven en inglés (output del LLM)
  - Los prompts del sistema y las instrucciones al LLM están en español (como se definió en la tesis)

### ADR-009: Reutilización de código existente

- **Status**: ✅ Decidido
- **Decisión**: **Siempre revisar y reutilizar lo existente en LocalLLM-DataForge y csv2trello antes de escribir código nuevo en Storico.**
- **Contexto**: Durante la investigación se desarrollaron dos herramientas funcionales: **LocalLLM-DataForge** (framework de pipelines de extracción con LLMs) y **csv2trello** (CLI/TUI para importar CSV a Trello vía API). Ambas contienen lógica ya probada, testeada y revisada: parsing de respuestas LLM, validación LLM-as-a-Judge, pipeline de extracción, integración con Trello API, manejo de errores con reintentos, caché, etc. Reescribir desde cero en Storico introduce riesgo de errores ya resueltos y duplica esfuerzo.
- **Consecuencias**:
  - El **motor de extracción** de Storico debe basarse en los prompts y el pipeline validados en LocalLLM-DataForge
  - El **conector Trello** debe reutilizar la lógica de `csv2trello/core/` (autenticación, creación de boards/listas/cards)
  - El parsing de respuestas LLM (texto plano con `summary:` / `description:`) debe heredar el `ExplodeTasks` de DataForge
  - La validación LLM-as-a-Judge debe basarse en `OllamaJudgeStep` + `single_judge.j2`
  - Cualquier funcionalidad nueva se evalúa primero contra estas dos bases de código antes de implementar
  - Storico **no copia** la arquitectura de pipeline de DataForge (Storico usa hexagonal, no pipeline de datos)

---

## 6. Arquitectura de componentes

### Diagrama de bloques

```
┌──────────────────────────────────────────────────────────────────────────┐
│                            STORICO SYSTEM                                │
├──────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────┐    │
  │  │              FRONTEND (Astro Routing + View Transitions)         │    │
  │  │                                                                   │    │
  │  │  ┌───────────────────────────────────────────────────────────┐   │    │
  │  │  │              Astro (layout, routing, pages)               │   │    │
  │  │  │  ┌─────────────────────────────────────────────────────┐ │   │    │
  │  │  │  │  🌓 ThemeToggle  🔔 Notifications  👤 UserMenu      │ │   │    │
  │  │  │  └─────────────────────────────────────────────────────┘ │   │    │
  │  │  │                                                           │   │    │
  │  │  │  ┌─────────────────────────────────────────────────────┐ │   │    │
  │  │  │  │  Páginas Astro (.astro) + islas React donde          │ │   │    │
  │  │  │  │  se necesita interactividad (formularios, kanban,   │ │   │    │
  │  │  │  │  editores, etc.)                                     │ │   │    │
  │  │  │  │                                                       │ │   │    │
  │  │  │  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────┐ │ │   │    │
  │  │  │  │  │Dashboard │ │  User    │ │  Kanban  │ │ Config │ │ │   │    │
  │  │  │  │  │Proyectos │ │  Stories │ │  Board   │ │  LLM   │ │ │   │    │
  │  │  │  │  └──────────┘ └──────────┘ └──────────┘ └────────┘ │ │   │    │
  │  │  │  └─────────────────────────────────────────────────────┘ │   │    │
  │  │  └───────────────────────────────────────────────────────────┘   │    │
│  └─────────────────────────────┬────────────────────────────────────┘    │
│                                │ HTTP REST + JWT                         │
│                                ▼                                         │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                   API GATEWAY (FastAPI)                           │    │
│  │                                                                   │    │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐  ┌──────────────┐  │    │
│  │  │Extraction │  │ Projects  │  │   Tasks   │  │   Export     │  │    │
│  │  │ Endpoints │  │ Endpoints │  │ Endpoints │  │  Endpoints   │  │    │
│  │  └───────────┘  └───────────┘  └───────────┘  └──────────────┘  │    │
│  └─────────────────────────────┬────────────────────────────────────┘    │
│                                │                                         │
│  ┌──────────────────────────────────────────────────────────────────┐    │
│  │                 APPLICATION LAYER (Use Cases)                     │    │
│  │                                                                   │    │
│  │  ┌────────────────────┐  ┌──────────────────┐  ┌──────────────┐  │    │
│  │  │  TaskExtraction    │  │ ProjectMgmt      │  │   Export     │  │    │
│  │  │  UseCase           │  │ UseCase          │  │   UseCase    │  │    │
│  │  └─────────┬──────────┘  └──────────────────┘  └──────────────┘  │    │
│  └────────────┼─────────────────────────────────────────────────────┘    │
│               │                                                          │
│  ┌────────────┼──────────────────────────────────────────────────────┐   │
│  │            ▼                DOMAIN LAYER                          │   │
│  │                                                                   │   │
│  │  ┌───────────────────────────────────────────────────────────┐    │   │
│  │  │  Services: TaskExtraction | UserStoryValidator |           │    │   │
│  │  │           TaskValidator | KanbanMapper                     │    │   │
│  │  ├───────────────────────────────────────────────────────────┤    │   │
│  │  │  Entities: UserStory | Task | Project | User              │    │   │
│  │  └───────────────────────────────────────────────────────────┘    │   │
│  └───────────────────────────────┬───────────────────────────────────┘   │
│                                  │                                       │
│  ┌───────────────────────────────┼───────────────────────────────────┐   │
│  │                               ▼    INFRASTRUCTURE (Adapters)        │   │
│  │                                                                     │   │
│  │  ┌─────────────────────────┐  ┌──────────────────────────────────┐ │   │
│  │  │    LLM Adapters         │  │   DB / Vector Adapter            │ │   │
│  │  │                         │  │                                  │ │   │
│  │  │  ┌──────┐ ┌──────┐    │  │  ┌────────────────────────────┐  │ │   │
│  │  │  │Ollama│ │OpenAI│    │  │  │  PostgreSQL                 │  │ │   │
│  │  │  └──────┘ └──────┘    │  │  └────────────────────────────┘  │ │   │
│  │  │  ┌──────┐ ┌────────┐  │  │  ┌────────────────────────────┐  │ │   │
│  │  │  │Claude│ │(futuro) │  │  │  │  Qdrant (historial         │  │ │   │
│  │  │  └──────┘ └────────┘  │  │  │  de extracciones)           │  │ │   │
│  │  └─────────────────────────┘  └──────────────────────────────────┘ │   │
│  │                                                                     │   │
│  │  ┌─────────────────────────┐  ┌──────────────────────────────────┐ │   │
│  │  │   Async Broker         │  │   Export Adapters                │ │   │
│  │  │                         │  │                                  │ │   │
│  │  │  ┌───────────────────┐  │  │  ┌──────┐ ┌──────┐ ┌─────────┐ │ │   │
│  │  │  │     Redis         │  │  │  │Trello│ │ Jira │ │ GitHub  │ │ │   │
│  │  │  │  (Celery broker)  │  │  │  └──────┘ └──────┘ │ Projects│ │ │   │
│  │  │  └───────────────────┘  │  │  ┌──────┐ ┌──────┐ └─────────┘ │ │   │
│  │  └─────────────────────────┘  │  │Azure │ │(fut.)│             │ │   │
│  │                              │  │DevOps│ └──────┘             │ │   │
│  │                              │  └──────┘                       │ │   │
│  │                              └──────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│     ┌──────────────────────────────────────────────────────────────────┐    │
│     │              BACKGROUND WORKERS (Celery)                         │    │
│     │                                                                  │    │
│     │  ┌──────────────────────────┐  ┌─────────────────────────────┐  │    │
│     │  │  Batch Extraction Worker │  │  Data Generation Worker     │  │    │
│     │  │  (procesa lotes async)   │  │  (LocalLLM-DataForge)       │  │    │
│     │  └──────────────────────────┘  └─────────────────────────────┘  │    │
│     └──────────────────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Relaciones entre capas

| Capa                  | Depende de           | Comunicación          |
| --------------------- | -------------------- | --------------------- |
| Frontend (Astro)      | API Gateway vía HTTP | REST + JSON + JWT     |
| API Gateway (FastAPI) | Application Layer    | In-process (Python)   |
| Application Layer     | Domain Layer (ports) | Interfaces/ABC        |
| Domain Layer          | Nadie (puro negocio) | —                     |
| Infrastructure        | Domain Layer (ports) | Implementa interfaces |
| Workers (Celery)      | Redis + Domain       | Mensajes async        |

### Flujo de datos típico

```
Browser → Astro UI → HTTP POST /extract → FastAPI → TaskExtractionUseCase
  → LLMPort (interfaz) → OllamaAdapter (implementación) → Ollama API
  → respuesta → TaskValidator → persistir en DB + Qdrant → respuesta JSON → Browser
```

---

## 7. Features por módulo

### 🧠 Core — Motor de extracción (MVP)

| #   | Feature                      | Descripción                                                                                                                  |
| --- | ---------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 1   | Extracción por LLM           | Dada una user story en inglés con formato "As a(n) [role], I want [feature], so that [benefit]", genera 3-8 tareas con título, descripción, etiquetas (categoría técnica: frontend, backend, api, testing, db, ui/ux, devops; o ámbito: módulo/funcionalidad) y dependencias (orden de ejecución: referencias a tareas predecesoras por índice o nombre) |
| 2   | Sistema de prompts multicapa | System prompt ("analista de requisitos ágiles") + instruction prompt + format prompt con few-shot learning (2-3 ejemplos)    |
| 3   | Editor de prompts           | Personalización de prompts del sistema desde configuración del workspace (solo admins)                                      |
| 4   | Soporte Ollama               | Conexión con modelos locales vía API de Ollama (LLaMA 3.2, Mistral)                                                          |
| 5   | Procesamiento batch          | Extracción asíncrona de múltiples user stories vía Celery                                                                    |
| 6   | Validación LLM-as-a-Judge    | Evaluación automática de calidad (coherencia, granularidad, relevancia)                                                      |
| 7   | Contexto histórico (RAG)    | Consulta extracciones previas en Qdrant para incluir ejemplos similares en el prompt del LLM                                 |
| 8   | Refinamiento post-extracción | Deduplicación, validación de dependencias, verificación de coherencia                                                        |

### 🔌 API REST — FastAPI (MVP)

| #   | Feature               | Descripción                         |
| --- | --------------------- | ----------------------------------- |
| 9   | `POST /extract`       | Extrae tareas de una user story     |
| 10  | `POST /batch`         | Procesamiento en lote y paralelo (usa múltiples GPUs si están disponibles)               |
| 11  | `GET /status/{id}`    | Estado de procesamiento asíncrono   |
| 12  | CRUD de proyectos     | Crear, listar, actualizar, eliminar |
| 13  | CRUD de workspaces    | Crear, listar, administrar miembros y equipos |
| 14  | CRUD de user stories  | Gestión completa                    |
| 15  | CRUD de tareas        | Gestión completa                    |
| 16  | Configuración workspace | Prompts del sistema, modelo LLM, preferencias |
| 17  | Documentación Swagger | OpenAPI generado por FastAPI        |

### 🗄️ Persistencia (MVP)

| #   | Feature           | Descripción                                                                     |
| --- | ----------------- | ------------------------------------------------------------------------------- |
| 18  | Base de datos     | Proyectos, user stories, tareas, configuraciones (PostgreSQL)                           |
| 19  | Base de vectores  | Historial de extracciones con embeddings en Qdrant para contexto del LLM (RAG)          |
| 20  | Manejo de errores | Reintentos con backoff exponencial, dead letter queue                           |

### 📤 Exportación (MVP → V2)

| #   | Feature                       | Prioridad |
| --- | ----------------------------- | --------- |
| 21  | Exportación JSON estructurado | MVP       |
| 22  | Exportación Markdown          | MVP       |
| 23  | Exportación CSV               | V2        |
| 24  | Exportación XML               | V3        |

### 🔗 Conectores (MVP → V3)

| #   | Feature                  | Prioridad |
| --- | ------------------------ | --------- |
| 25  | Conector Trello          | ✅ MVP    |
| 26  | Conector Jira            | V2        |
| 27  | Conector GitHub Projects | V2        |
| 28  | Conector Azure DevOps    | V3        |

### 🖥️ Frontend — Astro + React Islands (MVP)

| #   | Feature                | Tipo                | Descripción                                                                                  |
| --- | ---------------------- | ------------------- | -------------------------------------------------------------------------------------------- |
| 29  | Dashboard de proyectos | Astro + React       | Vista general con cards de proyectos y métricas                                              |
| 30  | Gestor de user stories | Astro + React       | Formulario estructurado + listado con estados                                                |
| 31  | Kanban board visual    | Astro + React       | Columnas: Backlog → To Do → In Progress → Review → Done. Preview de tareas antes de exportar |
| 32  | Editor de resultados   | Astro + React       | Revisión/edición manual de tareas: editar título, descripción, etiquetas                     |
| 33  | Selector de modelo LLM | Astro + React       | Configuración visual (modelo, temperatura, max tokens)                                       |
| 34  | Toggle de tema         | Astro               | Claro / Oscuro / Auto con persistencia                                                       |
| 35  | Layout responsivo      | Astro               | Sidebar + header + contenido. Mobile-first                                                   |
| 36  | Login / Register       | Astro + React       | Login con Google/GitHub vía Auth.js. Registro abierto                        |

### 🛡️ Infraestructura (MVP)

| #   | Feature                 | Descripción                                       |
| --- | ----------------------- | ------------------------------------------------- |
| 37  | Arquitectura hexagonal  | Separación dominio / aplicación / infraestructura |
| 38  | Procesamiento asíncrono | Celery + Redis                                    |
| 39  | Logging estructurado    | Correlation IDs para trazabilidad                 |
| 40  | Dockerización           | Docker Compose para dev                           |
| 41  | Permisos y workspaces  | V2                                                |
| 42  | Rate limiting           | V2                                                |

---

## 8. Pipeline de extracción

### Flujo paso a paso

```
┌──────────────┐
│ User Story   │  "As a user, I want to log in so that I can access my account"
│ (texto raw)  │
└──────┬───────┘
       │
       ▼
┌──────────────────────────────────────┐
│ 1. PREPROCESAMIENTO                  │
│                                      │
│ • Limpieza de texto (espacios, utf8) │
│ • Validación de formato mínimo       │
│ • Extracción de actor / acción /     │
│   objetivo (parse básico)            │
│ • Normalización                      │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ 2. CONTEXTO HISTÓRICO (RAG)          │
│                                      │
│ • Generar embedding de la user story │
│ • Buscar extracciones similares en   │
│   Qdrant (similitud > 0.85)          │
│ • Incluir ejemplos en el prompt      │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ 3. EXTRACCIÓN LLM                    │
│                                      │
│ • Construir prompt compuesto:        │
│   System: "You are an expert..."     │
│   + Instruction: task_generation.j2  │
│   + Few-shot: ejemplos del contexto  │
│ • Enviar al modelo (Ollama)          │
│ • Retry: 3 (backoff exp. 2^n)        │
│ • Sin timeout explícito              │
│ • Si falla → None, sigue con la      │
│   siguiente fila del batch           │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ 4. POST-PROCESAMIENTO                │
│                                      │
│ • Parsear formato texto plano:       │
│   "N. summary: ..." / "description:" │
│ • Dividir tareas concatenadas en     │
│   filas individuales (ExplodeTasks)  │
│ • Aplicar regex de parsing con       │
│   fallbacks para variantes de formato│
│ • Limpiar marcadores, preamble,      │
│   bold markdown alrededor de labels  │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ 5. PERSISTIR                          │
│                                      │
│ • Guardar en base de datos           │
│ • Almacenar embedding + resultado    │
│   en Qdrant para contexto futuro     │
└──────────────┬───────────────────────┘
               │
               ▼
┌──────────────────────────────────────┐
│ 6. RESPUESTA                          │
│                                      │
│ • Devolver tareas en JSON            │
│ • Incluir: confidence score,         │
│   modelo usado, tiempo de proceso    │
└──────────────────────────────────────┘
```

### Configuración de prompts (de la tesis)

Los prompts siguientes están basados en los que se probaron y validaron con el dataset Salony en LocalLLM-DataForge. Están en inglés porque los modelos LLM responden mejor en ese idioma para tareas técnicas de descomposición.

**System prompt:**

> "You are an expert software development lead who excels at breaking down user stories into clear, actionable development tasks."

**Instruction prompt (template `task_generation.j2`):**

> Break this user story into smaller development tasks to help the developers implement it efficiently. You can divide this user story into as many tasks as needed, depending on its complexity. Each task must be unique, actionable, and non-overlapping.
>
> Use EXACTLY this format — each numbered task starts on its own line with `N. summary:` followed by the summary text, then a new line with `description:` and the description text:
>
> 1. summary: Set up database schema for transactions
> description: Create the necessary database tables and indexes to store transaction history records with fields for date, amount, type, and notes.
>
> 2. summary: Implement transaction listing API endpoint
> description: Build a REST API endpoint that returns paginated transaction history for a given user, with support for date filtering and sorting.
>
> 3. summary: Build transaction history UI component
> description: Develop a user interface component that displays transaction history in a table format with sorting, pagination, and search functionality.
>
> Each numbered task MUST have `summary:` and `description:` on SEPARATE lines. Do NOT put summary and description on the same line. Do NOT use commas or other punctuation to separate summary from description.
>
> CRITICAL: Use ONLY plain text. Do NOT use markdown formatting like **bold**, *italics*, or backticks. Write `summary:` and `description:` as plain text without any surrounding markers.
>
> User story:
> {{user_story}}

**Formato de respuesta esperado:**

```
N. summary: <título de la tarea>
description: <descripción detallada>
```

**Parámetros del modelo (Ollama - LLaMA 3.2 / Mistral):**

- Temperature: 0.1 (baja creatividad, alta consistencia)
- Num predict (max tokens): 2048
- Sin top-p, frequency penalty, ni presence penalty (Ollama no requiere estos parámetros)

---

## 9. Modelo de lenguaje

### Evaluación de modelos — Pendiente ⏳

> **⚠️ Nota**: Esta es una evaluación planificada, no realizada aún. La tabla siguiente es un ejemplo ilustrativo del tipo de comparativa que se espera obtener. Los números de modelo y costos son referenciales. Esta sección se actualizará con datos reales tras la evaluación.

Se evaluarán 6 modelos con ~50 historias de usuario para determinar la mejor relación costo-beneficio.

Para el desarrollo de Storico, la estrategia es:

| Fase | Modelo principal                      | Propósito                                  |
| ---- | ------------------------------------- | ------------------------------------------ |
| MVP  | Ollama (LLaMA 3.2, Mistral)           | Desarrollo local, sin costos, sin API keys |
| V2   | OpenAI GPT-3.5-turbo + GPT-4 fallback | Producción, mayor precisión                |
| V3   | Multi-modelo seleccionable            | Flexibilidad para el usuario               |

### Interfaz del adaptador LLM (diseño propuesto)

```python
# Puerto (interfaz) en dominio — sin dependencias externas
class LLMPort(ABC):
    @abstractmethod
    def generate_tasks(self, user_story: str, config: LLMConfig) -> ExtractionResult:
        ...

# Implementación concreta en infraestructura
class OllamaAdapter(LLMPort):
    def generate_tasks(self, user_story: str, config: LLMConfig) -> ExtractionResult:
        # llama a API de Ollama
        ...

class OpenAIAdapter(LLMPort):
    def generate_tasks(self, user_story: str, config: LLMConfig) -> ExtractionResult:
        # llama a OpenAI API
        ...
```

---

## 10. Framework auxiliar: LocalLLM-DataForge

> **Nota importante**: Este framework fue una herramienta **separada** creada durante la investigación. No es parte del MVP de Storico pero los prompts, la arquitectura de validación y el pipeline de extracción que se validaron allí son la base técnica de Storico.

### Propósito

LocalLLM-DataForge es un **framework de pipelines de datos para procesamiento con LLMs locales** vía Ollama. Se creó ante la **falta de datasets públicos** con historias de usuario descompuestas en tareas (ground truth), pero evolucionó a una arquitectura genérica de pipelines reutilizables con steps conectables, sistema de caché, ejecución paralela y validación LLM-as-a-Judge.

### Arquitectura

```
User Stories (CSV)
    │
    ▼
┌────────────────────────┐
│ 1. LoadDataFrame       │ Carga el CSV de entrada
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ 2. ValidateUserStories │ Valida formato "As a(n)... I want... so that..."
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ 3. AddColumn (x3)      │ Agrega: us_id, generator_model_name, (opcional) judge_model_name
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ 4. OllamaLLMStep       │ Genera tareas vía Ollama (prompt template task_generation.j2)
│   (generación)         │ System prompt + instruction + few-shot
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ 5. ExplodeTasks        │ Divide tareas concatenadas en filas individuales
└────────┬───────────────┘
         │
         ▼
┌────────────────────────┐
│ 6. OllamaJudgeStep     │ LLM-as-a-Judge: evalúa coherencia, completitud,
│   (validación)         │ viabilidad, formato y granularidad (0-50)
└────────┬───────────────┘
         │
         ▼
    Dataset final (user story + tareas + metadata + score)
```

### Pipeline dual

Además del pipeline simple, existe un pipeline **dual** que ejecuta dos modelos generadores en paralelo y un `ComparisonJudgeStep` que compara ambos resultados y selecciona el mejor según calidad, devolviendo el ganador y la justificación.

### Framework de steps

El proyecto se organiza como un framework Python con steps conectables:

```
src/dataforge/
├── pipeline.py              ← DataForgePipeline (orquestador)
├── base_step.py             ← BaseStep (clase abstracta)
├── llm/
│   ├── ollama_step.py       ← Generación LLM básica
│   ├── ollama_judge_step.py ← Validación LLM-as-a-Judge
│   └── comparison_judge_step.py ← Comparación dual
├── transformers/
│   ├── load_dataframe.py    ← Carga de datos
│   ├── add_column.py        ← Columnas computadas
│   ├── keep_columns.py      ← Selección de columnas
│   ├── explode_tasks.py     ← División de tareas
│   └── json_repair.py       ← Reparación de JSON malformado
├── validators/
│   └── validate_user_stories.py  ← Validación de formato INVEST
├── use_cases/
│   └── salony/              ← Configuración específica del dataset Salony
└── utils/
    ├── cache.py             ← Sistema de caché por contenido
    ├── logging.py           ← Logging estructurado
    └── batching.py          ← Procesamiento por lotes
```

### Características clave

- **Steps conectables** con declaración de columnas de entrada/salida y validación automática de dependencias
- **Caché inteligente** por hash de contenido + configuración del step (`.cache/dataforge/`)
- **Batch processing** con ejecución paralela via `ThreadPoolExecutor` (configurable: `batch_size` + `num_workers`)
- **Reintentos** con backoff exponencial ante errores de conexión o API
- **JSON Repair** para manejar respuestas malformadas del LLM
- **Pipeline dual** para comparación de modelos lado a lado

### Dataset utilizado

El dataset principal es **Salony** — user stories del sector de salones de belleza — usado para entrenar y validar el pipeline de extracción. El formato de entrada es CSV con una columna `input` que contiene historias de usuario en formato INVEST.

### Resultados reportados

- ~500 historias de usuario procesadas (Salony)
- Tasa de éxito promedio: **~94%**
- Pipeline dual permite comparar resultados entre modelos (ej. LLaMA 3.2 vs Mistral)
- Judge evalúa en escala 0-50 con umbral de aprobación configurable (~35 pts)

### Relación con Storico

- Los **prompts** (system + instruction + few-shot) validados en DataForge son los que usa Storico
- El patrón **LLM-as-a-Judge** para validación automática se incorpora al motor de extracción de Storico
- El dataset Salony servirá como base para la **evaluación experimental** de Storico (juicio de expertos)
- La arquitectura de **steps y pipeline** no se traslada — Storico usa hexagonal, no pipeline de datos

---

## 11. Evaluación experimental

### Método

- **Juicio de expertos**: 6 expertos (Scrum Masters certificados + Product Owners con 3+ años de experiencia)
- **Comparativa**: Manual (personas) vs Automático (Storico)
- **Métricas**: Precisión, claridad, velocidad, satisfacción del usuario

### KPIs definidos en la tesis

| Métrica                                    | Descripción                                                 |
| ------------------------------------------ | ----------------------------------------------------------- |
| **TCR** (Task Coverage Rate)               | Cuántos requisitos relevantes son representados como tareas |
| **TAS** (Technical Accuracy Score)         | Puntuación experta sobre validez técnica de las tareas      |
| **IFI** (Implementation Feasibility Index) | Factibilidad práctica: claridad, complejidad, dependencias  |

### Resultados esperados (hipótesis)

- Reducción del tiempo de planificación
- Mejora en la comprensión de las tareas por parte del equipo
- Mayor consistencia en la descomposición entre diferentes proyectos

---

## 12. Estructura del frontend

### Árbol de directorios propuesto

```
storico/
├── src/
│   ├── layouts/
│   │   ├── MainLayout.astro          ← Shell: sidebar + header + slot con View Transitions
│   │   └── AuthLayout.astro          ← Layout para login/register
│   │
│   ├── pages/
│   │   ├── index.astro               ← Landing page (puro Astro, poco JS)
│   │   ├── login.astro               ← Login page (puro Astro, sin React)
│   │   ├── dashboard.astro           ← Dashboard de proyectos (isla React)
│   │   ├── stories.astro             ← Listado de user stories (isla React)
│   │   ├── stories/[id].astro        ← Detalle de story + tareas (isla React)
│   │   ├── kanban.astro              ← Kanban board (isla React)
│   │   ├── export.astro              ← Configuración de exportación (isla React)
│   │   └── settings.astro            ← Configuración general + LLM (isla React)
│   │
│   ├── components/                   ← Componentes compartidos
│   │   ├── astro/                    ← Componentes Astro (poco o ningún estado)
│   │   │   ├── ThemeToggle.astro
│   │   │   ├── Header.astro
│   │   │   └── Sidebar.astro
│   │   │
│   │   ├── react/                    ← Islas React (interactividad)
│   │   │   ├── ui/                   ← shadcn components (button, card, dialog, etc.)
│   │   │   ├── Dashboard.tsx
│   │   │   ├── StoryList.tsx
│   │   │   ├── StoryDetail.tsx
│   │   │   ├── KanbanBoard.tsx
│   │   │   ├── StoryForm.tsx
│   │   │   ├── TaskEditor.tsx
│   │   │   ├── TaskCard.tsx
│   │   │   ├── ModelSelector.tsx
│   │   │   └── ExportPanel.tsx
│   │   │
│   │   └── layouts/                  ← Componentes de layout reutilizables
│   │       ├── SidebarNav.tsx
│   │       └── Breadcrumbs.tsx
│   │
│   ├── stores/                       ← Zustand stores (compartidos entre islas)
│   │   ├── projectStore.ts
│   │   ├── taskStore.ts
│   │   └── uiStore.ts               ← Theme, sidebar state, etc.
│   │
│   ├── lib/                          ← Utilidades y API calls
│   │   ├── api.ts                    ← Cliente HTTP con fetch, abstraído para poder migrar a Axios
│   │   └── utils.ts                  ← Funciones auxiliares (cn(), etc.)
│   │
│   ├── types/                        ← Tipos TypeScript compartidos
│   │   ├── project.ts
│   │   ├── story.ts
│   │   └── task.ts
│   │
│   └── styles/
│       └── globals.css               ← Tailwind 4 + variables de tema shadcn
│
├── astro.config.mjs
├── tailwind.config.ts
├── tsconfig.json
└── package.json
```

### Stack frontend detallado

| Componente      | Tecnología                   | Propósito                                                |
| --------------- | ---------------------------- | -------------------------------------------------------- |
| Framework base  | **Astro**                    | Layout, routing, pages, View Transitions. React solo en islas |
| Islas React     | **React**                    | Componentes interactivos donde se necesita estado (formularios, kanban, editores) |
| Estado global   | **Zustand**                  | Stores ligeros y tipados para proyectos, tareas, UI      |
| UI primitives   | **shadcn**                   | Button, Card, Dialog, Form, Select, Tabs, Table, etc.    |
| Estilos         | **Tailwind CSS 4**           | Utility-first, diseño rápido y consistente               |
| Iconos          | **Lucide** (`lucide-react`)  | Iconos consistentes, tree-shakeable, SVG nativos         |
| Tema            | CSS variables + Tailwind     | Claro / Oscuro / Auto con `ThemeProvider`                |
| API client      | **fetch** nativo                  | Abstracción intercambiable para migrar a Axios si es necesario            |
| Internacionalización | **Astro i18n**                              | Español e inglés. Traducciones en archivos `en.json`/`es.json` |

### Mapa de rutas

| Ruta           | Componente      | Descripción                                          |
| -------------- | --------------- | ---------------------------------------------------- |
| `/`            | Dashboard.tsx   | Resumen de proyectos, métricas, actividad reciente   |
| `/stories`     | Stories.tsx     | Listado de user stories con búsqueda y filtros       |
| `/stories/:id` | StoryDetail.tsx | Detalle de story + tareas generadas + editor         |
| `/kanban`      | KanbanBoard.tsx | Vista Kanban de todas las tareas del proyecto activo |
| `/export`      | ExportPage.tsx  | Configurar exportación (formato, destino)            |
| `/settings`    | Settings.tsx    | Configuración de modelo LLM, preferencias de usuario |

Cada ruta es una página **Astro** (`.astro`) que puede incluir cero o más **islas React** para la interactividad que requiera. Las rutas con `:id` usan parámetros dinámicos de Astro.

### Principios de diseño UI

1. **Mobile-first** — responsive desde el inicio
2. **Accesible** — shadcn usa Radix UI que cumple WAI-ARIA
3. **Theme-aware** — todos los componentes soportan claro/oscuro

---

## 13. Preguntas abiertas

### 🟢 Futuras

| #   | Pregunta                            | Impacto                          |
| --- | ----------------------------------- | -------------------------------- |
| 1   | **Despliegue producción**           | Costos operativos y estrategia de hosting |
| 2   | **Licencia** del proyecto           | Distribución (MIT? GPL? Apache?) |
| 3   | **CI/CD**                           | Automatización                   |
| 4   | **Métricas de uso**                 | Dashboard de admin               |

---

## 14. Glosario

| Término                    | Definición                                                                                                                                           |
| -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| **User Story**             | Descripción breve de una funcionalidad desde la perspectiva del usuario. Formato: "As a(n) [role], I want [feature], so that [benefit]"                 |
| **Task**                   | Unidad de trabajo concreta, estimable y asignable. Desglose de una user story.                                                                       |
| **Kanban Board**           | Tablero visual con columnas que representan estados del flujo de trabajo (To Do → In Progress → Done)                                                |
| **LLM**                    | Large Language Model — modelo de lenguaje preentrenado                                                                                               |
| **LLM-as-a-Judge**         | Técnica donde un LLM evalúa la calidad de la salida de otro LLM o de sí mismo                                                                        |
| **Hexagonal Architecture** | Patrón que separa el dominio del negocio de los detalles de infraestructura mediante puertos (interfaces) y adaptadores (implementaciones)           |
| **Ports & Adapters**       | Sinónimo de arquitectura hexagonal                                                                                                                   |
| **Ollama**                 | Herramienta para ejecutar LLMs locales en hardware consumer                                                                                          |
| **FastAPI**                | Framework web Python con soporte async, tipado fuerte, OpenAPI automático                                                                            |
| **Astro**                  | Framework web para sitios con contenido estático e islas de interactividad                                                                           |
| **Few-shot learning**      | Técnica de prompting que incluye ejemplos en el prompt para guiar al modelo                                                                          |
| **Fine-tuning**            | Entrenamiento adicional de un modelo preentrenado en un dominio específico                                                                           |
| **Embedding**              | Representación vectorial de texto que captura significado semántico                                                                                  |
| **Astro i18n**             | Sistema de internacionalización nativo de Astro que maneja locale routing, detección de idioma y traducciones a nivel de página                      |
| **TCR**                    | Task Coverage Rate — métrica de cobertura de requisitos en tareas                                                                                    |
| **TAS**                    | Technical Accuracy Score — métrica de precisión técnica de tareas                                                                                    |
| **IFI**                    | Implementation Feasibility Index — métrica de factibilidad de implementación                                                                         |
| **INVEST**                 | Acrónimo para historias de usuario de calidad: Independent, Negotiable, Valuable, Estimable, Small, Testable                                         |
| **shadcn**                 | Colección de componentes React reutilizables construidos sobre Radix UI, estilizados con Tailwind. No es una dependencia npm — se copian al proyecto |
| **Zustand**                | Biblioteca liviana de manejo de estado para React. API simple basada en hooks, sin boilerplate                                                       |
| **Lucide**                 | Librería de iconos open-source en SVG. Tree-shakeable, compatible con React (`lucide-react`)                                                         |
| **Astro Islands**          | Patrón de arquitectura donde componentes interactivos (islas) se renderizan de forma aislada dentro de HTML estático                                 |
| **Astro View Transitions** | API de Astro para transiciones de página fluidas (like SPA) sin cargar JavaScript de framework completo                                             |
| **Auth.js**                | Biblioteca de autenticación para frameworks JS/TS. Soporta múltiples proveedores OAuth, sesiones JWT, y callbacks de autorización                    |
| **Qdrant**                 | Motor de búsqueda vectorial escrito en Rust. Almacena y consulta embeddings por similitud de coseno                                                  |

---

## 15. Referencias

### De la tesis

- Sommerville, I. (2016). _Software Engineering_ (10th ed.)
- Hevner, A. R. et al. (2004). _Design Science Research in Information Systems_
- Cohn, M. (2004). _User Stories Applied: For Agile Software Development_
- Wake, W. (2003). _INVEST in Good Stories, and SMART Tasks_
- Standish Group (2020). _CHAOS Report 2020_
- State of Agile (2021). _17th Annual State of Agile Report_

### Investigaciones relacionadas (de la tesis)

- Rentala (2023) — _User Story Toolkit_: clasificación y generación UML desde user stories
- Seitlheko (2021) — _SAPMT_: descomposición de épicas con NLP + algoritmo húngaro
- Wijaya (2025) — _MDL-LLaMA_: fine-tuning de LLaMA-2 para descomposición contextual
- AutoScrum (2023) — planificación ágil automatizada con GPT-3.5
- Sanwal (2024) — sistema multi-agente para ciclo ágil completo con LLMs
- Kumari (2023) — integración de IA en tableros Kanban con NLP y analítica predictiva

### Stack técnico

- **FastAPI**: <https://fastapi.tiangolo.com/>
- **Astro**: <https://astro.build/>
- **React**: <https://react.dev/>
- **Auth.js**: <https://authjs.dev/>

- **Tailwind CSS 4**: <https://tailwindcss.com/>
- **shadcn**: <https://ui.shadcn.com/>
- **Lucide**: <https://lucide.dev/>
- **Zustand**: <https://zustand.docs.pmnd.rs/>
- **Ollama**: <https://ollama.ai/>
- **Celery**: <https://docs.celeryq.dev/>
- **Redis**: <https://redis.io/>
- **PostgreSQL**: <https://www.postgresql.org/>
- **Qdrant**: <https://qdrant.tech/>
- **Docker**: <https://www.docker.com/>

---

> **Documento generado el 2026-06-30 como parte de la fase de definición de Storico.**
> Para preguntas o actualizaciones, contactar al autor de la tesis.
