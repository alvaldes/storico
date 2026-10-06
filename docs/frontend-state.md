# Frontend State Management

> Modelo de estado global con Zustand 5.
> Última actualización: 2026-09-23

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

Preferencias del usuario. Una sola: el formato de exportación por defecto.

```typescript
interface SettingsState {
  settings: AppSettings;         // { export: ExportConfig }
  apiLoaded: boolean;
  apiSaving: boolean;
  lastSaveResult: SaveResult;   // 'idle' | 'success' | 'error'
}

// Acciones
loadFromApi()                   // GET /api/v1/users/me/settings
syncToApi(toastLabels)          // PUT /api/v1/users/me/settings
setExportFormat(format)
resetSettings()
```

**Sin configuración de LLM por usuario**: este store ya no lleva un bloque `llm` —ni por lo
tanto ninguna API key— porque nada lo leía: la configuración de LLM es por **workspace**
(`workspace_llm_configs`, vía `LLMConfigEditor`). El backend removió el campo de su schema y
de lo guardado (revisión `0022`), y rechaza con `422` un `PUT` que traiga un bloque `llm`.

`syncToApi` recibe las etiquetas del toast **del llamador**: el store no tiene copy propia (sus
defaults eran strings en inglés sobre una configuración de LLM que ya no existe).
`AccountPage` es quien lo llama, al cambiar el formato de exportación.

**Persistencia parcial**: Solo `settings.export` en localStorage (key: `storico-settings-v2`).
**No persiste**: API keys en localStorage.
**Deep-merge**: Merge personalizado para hidratación.
**Clave legacy eliminada**: `storico-settings`, la clave previa a `v2`, guardaba `settings`
completo y con él un `apiKey` en claro por proveedor cloud. El módulo la borra al evaluarse
(`dropLegacySettingsKey`), de forma best-effort: sin `localStorage` (render en servidor) o con
un storage que rechaza la operación, la clave sobrevive y la app sigue igual.

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

### loadingStore

Contador de peticiones bloqueantes que alimenta el loader de página completa.

```typescript
interface LoadingState {
  pending: number;    // peticiones bloqueantes en vuelo
  visible: boolean;   // el overlay está pintado
}

// Funciones (no acciones del store):
beginBlockingRequest()   // +1, y arma el show diferido
endBlockingRequest()     // -1, y arma el hide con piso de visibilidad
resetBlockingLoader()    // solo tests: limpia timers y contador
```

El contador y los dos timers viven en estado **a nivel de módulo**, no en el componente: sobreviven
el desmontaje y remontaje de la isla, así que una mutación en vuelo durante una navegación conserva
su overlay en vez de perderlo. Un único escritor (`sync()`) empuja `pending` y `visible` al store, de
modo que no pueden divergir. Ver la sección siguiente para el contrato completo.

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
  async postForm<T>(path, form: FormData): Promise<T>
}
```

`postForm` existe para subidas multipart: un body `FormData` debe mantener el
`Content-Type` que el navegador genera (`multipart/form-data; boundary=...`, la
boundary no puede fijarse a mano), así que es el único método que no setea
ningún header de content type ni pasa el body por `JSON.stringify`.

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

## Loader de página completa (peticiones bloqueantes)

Las llamadas que el usuario percibe como lentas tienen una señal global: un velo a pantalla completa
con un spinner y el texto `common.processing`. Se monta **una sola vez**, en `DashboardShell`
(`src/components/react/FullPageLoader.tsx`), porque toda mutación de `ApiClient` en la aplicación
ocurre debajo de ese shell. No existe en las páginas públicas: ninguna de ellas importa `ApiClient`.

### Qué lo dispara

**Automático por método HTTP, con lista de excepciones** — no opt-in por acción. `ApiClient.request()`
y `ApiClient.postForm()` llaman a `shouldBlockRequest(method, path)`
(`src/lib/blocking-requests.ts`) y envuelven la petición en `beginBlockingRequest()` /
`endBlockingRequest()` dentro de un `try/finally`.

| Método | ¿Bloquea? |
|---|---|
| `POST`, `PUT`, `PATCH`, `DELETE` | sí, salvo excepción |
| `GET`, `HEAD`, `OPTIONS` | nunca |

Las lecturas quedan exentas por método, y eso es lo que mantiene fuera del overlay al sondeo de
extracción (un `GET` cada 2 s) y a todos los refrescos de fondo, sin necesitar una excepción por
call site. La query string y el hash se descartan antes de comparar, así que una excepción no se
esquiva ni se dispara por parámetros.

Las tres excepciones, cada una con su motivo escrito en el propio código (`BLOCKING_EXCLUSIONS`):

| Path | Por qué no bloquea |
|---|---|
| `PATCH /api/v1/users/me/onboarding` | Escritura automática del primer login, disparada por el modal de onboarding. |
| `POST /api/v1/workspaces/{ws}/settings/llm/models` | Sondeo automático de modelos. Es `POST` sólo porque la selección puede llevar una API key que no debe quedar en el query string de un log de acceso. |
| `POST /api/v1/workspaces/{ws}/extract/` | El arranque de extracción responde `202` al instante y la página de la historia ya tiene su propia UI de pendiente (selector de versiones, toast y poll). |

### Cuándo se ve

El overlay no aparece en cualquier mutación, sólo cuando la mutación **se demora**; sin esto, el
disparador automático haría parpadear la pantalla entera en cada arrastre de tarjeta Kanban (un `PUT`
que responde en ~100 ms).

| Constante | Valor | Efecto |
|---|---|---|
| `BLOCKING_LOADER_DELAY_MS` | 250 ms | El overlay sólo se pinta si la petición sigue en vuelo al vencer el plazo. Una petición más rápida nunca lo muestra. |
| `BLOCKING_LOADER_MIN_VISIBLE_MS` | 400 ms | Piso de visibilidad **medido desde que el velo apareció**, no desde que el trabajo terminó. Es el antídoto contra el parpadeo, nunca una espera extra: una petición que ya duró 10 s se oculta en el acto (`max(0, MIN_VISIBLE - (ahora - visibleSince))`). |

Dos escrituras consecutivas cuentan como una sola operación: el `begin` de la segunda llega antes de
que venza el `hide` de la primera, así que el velo no baja entre medio. Es exactamente el caso de
invalidar una tarea, que hace `POST` de la marca y después `PUT` de la tarea.

### z-index

`z-[60]`, y el valor es deliberado: por encima de los diálogos de shadcn (`z-50` en `dialog.tsx`,
`alert-dialog.tsx` y `sheet.tsx`) para que el velo también tape el diálogo que el usuario acaba de
confirmar, y por debajo de sonner (`z-index: 999999999`, `sonner/dist/styles.css`) para que el toast de
éxito que se dispara al resolver la petición se lea por encima. La cadena de ancestros del overlay no
crea ningún stacking context, así que su `60` compite en el contexto raíz con el `50` de los diálogos.

### Caso límite aceptado

Se monta también cuando el usuario borra su cuenta (`DELETE /api/v1/users/me`) — a propósito: es una
mutación lenta e irreversible, y el velo es la única señal de que algo está pasando antes de que el
navegador se vaya del sitio.

### Verificación

Medido en el navegador el 2026-10-05, con latencia real inyectada por CDP (1500 ms): un `POST` real
no pinta el velo a los 120 ms, sí lo pinta a los 620 ms, un `GET` nunca toca el contador, y un error
`404` lo libera y baja el velo (la rama `finally`, o sea el modo de falla «overlay trabado para
siempre»), con `elementFromPoint` devolviendo el overlay en las cuatro esquinas y el centro. El
comando exacto y la salida cruda están en `odd/tasks/blocking-page-loader.md`.

## Contrato de los diálogos: techo de altura y scroll

Todo popup de `Dialog` (`ui/dialog.tsx`) y `AlertDialog` (`ui/alert-dialog.tsx`) lleva
`max-h-[calc(100dvh-2rem)]` y `overflow-y-auto overscroll-contain`, y es `flex flex-col`. El techo es
obligatorio: sin él la altura la decide el contenido, y como el popup está centrado con
`-translate-y-1/2`, un diálogo alto crece para los dos lados y lo que sobra queda recortado **sin
ningún scroll** — que fue exactamente el defecto que dejó el botón de guardar del editor de tareas
inalcanzable (883 px en un viewport de 757 px, con el header en `top -63` y el Save en `772-804`).

`dvh` y no `vh`: en Safari de iOS `100vh` incluye el área de la barra de URL y el diálogo se corta igual.
El idioma ya estaba en el repo — `MobileNav.tsx` ya pasa un techo `dvh` a su `SheetContent`.

**Un call site puede sobrescribir el scroll o el techo.** `cn()` es `twMerge(clsx(...))`, así que la clase
del call site gana por venir última. Eso no es un detalle: es lo que permite que un diálogo con estructura
propia funcione. `TaskEditor` pasa `overflow-hidden` para que el popup no scrollee y puedan quedar el
título y el footer fijos mientras scrollean sólo los campos; `CommandDialog` pasa `overflow-hidden` y deja
que su lista interna (`max-h-72 overflow-y-auto`) sea el único scroller. Un test de contrato
(`ui/__tests__/dialog.test.tsx`) fija esa dependencia, porque cambiar `twMerge` por `clsx` la rompería en
silencio.

El patrón para un diálogo alto que quiera header y footer fijos:

```tsx
<DialogContent className="sm:max-w-2xl max-h-[calc(100dvh-2rem)] overflow-hidden">
  <DialogHeader className="shrink-0">…</DialogHeader>
  <div className="min-h-0 flex-1 space-y-5 overflow-y-auto">…campos…</div>
  <DialogFooter className="shrink-0">…</DialogFooter>
</DialogContent>
```

`min-h-0` es lo que permite que un hijo flex encoja por debajo de su tamaño de contenido; sin él la región
scrolleable crecería para entrar y el arreglo no haría nada. No usar `sticky` para el footer: con el `p-4`
del popup y los márgenes negativos que ya trae `DialogFooter` (`-mx-4 -mb-4`), un `sticky bottom-0` queda
un rem fuera del scrollport y se corta.

Verificación: jsdom no tiene motor de layout, así que un test unitario de esto sólo puede afirmar clases.
Lo que lo prueba es el probe en navegador — abrir el diálogo, tildar el campo que lo hace más alto, y
comprobar que `elementFromPoint` en el centro del botón principal lo devuelve. Medición, pasada visual y
hallazgos en `odd/tasks/dialog-viewport-overflow.md`.

## Redirecciones internas: `window.location.assign` vs `navigate()` de Astro

Decisión pendiente **aceptada**: las redirecciones internas siguen usando `window.location.assign`
(recarga completa) en lugar del `navigate()` de Astro con View Transitions (navegación SPA sin
recarga). Migrar mejoraría la UX y silenciaría el scanner de open-redirect; las cinco redirecciones
son internas por construcción (`localizedPath` clampea el locale y los destinos llevan UUIDs), así
que el riesgo real es bajo. El trade-off que la mantiene abierta: son cinco call sites que tocar y
el orden de montaje de las islas después de una navegación SPA no tiene hoy ningún test de navegador
(ver las brechas de verificación en `testing.md`).

Call sites medidos el 2026-09-23 con
`grep -rn 'window\.location\.assign' frontend/src --include='*.ts' --include='*.tsx'`:

| Archivo | Línea | Contexto |
|---|---|---|
| `frontend/src/components/react/WorkspaceSettings.tsx` | 187 | redirect al dashboard tras eliminar el workspace |
| `frontend/src/components/react/StoriesList.tsx` | 384 | click en una story |
| `frontend/src/components/react/ProjectsList.tsx` | 169 | click en un proyecto |
| `frontend/src/components/react/AccountPage.tsx` | 200 | cambio de idioma (`localizedPath`) |
| `frontend/src/components/react/DeleteAccountDialog.tsx` | 61 | post-eliminación de cuenta |
