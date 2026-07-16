# Frontend State Management

> Modelo de estado global con Zustand 5.
> Última actualización: 2026-07-15

## Stores

### authStore

Estado de autenticación del usuario actual.

```typescript
interface AuthState {
  user: AuthUser | null;        // { id, email, name, avatar_url?, authProvider? }
  loading: boolean;             // default: true
  isFirstLogin: boolean;        // default: false
  workspaceName: string;        // default: ''
}

// Acciones
setUser(user)                   // Setear usuario logueado
setIsFirstLogin(value)          // Marcar/desmarcar primer login
setWorkspaceName(name)          // Nombre del workspace actual
setOnboardingDone()             // Completar onboarding (setea isFirstLogin=false)
setLoading(value)               // Controlar loading state
clear()                         // Resetear estado (logout)
```

### workspaceStore

Gestión de workspaces. Persiste `currentWorkspace` en localStorage.

```typescript
interface WorkspaceState {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  loading: boolean;
  saving: boolean;
  error: string | null;
}

// Acciones
fetchWorkspaces()               // GET /api/v1/workspaces
setCurrentWorkspace(workspace)  // Seleccionar workspace activo
createWorkspace(params)         // POST /api/v1/workspaces
updateWorkspace(id, params)     // PUT /api/v1/workspaces/{id}
deleteWorkspace(id)             // DELETE /api/v1/workspaces/{id}
getById(id)                     // Búsqueda local por ID
```

**Persistencia**: `currentWorkspace` en localStorage (key: `workspace-storage`).
**Auto-select**: Si no hay workspace seleccionado, selecciona el primero de la lista.

### projectStore

Proyectos del workspace activo.

```typescript
interface ProjectState {
  projects: Project[];
  loading: boolean;
  saving: boolean;
  error: string | null;
}

// Acciones
fetchProjects()                 // GET /api/v1/workspaces/{wsId}/projects
createProject(params)           // POST /api/v1/workspaces/{wsId}/projects
updateProject(id, params)       // PUT /api/v1/workspaces/{wsId}/projects/{id}
deleteProject(id)               // DELETE /api/v1/workspaces/{wsId}/projects/{id}
getById(id)                     // Búsqueda local
```

Lee `currentWorkspace` de `workspaceStore` para scoping.

### storyStore

User stories del proyecto activo.

```typescript
interface StoryState {
  stories: UserStory[];
  loading: boolean;
  saving: boolean;
  error: string | null;
}

// Acciones
fetchStories(projectId?, workspaceId?)
fetchStory(id)
createStory(params)
updateStory(id, params)
deleteStory(id)
getById(id)
```

### taskStore

Tareas agrupadas por story.

```typescript
interface TaskState {
  tasks: Record<string, Task[]>;   // keyed by storyId
  loading: boolean;
  extracting: boolean;
  error: string | null;
}

// Acciones
fetchTasks(storyId)
extractTasks(storyId)
setTasks(storyId, tasks)
updateTask(taskId, updates)
```

### settingsStore

Configuración del workspace (LLM, exportación).

```typescript
interface SettingsState {
  settings: AppSettings;         // { llm: LLMConfig, export: ExportConfig }
  apiLoaded: boolean;
  apiSaving: boolean;
  lastSaveResult: SaveResult;   // 'idle' | 'success' | 'error'
}

// Acciones
loadFromApi()                   // GET /api/v1/users/me/settings
syncToApi(toastLabels?)         // PUT /api/v1/users/me/settings
setLLMProvider(provider)
setOllamaConfig(config)
setOpenAIConfig(config)
setAnthropicConfig(config)
setExportFormat(format)
resetSettings()
```

**Persistencia parcial**: Solo `settings.export` en localStorage (key: `storico-settings-v2`).
**No persiste**: API keys en localStorage.
**Deep-merge**: Merge personalizado para hidratación.

### uiStore

Estado de UI global.

```typescript
interface UIState {
  theme: Theme;                  // 'light' | 'dark' | 'system'
  sidebarOpen: boolean;          // default: true
}

// Acciones
setTheme(theme)
toggleTheme()
setSidebarOpen(open)
toggleSidebar()
```

Lee tema de localStorage en init. Aplica `applyTheme()` en browser.

## Reglas de Estado

1. **Un store por dominio** — proyectos, tareas, UI, auth, settings. No un store monolítico.
2. **Estado local de React** para datos que no cruzan islas — no todo va a Zustand.
3. **Persistencia mínima** — solo `currentWorkspace`, `theme`, y `settings.export` persisten.
4. **API keys nunca en localStorage** — solo en memoria o backend.
5. **Los stores leen de `workspaceStore`** para scoping — no duplican el workspace activo.

## API Client

Todas las llamadas API pasan por `ApiClient` (`src/lib/api.ts`).

```typescript
class ApiClient {
  constructor(baseUrl: string)    // baseUrl = '' (proxy vía Astro)
  async get<T>(path): Promise<T>
  async post<T>(path, body?): Promise<T>
  async put<T>(path, body?): Promise<T>
  async delete<T>(path): Promise<T>
  async patch<T>(path, body?): Promise<T>
}
```

Módulos de dominio:

| Módulo | Funciones |
|--------|-----------|
| `projects-api.ts` | CRUD de proyectos scoped a workspace |
| `stories-api.ts` | CRUD de user stories |
| `tasks-api.ts` | Listar tareas, extraer |
| `workspace-api.ts` | CRUD de workspaces + miembros |
| `user-api.ts` | Perfil, onboarding |
| `settings-api.ts` | Configuración + test LLM |
| `llm-config-api.ts` | Config LLM del workspace |
| `prompts-api.ts` | Prompts del workspace |

Todos los módulos convierten keys entre camelCase (frontend) y snake_case (API).
