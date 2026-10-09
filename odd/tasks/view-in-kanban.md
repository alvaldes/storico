# ODD Feature: view-in-kanban

> **Status**: cerrada. Abre la única puerta de entrada que le faltaba a la cascada de filtros del
> tablero: hoy sólo se llega a un tablero filtrado eligiendo proyecto, historia y versión a mano
> dentro del propio tablero.
> **Created**: 2026-10-08 (pedido del owner de esa fecha)
> **Workflow**: Organic Driven Development (ODD)
> **Branch**: `feat/versioning-visibility` (continuación, decisión del owner: la cascada de filtros
> sólo existe en esta rama; en `main` el tablero sigue sin filtros).

## Problem

La feature `versioning-visibility` dejó el tablero filtrándose por proyecto → historia → versión,
resuelto en el servidor por el alcance más específico (D5 de ese documento). Lo que no dejó es
**cómo llegar a un tablero ya filtrado**: el único camino es entrar a `/[locale]/kanban` y elegir la
cascada a mano, aunque el usuario ya esté mirando exactamente ese proyecto o esa historia en otra
pantalla.

Medido en el código:

- `KanbanBoard.tsx:86-88` arranca la cascada en `null` en los tres niveles, y `KanbanBoardProps`
  (`KanbanBoard.tsx:40-42`) sólo acepta `locale`. La página
  (`frontend/src/pages/[locale]/kanban.astro:15`) le pasa nada más que `locale`. No hay ningún
  lector de query params en el frontend salvo `login.astro:72`.
- Las cuatro superficies donde el usuario mira un proyecto o una historia ya tienen su cluster de
  acciones: `ProjectsList.tsx:182-218` (menú Editar/Eliminar), `ProjectDetail.tsx:112-127`,
  `StoriesList.tsx:479-504` (Editar/Eliminar por fila), `StoryDetail.tsx:504-520`. Ninguna navega al
  tablero.
- `UserStory.projectId` existe (`frontend/src/types/story.ts:39`), así que una superficie que muestra
  una historia **ya sabe** a qué proyecto pertenece sin pedir nada.

## Decisions

| #  | Decisión | Elección |
|----|----------|----------|
| D1 | Mecanismo de entrada | **Query params en la ruta del tablero**: `/[locale]/kanban?project=<id>` y `?story=<id>`. `kanban.astro` los lee de `Astro.url.searchParams` y se los pasa al islote como props. El seed viaja con el HTML: el tablero se hidrata ya filtrado, sin una lectura previa del cliente, y el link queda compartible. No se escribe ningún store: `storyStore` es de la página de historias y el tablero tiene prohibido escribir ahí. |
| D2 | Alcance del seed | **Cascada completa**: un link a una historia lleva también su proyecto. Las cuatro superficies tienen el `projectId` a mano, así que el tablero nunca recibe un nivel hijo sin su padre — la misma invariante que ya respetan `handleProjectChange`/`handleStoryChange` (`KanbanBoard.tsx:264-280`) y el reset por cambio de workspace. |
| D3 | `?story` sin `?project` | El tablero **no** lo siembra: la invariante de D2 lo prohíbe, y resolverlo con `getStory` costaría una lectura extra sólo para un caso que ninguna superficie propia produce. Si además viene `?project`, ese nivel sí se aplica; si no, el tablero carga sin filtros. Es degradación honesta y queda documentada, no un estado a medias silencioso. |
| D4 | El seed sobrevive la primera hidratación del workspace | El reset por cambio de workspace (`KanbanBoard.tsx:130-131`) hoy limpia los filtros cuando `workspaceId` pasa de `undefined` a un id real — que es exactamente el arranque de una sesión sin `currentWorkspace` persistido. Con un deep link, eso borraría la cascada sembrada antes de su primer fetch. Se corrige: el reset sólo dispara cuando el workspace anterior era uno real (`prevWorkspaceId !== undefined`). **Es un defecto que el deep link expone, no una preferencia.** |
| D5 | El botón | Un link de verdad: `<a href>` renderizado a través del `render` de `Button` (patrón Base UI ya usado por los triggers del tablero), con icono + `t.kanban.view_in_kanban`. Dentro de las filas clicables de las listas frena la propagación, igual que los botones de editar/eliminar existentes, para que la navegación al detalle de la fila no compita con la del botón. |
| D6 | Copy | `kanban.view_in_kanban` en `en.json`/`es.json`: `View in Kanban` / `Ver en Kanban`. Español neutro internacional por ADR-008; la paridad de claves ya está guardada por `frontend/src/i18n/__tests__/neutral-spanish.test.ts:152`. |
| D7 | Sincronización de la URL | **No hay.** El seed es de una sola vez, en la entrada; después el usuario puede cambiar o limpiar filtros y la URL no se actualiza. Mantener la barra y la query en espejo es otra feature (y la primera que pediría un `replaceState` por cada cambio). |

## Non-goals

- Deep link a una **versión** concreta (`?version=`). Sólo proyecto e historia.
- Refrescar la URL cuando cambian los filtros dentro del tablero (D7).
- Resolver `?story` huérfano con una lectura extra de la historia (D3).
- Cualquier cambio de backend: no hace falta ni un endpoint ni un campo nuevos.
- Un botón "Ver en Kanban" en el Dashboard o en las cards del propio tablero.

## Verified facts (with evidence)

- `KanbanBoard.tsx:40-42` — `KanbanBoardProps` es `{ locale?: Locale }`.
- `KanbanBoard.tsx:86-88` — los tres niveles de la cascada arrancan en `null`.
- `KanbanBoard.tsx:126-133` — reset de filtros por cambio de workspace, en fase de render.
- `KanbanBoard.tsx:216-248` — `activeFilters` (un solo alcance) y `filtersKey`/`loadTasks`.
- `frontend/src/pages/[locale]/kanban.astro:15` — `<KanbanBoard client:load locale={locale} />`, el
  único prop que recibe hoy.
- `frontend/src/layouts/MainLayout.astro:2,41` — `ClientRouter` activo: la navegación es de cliente,
  pero el servidor sigue renderizando la página nueva, así que las props derivadas de
  `Astro.url.searchParams` viajan bien.
- `ProjectsList.tsx:169` y `StoriesList.tsx:433` — navegación por `window.location.assign`; las cards
  de ambas listas son clicables enteras.
- `frontend/src/types/story.ts:39` — `projectId: string` en `UserStory`.
- `frontend/src/components/ui/button.tsx:47-56` — `Button` es `ButtonPrimitive` de `@base-ui/react`,
  así que acepta `render={<a ... />}`.
- `openspec/specs/kanban-board/spec.md` — "Kanban Page Route" nombra a `locale` como el prop del
  islote, y "Kanban Filter Cascade" fija el alcance más específico. Un seed por props toca las dos.
- `openspec/config.yaml` — `strict_tdd: true`; el runner de frontend es `cd frontend && pnpm test`
  (vitest).

## Tasks

- [x] **WU1 — Entrada por deep link al tablero (frontend)** → `3054f51`. `kanban.astro` lee `project`
  y `story` de `Astro.url.searchParams` y se los pasa al islote; `KanbanBoard` acepta
  `initialProjectId`/`initialStoryId`, siembra la cascada con la regla de D2/D3 y corrige el reset de
  workspace de D4. RED observado en tres de los cuatro casos nuevos (los props ignorados, y el reset
  viejo comiéndose el seed en la transición `undefined → workspace-1`); GREEN: 51/51 en
  `KanbanBoard.test.tsx` y `tsc --noEmit` en 0. La suite completa de frontend queda para el cierre.
- [x] **WU2 — El botón en las cuatro superficies (frontend)** → `dd90427`. `ProjectsList` y
  `StoriesList` con el link icon-only dentro de sus clusters (que ya frenan la propagación),
  `ProjectDetail` y `StoryDetail` con el botón con etiqueta en su header, y `kanban.view_in_kanban`
  en los dos catálogos. RED observado: seis casos nuevos fallando sobre el rol `link` inexistente;
  GREEN: 123/123 en las seis suites tocadas (las cuatro del botón, `accessible-name-collisions` y
  `src/i18n/__tests__`) y `tsc --noEmit` en 0.
- [x] **WU3 — Specs y cierre** → delta en `319cbb4`. `openspec/specs/kanban-board/spec.md` gana el
  requisito "Kanban Deep-Link Entry" con cuatro escenarios, extiende "Kanban Page Route" y corrige
  la frase del cambio de workspace que se leía como si exigiera el defecto de D4.

## Limits and follow-ups

- El seed no valida contra el workspace: un `?project=<id de otro workspace>` produce el error del
  backend en el tablero (o un tablero filtrado vacío), que es el mismo camino de error que ya existe
  para un filtro elegido a mano. No se inventa una validación de cliente que el servidor ya hace.
- La cascada sigue leyendo las historias del proyecto con `listStories(projectId, 1, 100)`
  (`KanbanBoard.tsx:143-166`), así que un proyecto con más de 100 historias tiene historias
  inseleccionables — límite previo de `versioning-visibility`, no se toca acá. Un deep link a una de
  esas historias sembraría el nivel de historia sin que el select pueda mostrar su label.
- El botón no pide confirmación ni muestra progreso: es un link, navega y listo.
- **Dos desviaciones registradas, las dos en los tests de WU2.** (a) jsdom 29 mantiene `window.location`
  no forjable (`configurable: false`, `writable: false`), así que `spyOn(window.location, 'assign')`
  no se puede usar: los dos tests de contención del click testigo con un listener burbujeante en
  `document`, que es fiel porque el handler de la fila corre mientras el click burbujea por el
  contenedor de React — si el click escapa del link, el listener de `document` lo ve. (b) El caso de
  `?story` huérfano pasó ya en RED (el default sin sembrar ya ignoraba el id), así que no aportó señal
  de fallo; queda como guarda que fija la regla después de la implementación.
- **Pendiente de limpieza, fuera del alcance de esta feature**: hay un
  `console.log('DEBUG-HTML', …)` commiteado en el describe WU20 de
  `frontend/src/components/react/__tests__/KanbanBoard.test.tsx`. Sale por stderr en cada corrida de
  la suite. No se tocó: es un cambio sin relación con esta feature y merece su propio commit.
- **La página de docs del tablero no menciona los filtros ni el botón.**
  `frontend/src/content/docs/{en,es}/docs/kanban.md` (81 líneas cada una) describe el tablero sin
  nombrar la cascada, que es una deuda anterior de `versioning-visibility`; documentar sólo el botón
  dejaría la mitad del camino adentro. Se deja como follow-up conjunto, no como parte de WU3.

## Closure

Rama `feat/versioning-visibility` (decisión del owner: la cascada de filtros sólo existe acá). Cuatro
commits:

| Commit | Unidad |
|--------|--------|
| `f42107d` | plan (este documento) |
| `3054f51` | WU1 — entrada por deep link al tablero |
| `dd90427` | WU2 — el botón en las cuatro superficies + `kanban.view_in_kanban` |
| `319cbb4` | WU3 — delta de spec en `openspec/specs/kanban-board/spec.md` |

Gates, corridos por un verificador independiente sobre el árbol commiteado, no por quien escribió el
código:

- `cd frontend && pnpm exec vitest run` → **79 archivos, 904 tests, 0 fallos**.
- `cd frontend && pnpm exec tsc --noEmit` → **exit 0**.
- `cd frontend && pnpm build` → **exit 0**, `[build] Complete!`. Ningún warning ni error nombra el
  islote del tablero, `view_in_kanban` ni los props nuevos; los dos `[WARN] Astro.request.headers`
  que aparecen son de la ruta de docs de Starlight, no de la app.
- **Backend sin gates y sin cambios**: los tres commits de la feature no tocan ningún path de
  `backend/`. Los 17 archivos de backend que `git diff --name-only main...HEAD` lista vienen de
  commits anteriores de la rama, no de acá.
- Los dos catálogos de i18n siguen con **764 claves cada uno y cero diferencias** (verificado
  aplanando ambos archivos desde el commit, no desde el working tree).
- Verificado además por lectura del código commiteado: el seed sólo vive en los `useState` (ningún
  efecto lo reaplica, no se agregó ninguna lectura extra), la guarda del reset distingue primera
  llegada de switch real, y los cuatro `href` son exactamente las dos plantillas de D5.

Lo que la verificación **no** cubrió, dicho sin adornos: no hubo ejercicio en navegador —el deep link
y la contención del click se sostienen en la lectura del código commiteado más los tests—, y el RED de
WU1/WU2 lo observó el worker que implementó, no el verificador.
