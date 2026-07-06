# Design Brief: Storico — Frontend

> **Compilado el:** 2026-07-06
> **Basado en:** Historia de decisiones de diseño, SDD artifacts, y código producido en sesiones anteriores.
> **Propósito:** Documento vivo del frontend de Storico — decisiones de UI/UX, pantallas, arquitectura de componentes, estado, routing, y roadmap.
> **Scope:** Exclusivamente el frontend (`frontend/`). El backend vive en su propio contexto.

---

## Producto en una línea

> Pegá una user story en lenguaje natural, obtené tareas técnicas estructuradas en un tablero Kanban, editá y exportá a tu herramienta de gestión.

---

## 1. Visión General del Frontend

- **Alcance del MVP:** Un solo workspace, un usuario administrador (sin multi-tenant, sin equipos). Autenticación con Google/GitHub vía Auth.js. User stories en inglés con formato INVEST. Extracción vía Ollama (LLM local). Exportación a JSON, Markdown y Trello.

- **Cómo encaja en Storico:** El frontend es la puerta de entrada del usuario. Consume la API REST de Storico (FastAPI) y presenta los resultados del motor de extracción LLM en un tablero Kanban interactivo. No tiene lógica de dominio — es puramente presentacional + orquestación de UI.

- **Stack:** Astro (routing, pages, layouts) + React (islas de interactividad) + Zustand (estado global) + Tailwind CSS 4 (estilos) + shadcn (componentes UI) + Lucide (iconos).

- **Objetivos Clave:**
  1. **UX fluida y cero fricción** — el usuario pega una user story y en segundos ve tareas en un Kanban. View Transitions para navegación tipo SPA sin el peso de una SPA.
  2. **Sin JavaScript innecesario** — Astro renderiza en el servidor; React solo where needed. Cada página envía solo el JS de sus islas.
  3. **Tema claro/oscuro + i18n (es/en)** — desde el día 1.

---

## 2. Pantallas

### 2.1 Dashboard / Inicio (`/dashboard`)

La pantalla por defecto después del login. Resumen del workspace con cards de proyectos y acción rápida para empezar una extracción.

**Header:**
- Logo + nombre de la app (Storico)
- Navegación: Dashboard (activo), Stories, Kanban, Export, Settings
- ThemeToggle (claro/oscuro)
- User menu (avatar, nombre, logout) — 🔲 pendiente de Auth

**Contenido:**
- Cards de proyectos: cada card muestra nombre, cantidad de stories, cantidad de tareas generadas, fecha del último cambio
- Botón primario "Nuevo proyecto" → abre modal/formulario inline
- Métricas rápidas: total de stories procesadas, total de tareas generadas, extracciones exitosas/fallidas

**Interacciones:**
- Clic en card de proyecto → navega a `/stories?projectId=X`
- Clic en "Nuevo proyecto" → modal con campo de nombre (y opcional: descripción)

**Estados:**
| Estado | Qué se muestra |
|--------|---------------|
| **Carga** | Cards skeleton (3-4 rectángulos grises animados) |
| **Vacío** | Ilustración amigable + "Creá tu primer proyecto. Los proyectos agrupan tus user stories y tareas." + botón "Nuevo proyecto" |
| **Error** | Toast/alert: "No pudimos cargar tus proyectos. Intentá de nuevo." + botón de reintentar |
| **Sin métricas** | Los contadores muestran 0 en lugar de ocultarse |

---

### 2.2 Listado de User Stories (`/stories`)

Tabla/lista de todas las user stories del proyecto activo, más una acción para crear una nueva y extraer tareas.

**Header (de página):**
- Título: "User Stories" + nombre del proyecto activo
- Botón primario "Nueva story"
- Filtros: por estado (pendiente, procesando, completada, fallida), búsqueda por texto
- Selector de proyecto (si hay múltiples)

**Columnas de la tabla:**
| Columna | Comportamiento |
|---------|---------------|
| Título / Story | Texto truncado de la user story. Tooltip con el texto completo al hover. |
| Estado | Badge con color: Pendiente (gris), Procesando (azul), Completada (verde), Fallida (rojo) |
| Tareas generadas | Número (ej. "5 tareas") |
| Modelo usado | Nombre del LLM (ej. "LLaMA 3.2") |
| Fecha | Fecha de creación |
| Acción | Botón "Ver detalle" / menú contextual (⋮) con: Ver detalle, Re-procesar, Eliminar |

**Interacciones:**
- Clic en fila → navega a `/stories/[id]`
- Clic en botón "Nueva story" → navega a `/stories/new` o abre modal de creación
- Clic en "Re-procesar" → re-envía la story al LLM, actualiza tareas

**Estados:**
| Estado | Qué se muestra |
|--------|---------------|
| **Carga** | Filas skeleton (5-6 filas con texto animado) |
| **Vacío** | Ilustración + "Todavía no hay user stories. Creá una para empezar a extraer tareas." + botón "Nueva story" |
| **Error al listar** | Toast/alert con mensaje de error + botón reintentar |
| **Error al eliminar** | Toast con "No pudimos eliminar la story. Intentá de nuevo." |
| **Proyecto sin seleccionar** | Mensaje: "Seleccioná un proyecto del dashboard para ver sus stories" |

---

### 2.3 Crear / Editar User Story (`/stories/new` o modal inline)

Formulario para ingresar una nueva user story y disparar la extracción de tareas.

**Estructura del formulario:**
- **Proyecto**: Selector de proyecto (autocompletado, filtrable)
- **User story**: Textarea grande (3-4 líneas) con placeholder:
  ```
  "As a(n) [role], I want [feature], so that [benefit]"
  ```
- **Validación en vivo**: Indicador visual del formato INVEST
  - ✅ Tiene "As a(n)" → check verde
  - ✅ Tiene "I want" → check verde
  - ✅ Tiene "so that" → check verde
  - ❌ Formato incorrecto → texto de ayuda: "Las user stories deben seguir el formato: As a(n) [role], I want [feature], so that [benefit]"
- **Modelo LLM**: Selector (Ollama LLaMA 3.2, Mistral; futuro: GPT-4, Claude)
- **Botón**: "Extraer tareas" (primario, deshabilitado si el formato es inválido)

**Flujo post-extracción:**
1. Botón cambia a "Extrayendo..." con spinner
2. Barra de progreso indeterminada (o paso a paso: "Pre-procesando... → Consultando LLM... → Analizando resultado...")
3. Al completar → redirige a `/stories/[id]` con las tareas recién generadas
4. Si falla → mensaje de error con opción de reintentar con otro modelo o ajustar la story

**Estados:**
| Estado | Qué se muestra |
|--------|---------------|
| **Carga inicial** | Formulario vacío con skeleton |
| **Validación en vivo** | Checks/errores aparecen mientras el usuario escribe |
| **Envío / Procesando** | Spinner + "Extrayendo tareas..." + barra de pasos |
| **Éxito** | Redirect a `/stories/[id]` con toast "Tareas extraídas exitosamente" |
| **Error de extracción** | Mensaje: "No pudimos extraer tareas de esta story. {razón}. ¿Querés intentar con otro modelo o ajustar la story?" + botones "Reintentar" y "Editar story" |
| **Error de validación** | El botón "Extraer tareas" deshabilitado + campos inválidos marcados en rojo |
| **Error de red** | Toast: "Error de conexión. Verificá que el servidor esté corriendo." |

---

### 2.4 Detalle de Story + Tareas (`/stories/[id]`)

Vista principal de resultados: la user story original y las tareas que generó el LLM, con capacidad de editar y re-procesar.

**Encabezado:**
- User story completa (texto en bloque, copiable)
- Badge de estado (Completada / Fallida / Procesando)
- Modelo usado + temperatura + tiempo de procesamiento
- Botones de acción:
  - "Re-procesar" (vuelve a enviar al LLM)
  - "Exportar" (abre panel de exportación)
  - "Abrir en Kanban" (navega a `/kanban?storyId=X`)

**Listado de tareas:**
Cada tarea se muestra como una card expandible:

```
┌────────────────────────────────────────────────┐
│  [checkbox]  1. Set up database schema...      │
│              frontend • backend • alta         │
│              Depende de: —                      │
│              ▼ descripción                     │
│              "Crear tablas para..."             │
│              [✏️ Editar] [🗑️ Eliminar]         │
└────────────────────────────────────────────────┘
```

- Checkbox para marcar como completada
- Número de tarea (jerarquía: 1, 2, 3...)
- Título (summary) — editable inline
- Etiquetas técnicas como badges de colores:
  - `frontend` → azul
  - `backend` → verde
  - `api` → naranja
  - `testing` → rosa
  - `db` → violeta
  - `ui/ux` → celeste
  - `devops` → gris
- Prioridad: alta / media / baja (con color)
- Dependencias: lista de tareas predecesoras (links)

**Editor de tareas (TaskEditor):**
- Al hacer clic en ✏️ → la card se expande en modo edición
- Campos editables: título, descripción (textarea), etiquetas (multi-select con badges), prioridad (select), dependencias (selector de otras tareas)
- Botones: "Guardar cambios" / "Cancelar"
- Sin confirmación al salir (auto-save cada 30s opcional — diferido a V2)

**Estado vacío de analíticas (sin tareas):**
- "El LLM no generó tareas para esta story. {razón posible}"
- Botones: "Re-procesar con otro modelo" / "Editar story" / "Descartar"

**Estados:**
| Estado | Qué se muestra |
|--------|---------------|
| **Carga** | Skeleton de story + 3-4 skeletons de task cards |
| **Procesando** | Story visible + "Extrayendo tareas..." con spinner + resultado parcial si llegó |
| **Completada con tareas** | Story + listado de task cards |
| **Completada sin tareas** | Story + estado vacío con sugerencias |
| **Fallida** | Story + mensaje de error + botones para reintentar |
| **Editando tarea** | Task card expandida en modo edición |

---

### 2.5 Kanban Board (`/kanban`)

Tablero visual con columnas que representan estados del flujo de trabajo. Preview de tareas antes de exportar.

**Encabezado:**
- Título: "Kanban Board" + nombre del proyecto
- Selector de proyecto/story (para filtrar qué tareas se muestran)
- Botón "Exportar" (abre ExportPanel)
- Contador: "X tareas en total"

**Columnas:**
```
┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐
│ Backlog  │  │ To Do    │  │ In Prog… │  │ Review   │  │ Done     │
│          │  │          │  │          │  │          │  │          │
│ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │  │ ┌──────┐ │
│ │Task  │ │  │ │Task  │ │  │ │Task  │ │  │ │Task  │ │  │ │Task  │ │
│ │card  │ │  │ │card  │ │  │ │card  │ │  │ │card  │ │  │ │card  │ │
│ └──────┘ │  │ └──────┘ │  │ └──────┘ │  │ └──────┘ │  │ └──────┘ │
│          │  │          │  │          │  │          │  │          │
│ + X más  │  │ + X más  │  │ + X más  │  │ + X más  │  │ + X más  │
└──────────┘  └──────────┘  └──────────┘  └──────────┘  └──────────┘
```

**Task card dentro del Kanban:**
```
┌──────────────────────┐
│ Implementar login    │
│ backend • api • alta │
│ Story: ST-001        │
└──────────────────────┘
```
- Título (truncado a 2 líneas)
- Etiquetas técnicas en badges pequeños
- Story de origen (link)
- Arrastrable con drag handle (⣿)

**Interacciones:**
- **Drag & drop** entre columnas → cambia estado de la tarea → `PUT /api/v1/tasks/{id}`
- **Clic en card** → abre modal con detalle completo (reutiliza TaskCard expandida)
- **Scroll horizontal** si hay muchas columnas (overflow-x auto)
- **Columna vacía**: línea punteada con texto "Arrastrá tareas acá"

**Estados:**
| Estado | Qué se muestra |
|--------|---------------|
| **Carga** | Esqueleto de columnas con cards skeleton |
| **Vacío (sin tareas)** | "No hay tareas en este proyecto. Extraé tareas desde Stories para verlas acá." + botón "Ir a Stories" |
| **Columna sin tareas** | Línea punteada + "Arrastrá tareas acá" |
| **Error al mover tarea** | La card vuelve a su columna original + toast "No pudimos actualizar el estado. Intentá de nuevo." |
| **Error de carga** | Toast/alert + botón reintentar |

---

### 2.6 Panel de Exportación (`/export`)

Configuración y preview de la exportación de tareas a diferentes formatos y destinos.

**Selectores:**
- **Story / Proyecto**: qué incluir en la exportación (story actual, proyecto completo)
- **Formato**: JSON, Markdown (MVP). CSV, XML (V2+).
- **Destino**: Trello (MVP), Jira, GitHub Projects (V2+)

**Preview:**
- Área de preview con el output en tiempo real (texto renderizado)
- Para Trello: muestra preview del board que se creará

**Botón de acción:**
- "Exportar" → descarga el archivo (formato local) o abre OAuth flow (Trello)

**Estados:**
| Estado | Qué se muestra |
|--------|---------------|
| **Carga** | Skeleton del panel |
| **Sin datos** | "No hay tareas para exportar. Primero extraé tareas de una user story." |
| **Preview generado** | Área de texto con el output formateado |
| **Error al exportar** | Toast con mensaje específico (ej. "No pudimos conectar con Trello. Verificá tu autenticación.") |
| **Exportación exitosa** | Toast + opción "Abrir en Trello" (si aplica) |

---

### 2.7 Configuración (`/settings`)

Preferencias del workspace: modelo LLM, prompts del sistema, tema, idioma.

**Secciones:**
- **Modelo LLM**:
  - Selector: Ollama (local) / OpenAI / Anthropic (futuro)
  - Parámetros: temperatura (slider 0-1, default 0.1), max tokens (input numérico, default 2048)
  - Botón "Test de conexión" → llama al modelo con un prompt de prueba
  - Estado de conexión: ✅ Conectado / ❌ No disponible (con razón)
- **Prompts del sistema** (🔲 V2, solo admin):
  - Textarea con el system prompt actual
  - Botón "Restaurar default"
- **Tema**: Claro / Oscuro / Auto
- **Idioma**: Español / Inglés (persistencia en localStorage, override de preferencia del navegador)

**Estados:**
| Estado | Qué se muestra |
|--------|---------------|
| **Carga** | Skeleton del formulario |
| **Test de conexión exitoso** | Badge verde: "Modelo X conectado en Yms" |
| **Test de conexión fallido** | Badge rojo: "No pudimos conectar. Verificá que Ollama esté corriendo." + posibles causas |
| **Guardado exitoso** | Toast: "Configuración guardada" |
| **Error al guardar** | Toast con mensaje de error |

---

### 2.8 Login (`/login`)

Pantalla pública de autenticación. Sin islas React (puro HTML estático).

**Contenido:**
- Logo + nombre de la app
- "Iniciá sesión en Storico"
- Botón "Continuar con Google" (🔲 pendiente)
- Botón "Continuar con GitHub" (🔲 pendiente)
- Footer: "Al iniciar sesión, aceptás nuestros Términos y Política de Privacidad"

**Estados:**
| Estado | Qué se muestra |
|--------|---------------|
| **Default** | Botones de OAuth + branding |
| **Carga** | Botón deshabilitado con spinner + "Redirigiendo..." |
| **Error** | Toast: "No pudimos autenticarte. Intentá de nuevo." |

---

### 2.9 Landing Page (`/`)

Página pública (sin autenticación) que presenta Storico.

**Contenido:**
- Hero: "De user stories a tareas en segundos" + subtítulo explicativo
- Demo visual: screenshot animado o ilustración del flujo
- Call to action: "Comenzá gratis" → `/login`
- Features: 3 cards con íconos (Extracción automática, Kanban visual, Exportación a Trello)
- Footer: links a Términos, Privacidad, contacto

**Estados:**
| Estado | Qué se muestra |
|--------|---------------|
| **Default** | Página completa con hero, features, CTA |

---

## 3. Decisiones de Arquitectura y Patrones

### Patrón Arquitectónico

**Astro Islands + Container-Presentational.** Astro es el orquestador (routing, layouts, páginas estáticas). Los componentes React son islas de interactividad que se hidratan individualmente. No hay SPA — cada página es HTML renderizado en servidor con transiciones client-side suaves (View Transitions).

```
Browser Request
      │
      ▼
┌──────────────────────────────────────────┐
│              Astro Server                │
│  (renderiza HTML, detecta locale,        │
│   aplica layout, inyecta CSS)            │
└──────────┬───────────────────────────────┘
           │
           ▼
┌──────────────────────────────────────────┐
│         Página .astro (HTML)            │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  Isla React #1 (Dashboard.tsx)     │  │
│  │  → se hidrata en el cliente        │  │
│  │  → usa Zustand + fetch API         │  │
│  └────────────────────────────────────┘  │
│                                          │
│  ┌────────────────────────────────────┐  │
│  │  Componente Astro (Header.astro)   │  │
│  │  → cero JS, solo HTML+CSS         │  │
│  └────────────────────────────────────┘  │
└──────────────────────────────────────────┘
```

### Reglas Cardinales del Frontend

| Regla | Explicación |
|-------|-------------|
| **Astro maneja routing, NO React Router** | Todas las rutas en `src/pages/`. View Transitions para navegación fluida. |
| **React solo en islas** | Nada de `<React.StrictMode>` envolviendo toda la app. Cada isla es independiente. |
| **Zustand para estado compartido entre islas** | Si dos islas necesitan el mismo estado (ej. proyecto activo), va a un store. Si no, estado local de React. |
| **API client abstraído** | `src/lib/api.ts` con fetch nativo. Si se necesita migrar a Axios, se cambia un archivo. |
| **Tipos compartidos** | `src/types/` refleja los schemas de la API backend. Single source of truth. |
| **Sin dependencias UI pesadas** | shadcn + Tailwind 4. No Material UI, no Ant Design. |

### Estructura de Carpetas

```text
frontend/src/
├── layouts/                        # Astro layouts
│   ├── MainLayout.astro            # Shell: sidebar + header + slot (View Transitions)
│   └── AuthLayout.astro            # Layout minimalista para login/register
│
├── pages/                          # Astro Routing (cada archivo = una ruta)
│   ├── index.astro                 # Landing page (poco JS, puro HTML)
│   ├── login.astro                 # Login page (estático)
│   └── dashboard.astro             # Dashboard (isla React)
│
├── components/
│   ├── astro/                      # Componentes sin estado (cero JS en cliente)
│   │   ├── Header.astro
│   │   └── Sidebar.astro
│   │
│   └── react/                      # Islas React (interactividad estado/comportamiento)
│       ├── ui/                     # shadcn primitives (button, card, dialog, select, etc.)
│       ├── Dashboard.tsx
│       ├── ThemeToggle.tsx
│       ├── StoryList.tsx           # 🚧 Pendiente
│       ├── StoryDetail.tsx         # 🚧 Pendiente
│       ├── KanbanBoard.tsx         # 🚧 Pendiente
│       ├── StoryForm.tsx           # 🚧 Pendiente
│       ├── TaskEditor.tsx          # 🚧 Pendiente
│       ├── TaskCard.tsx            # 🚧 Pendiente
│       ├── ModelSelector.tsx       # 🚧 Pendiente
│       └── ExportPanel.tsx         # 🚧 Pendiente
│
├── stores/                         # Zustand — estado global entre islas
│   ├── projectStore.ts             # Proyecto activo, lista de proyectos
│   ├── taskStore.ts                # Tareas del proyecto activo
│   └── uiStore.ts                  # Sidebar collapsed, tema, estado global UI
│
├── lib/                            # Utilidades
│   ├── api.ts                      # Cliente HTTP (fetch abstraído)
│   └── utils.ts                    # cn() y helpers
│
├── types/                          # Tipos compartidos (reflejan API backend)
│   ├── project.ts                  # Project, CreateProjectPayload
│   ├── story.ts                    # UserStory, CreateStoryPayload
│   └── task.ts                     # Task, ExtractionResult
│
├── i18n/                           # Traducciones
│   ├── en.json
│   └── es.json
│
└── styles/
    └── globals.css                 # Tailwind 4 + CSS variables de tema (shadcn)
```

### Mapa de Rutas

| Ruta | Página Astro | Isla React | Descripción |
|------|-------------|------------|-------------|
| `/` | `index.astro` | — | Landing page pública |
| `/login` | `login.astro` | — | Login OAuth (Google/GitHub) |
| `/dashboard` | `dashboard.astro` | `Dashboard.tsx` | Resumen de proyectos y métricas |
| `/stories` | (pendiente) | `StoryList.tsx` | Listado de user stories del proyecto |
| `/stories/new` | (pendiente) | `StoryForm.tsx` | Crear story + extraer tareas |
| `/stories/[id]` | (pendiente) | `StoryDetail.tsx` + `TaskEditor.tsx` | Detalle de story + tareas generadas |
| `/kanban` | (pendiente) | `KanbanBoard.tsx` | Tablero Kanban drag & drop |
| `/export` | (pendiente) | `ExportPanel.tsx` | Configuración de exportación |
| `/settings` | (pendiente) | `ModelSelector.tsx` | Configuración de modelo LLM, tema, idioma |

### Decisiones de Diseño (Frontend ADRs)

| ID | Decisión | Status |
|----|----------|--------|
| **ADR-001** | **Astro Routing + View Transitions + islas React** | ✅ Implementado |
| **ADR-003** | **Auth.js (OAuth) con Google + GitHub** | 🔲 Pendiente de implementar |
| **ADR-006** | **shadcn + Tailwind CSS 4 + Lucide** | ✅ Implementado |
| **ADR-007** | **Tema claro/oscuro con CSS variables + `ThemeToggle`** | ✅ Implementado |
| **ADR-008** | **Astro i18n. Español e inglés. User stories solo en inglés** | ✅ Implementado (archivos de traducción listos) |

### Principios de UI/UX

| Principio | Aplicación |
|-----------|------------|
| **Mobile-first responsive** | Sidebar colapsable, grid adaptativo, contenedores fluidos |
| **Accesibilidad WAI-ARIA** | shadcn usa Radix UI que cumple estándares de accesibilidad |
| **Theme-aware** | Todos los componentes soportan claro/oscuro vía CSS variables |
| **Feedback visual inmediato** | Skeleton loading, toasts para errores/éxito, optimistic updates |
| **Sin recarga completa** | View Transitions entre páginas; llamadas API con fetch asíncrono |
| **Consistencia visual** | shadcn + Lucide + Tailwind; sin estilos inline, sin componentes de terceros |

---

## 4. Registro de Investigación e Ideación

### Stack Tecnológico Detallado

| Tecnología | Versión | Rol en el Frontend |
|-----------|---------|-------------------|
| **Astro** | 5.7+ | Framework principal: routing, layouts, View Transitions, build |
| **React** | 19+ | Islas de interactividad (con React Compiler — sin useMemo/useCallback manual) |
| **Zustand** | 5+ | Estado global liviano entre islas React |
| **shadcn** | latest | Componentes UI sobre Radix (button, card, dialog, select, table, tabs, etc.) |
| **Tailwind CSS** | 4+ | Utility-first CSS (nueva engine, `@theme` directive, sin `tailwind.config.ts`) |
| **Lucide** | 0.510+ | Iconos SVG tree-shakeable |
| **Auth.js** | latest | Autenticación OAuth (Google, GitHub) |
| **TypeScript** | 5.8+ | Tipado estricto en toda la codebase |

### API Client Architecture

```
React Island (componente)
      │
      ▼
src/lib/api.ts  (abstracción única)
      │
      ▼
fetch() nativo  →  GET/POST/PUT/DELETE  →  Backend FastAPI
      │
      ▼
    Response JSON  →  Tipos en src/types/
```

- `api.ts` expone funciones por recurso: `getProjects()`, `createProject()`, `extractTasks()`, etc.
- Todas las llamadas pasan por una función `apiFetch()` con manejo de errores unificado.
- Los tokens de auth se inyectan via headers; el store de UI maneja loading/error states.
- La abstracción permite migrar a Axios cambiando un archivo (sin tocar componentes).

### Lo que Sabemos del Backend (Contrato API)

El frontend consume estos endpoints REST. Los schemas Pydantic se reflejan en `src/types/`:

| Recurso | Endpoints | Tipo en frontend |
|---------|-----------|------------------|
| **Health** | `GET /health` | `{ status: string }` |
| **Projects** | `GET/POST /api/v1/projects`, `GET/PUT/DELETE /api/v1/projects/{id}` | `Project`, `CreateProjectPayload` |
| **User Stories** | `GET/POST /api/v1/stories`, `GET/PUT/DELETE /api/v1/stories/{id}` | `UserStory`, `CreateStoryPayload` |
| **Tasks** | `GET/POST /api/v1/tasks`, `GET/PUT/DELETE /api/v1/tasks/{id}` | `Task` |
| **Extractions** | `POST /api/v1/extract`, `GET /api/v1/extractions`, `GET /api/v1/extractions/{id}` | `ExtractionResult` |
| **Users** | `GET /api/v1/users/me` | `User` (stub) |

### Riesgos Identificados (Frontend)

| Riesgo | Impacto | Mitigación |
|--------|---------|------------|
| **View Transitions + islas React** pueden tener flickering en transiciones complejas | 🟡 Medio | Testear en múltiples navegadores; considerar `transition:animate` de Astro |
| **Zustand compartido entre islas** — si las islas no están en la misma página, el store se reinicia | 🟡 Medio | Persistir estado crítico en localStorage (proyecto activo, tema) |
| **Auth.js + Astro** — la integración no es tan directa como en Next.js | 🟡 Medio | Usar middleware de Astro para proteger rutas; documentar la integración |
| **Tailwind 4 + shadcn** — shadcn espera Tailwind 3 por defecto | 🟢 Bajo | Configurar manualmente las CSS variables; ya resuelto en el bootstrap |
| **i18n en islas React** — las islas reciben locale como props | 🟢 Bajo | Ya definido: pasar `locale` desde la página Astro a cada isla |
| **Sin backend disponible en desarrollo** | 🔴 Alto | Desarrollar con mock data + `api.ts` intercambiable; Docker Compose levanta todo |
| **Drag & drop en Kanban** puede ser complejo con islas React | 🟡 Medio | Evaluar @dnd-kit (liviano, moderno) vs react-beautiful-dnd (mantenido pero legacy) |

---

## 5. Plan de Ejecución (Roadmap Frontend)

### ✅ Completado — Bootstrap

- [x] **Configuración del proyecto:**
  - [x] Astro + React + Tailwind 4 + Vite configurados
  - [x] shadcn CLI instalado, estructura `ui/` creada
  - [x] TypeScript strict mode + path aliases (`@/`)
  - [x] Lucide + Zustand + tailwind-merge + clsx como dependencias
  - [x] `globals.css` con variables de tema claro/oscuro

- [x] **Layouts y páginas base:**
  - [x] `MainLayout.astro` (sidebar + header + slot con View Transitions)
  - [x] `AuthLayout.astro` (layout minimalista)
  - [x] `index.astro` (landing page)
  - [x] `login.astro` (página de login, markup estático)
  - [x] `dashboard.astro` (integra isla Dashboard)

- [x] **Componentes base:**
  - [x] `Header.astro` (navegación + ThemeToggle)
  - [x] `Sidebar.astro` (navegación entre secciones)
  - [x] `Dashboard.tsx` (cards de proyectos, métricas)
  - [x] `ThemeToggle.tsx` (claro/oscuro/auto con persistencia)

- [x] **Estado y datos:**
  - [x] `projectStore.ts` (Zustand) — lista de proyectos, proyecto activo, CRUD
  - [x] `taskStore.ts` (Zustand) — tareas del proyecto activo
  - [x] `uiStore.ts` (Zustand) — sidebar collapsed, tema, loading states
  - [x] `api.ts` (cliente HTTP con fetch abstraído)

- [x] **Tipos compartidos:**
  - [x] `project.ts` — `Project`, `CreateProjectPayload`, `UpdateProjectPayload`
  - [x] `story.ts` — `UserStory`, `CreateStoryPayload`, `StoryStatus`
  - [x] `task.ts` — `Task`, `TaskStatus`, `ExtractionResult`

- [x] **Internacionalización:**
  - [x] `en.json` — todas las claves de UI en inglés
  - [x] `es.json` — todas las claves de UI en español
  - [x] Archivos de traducción listos para integrar con Astro i18n

### 🚧 Pendiente

- [ ] **Fase 1: User Stories (`/stories`, `/stories/new`, `/stories/[id]`)**
  - [ ] `StoryList.tsx` — tabla con búsqueda, filtros por estado, paginación, estados vacío/carga/error
  - [ ] `StoryForm.tsx` — formulario con validación en vivo del formato INVEST, selector de modelo LLM, barra de progreso de extracción
  - [ ] `StoryDetail.tsx` — story completa + listado de task cards con edición inline
  - [ ] `TaskEditor.tsx` — edición expandible de título, descripción, etiquetas (badges de colores), prioridad, dependencias
  - [ ] `TaskCard.tsx` — card reutilizable con checkbox, etiquetas, prioridad (para listado y Kanban)
  - [ ] Conexión con `GET/POST /api/v1/stories`, `POST /api/v1/extract`, `GET /api/v1/tasks`

- [ ] **Fase 2: Kanban Board (`/kanban`)**
  - [ ] `KanbanBoard.tsx` — 5 columnas (Backlog → To Do → In Progress → Review → Done)
  - [ ] Drag & drop entre columnas con @dnd-kit
  - [ ] Task cards dentro del Kanban (título, etiquetas, story origen)
  - [ ] Preview de tareas antes de exportar
  - [ ] Conexión con `PUT /api/v1/tasks/{id}` (cambio de estado)

- [ ] **Fase 3: Exportación y Settings (`/export`, `/settings`)**
  - [ ] `ExportPanel.tsx` — selector de formato (JSON, Markdown), preview en vivo, descarga
  - [ ] Conector Trello (vía backend)
  - [ ] `ModelSelector.tsx` — selector de modelo LLM, temperatura, max tokens, test de conexión
  - [ ] Settings de tema (claro/oscuro/auto) e idioma (es/en)

- [ ] **Fase 4: Autenticación y Testing**
  - [ ] Auth.js + Astro: login con Google OAuth, login con GitHub OAuth
  - [ ] Protección de rutas (middleware de Astro, redirect a `/login`)
  - [ ] User menu en Header (avatar, nombre, logout)
  - [ ] Testing de componentes (Vitest + Testing Library)
  - [ ] Testing de stores Zustand

---

## 6. Gatillos de Control (Triggers)

### Detenerse y Revisar cuando

| Situación | Acción |
|-----------|--------|
| **Se necesita un componente nuevo** | Primero verificar si shadcn ya lo provee (`npx shadcn add`). Si existe, no escribirlo a mano. |
| **Dos islas React necesitan el mismo estado** | Preguntar: ¿debería ir a un store de Zustand en lugar de pasarlo como prop? |
| **Un componente React tiene más de 300 líneas** | Dividir en subcomponentes. Si tiene lógica de negocio, está en el lugar equivocado. |
| **Se importa una librería JS pesada** | Preguntar: ¿realmente la necesito? ¿Puedo hacerlo con CSS puro + Astro? |
| **El build de Astro falla** | Verificar que las islas React no importen cosas del servidor (fs, path, etc.). |
| **View Transitions no funciona** | Verificar que los layouts tengan `transition:name` único y que no haya conflictos de CSS. |
| **Se agrega React Router** | ⛔ STOP. Astro maneja routing. Si necesitás navegación interna en una isla, probablemente necesitás un modal, no otra ruta. |
| **El store de Zustand crece sin control** | Revisar: un store por dominio (proyectos, tareas, UI). No un store monolítico. |
| **Un componente no maneja estados de carga/error/vacío** | Revisar la especificación de la pantalla — toda pantalla debe cubrir los 3 estados. |

### Criterios de Aceptación

| Criterio | Verificación |
|----------|--------------|
| **Build exitoso** | `npm run build` sin warnings ni errores |
| **Sin JS innecesario** | `astro build` debe mostrar 0 JS en páginas sin islas React |
| **View Transitions fluídas** | Navegar entre páginas sin recarga completa, sin flickering |
| **Tema claro/oscuro funcional** | Toggle cambia tema, se persiste en localStorage, respeta prefers-color-scheme |
| **i18n completo** | Todas las cadenas de UI están traducidas (es/en). No hay texto hardcodeado en los componentes. |
| **Responsive** | Sidebar colapsa en mobile, layout se adapta sin overflow horizontal |
| **API conectada** | Las islas React hacen fetch al backend y manejan loading/error states |
| **Estados cubiertos** | Cada pantalla tiene al menos: estado de carga, estado vacío, estado de error |
| **PR mergeable** | Commits con conventional commits, sin conflictos, build verde |

### Ritmo de Trabajo

1. **SDD Planning** → proposal → spec → design → tasks (para cada feature frontend)
2. **Implementación** → PRs pequeños (una página o un componente por PR)
3. **Verificación** → `npm run build`, probar en navegador, revisar View Transitions
4. **Próximo cambio recomendado:** Fase 1 — páginas de User Stories (`/stories`, `/stories/new`, `/stories/[id]`). El backend ya tiene los endpoints CRUD de stories y el stub de extracción. Arrancar por `StoryForm.tsx` + `StoryList.tsx`.

---

## Apéndice A: Árbol de Componentes (Estado Actual)

```text
layouts/
├── MainLayout.astro          # ✅ Header + Sidebar + slot (View Transitions)
└── AuthLayout.astro          # ✅ Layout minimalista

pages/
├── index.astro               # ✅ Landing page
├── login.astro               # ✅ Página login (markup HTML + formulario)
└── dashboard.astro           # ✅ Integra isla Dashboard

components/astro/
├── Header.astro              # ✅ Navegación + ThemeToggle
└── Sidebar.astro             # ✅ Navegación lateral

components/react/
├── Dashboard.tsx             # ✅ Cards de proyectos + métricas
├── ThemeToggle.tsx           # ✅ Toggle claro/oscuro
├── ui/                       # 🔲 shadcn components (pendientes de agregar)
│   ├── button.tsx
│   ├── card.tsx
│   ├── dialog.tsx
│   └── ...

stores/
├── projectStore.ts           # ✅ Proyecto activo, lista, CRUD
├── taskStore.ts              # ✅ Tareas del proyecto activo
└── uiStore.ts                # ✅ Sidebar, tema, loading states

lib/
├── api.ts                    # ✅ Cliente HTTP abstraído
└── utils.ts                  # ✅ cn(), helpers

types/
├── project.ts                # ✅ Project, Payloads
├── story.ts                  # ✅ UserStory, Payloads
└── task.ts                   # ✅ Task, ExtractionResult

i18n/
├── en.json                   # ✅ Traducciones inglés
└── es.json                   # ✅ Traducciones español

styles/
└── globals.css               # ✅ Tailwind 4 + variables tema
```

**Leyenda:** ✅ Completo | 🔲 Pendiente | 🔶 Parcial

## Apéndice B: Flujo de Datos (Frontend)

```
Usuario escribe user story en formulario
      │
      ▼
StoryForm.tsx (isla React)
      │
      ├─→ Valida formato "As a(n)... I want... so that..." (en vivo)
      │
      ▼
api.ts → fetch POST /api/v1/stories → Backend guarda
      │
      ▼
api.ts → fetch POST /api/v1/extract → Backend procesa con LLM
      │
      ▼
taskStore.ts ← setTasks(result.tasks)  ←←←  Response JSON
      │
      ├─→ StoryDetail.tsx renderiza story + task cards
      ├─→ KanbanBoard.tsx renderiza columnas (drag & drop)
      ├─→ TaskEditor.tsx permite editar tareas inline
      └─→ ExportPanel.tsx prepara formato de salida

Cambio de estado en Kanban (drag & drop)
      │
      ▼
taskStore.ts → updateTaskStatus(id, newStatus)
      │
      ▼
api.ts → fetch PUT /api/v1/tasks/{id} → Backend persiste
      │
      ▼
taskStore.ts ← actualiza estado local

Exportación
      │
      ▼
ExportPanel.tsx → api.ts → fetch POST /api/v1/export → Backend genera output
      │
      ▼
    Descarga archivo / Redirect a Trello OAuth
```

> **Documento generado el 2026-07-06. Exclusivo del frontend de Storico.**
> Para el contexto completo del proyecto (backend, tesis, pipeline LLM), ver `AGENTS.md` en la raíz del repositorio.
