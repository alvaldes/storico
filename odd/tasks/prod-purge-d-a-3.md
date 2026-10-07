**Registro de evidencia — no es una segunda lista de pendientes.** La regla de `prod.todo.md` es que un
ítem cerrado se marca allí y su detalle vive en el documento que le corresponda; para este registro, ese
documento es este archivo. Los ítems que seguían abiertos dentro del post-mortem vuelven a `prod.todo.md`
como pendientes vivos, cada uno con una línea que apunta acá.

**Qué es:** el registro de la purga de producción, el merge y el deploy que desbloquearon la revisión
`0028` (decisión **D-a-3**), cerrado y verificado el 2026-09-30.

**De dónde viene:** era la sección `## Bloqueo de despliegue (D-a-3)` de `prod.todo.md`; se movió aquí el
2026-10-07 porque 284 líneas de post-mortem no pertenecen dentro de una checklist operativa.

**La movida no editó nada:** el cuerpo de abajo está movido verbatim —sin reformular, recortar, reordenar
ni reformatear—. Lo único que cambió es el nivel de los encabezados (`##` → `#`, `###` → `##`, para que
este archivo tenga un solo H1) y una corrección fechada junto al marcador del merge, dejada en su lugar
más abajo sin borrar la frase original.

**Por qué `prod.todo.md` conserva una redirección:** varios registros archivados en
`openspec/changes/archive/**` citan `prod.todo.md` como la ubicación de este registro; esas citas eran
ciertas cuando se escribieron y no se reescriben. La redirección hace que seguir una cita vieja todavía
llegue al contenido.

---
# Bloqueo de despliegue (**D-a-3**): **CERRADO** — purga, merge y deploy verificados el 2026-09-30

**Descubierto el 2026-09-30, al cerrar el slice (a) de versionado de extracciones (PR #30). Ningún
otro archivo de este repo lo decía. Cerrado el mismo día: purga ~04:28 UTC, merge `1dcc716`, deploy
`run 36675276096` success.**

`0028_extraction_versioning` lee `SELECT count(*) FROM extractions` y `SELECT count(*) FROM tasks`
antes de tocar el esquema, y **lanza `RuntimeError` si alguna de las dos tablas tiene una fila**
(decisión D11: no se hace backfill). `.github/workflows/deploy-backend.yml:101` ejecuta
`alembic upgrade head` en la ventana de mantenimiento de **todo** despliegue.

**La premisa ahora está medida en el lugar correcto (2026-09-30).** Esta fila afirmaba que producción
tiene datos citando la colección **Qdrant** `storico_extractions_prod`, medida el 2026-09-28. No es la
misma cosa: la guarda de `0028` cuenta las tablas **relacionales** de Neon. Conectando en lectura —solo
`SELECT count(*)`, sin DDL y sin imprimir la cadena de conexión—, medido directamente:

| Medido en producción | Valor |
| --- | --- |
| `alembic_version` | **`0027`** — `0028` es la siguiente y **se va a negar** |
| `extractions` | **17** (11 `failed`, 6 `completed`; span 2026-08-03 → 2026-09-24) |
| `tasks` | **42**, todos en `status = backlog` |
| `user_stories` / `projects` / `users` / `workspaces` | 6 / 3 / 3 / 4 |
| `workspace_llm_configs` | 4 — una referencia el proveedor personalizado `'Nan'`, con API key cifrada, `temperature 0.1`, `max_tokens 2048` |
| `task_invalidations` | **la tabla no existe** (consecuencia natural de estar en `0027`) |

Cada número salió de dos caminos SQL independientes que coinciden; donde no coincidían, la sonda se
descartó y no se reportó. La primera pasada usó `fetchval` sobre consultas de varias filas y devolvió
solo la primera: reportó `temperature` como reconstruible cuando no lo es.

Consecuencia exacta: **mergear `main` con `0028` dentro deja la API abajo a propósito.** El `docker stop`
ya ocurrió, la migración falla, y el `docker run` no llega — que es el comportamiento diseñado del
workflow (un fallo deja la API abajo antes que servir contra un esquema que no coincide), pero no es
un despliegue: es una caída.

`0028` es correcta como código; lo que faltaba era la decisión operativa. **Elegida el 2026-09-30:
camino 1, ventana de purga.** El merge y la purga siguen siendo dos decisiones ordinarias aparte, y
**ninguna se ejecutó**: nada se borró en producción al escribir esta línea.

Antes de elegir se midió el costo real de cada camino, y dos afirmaciones de este documento estaban
mal: D11 nombraba la columna equivocada y el costo de la purga estaba sobrevendido.

| Campo que una `0029` tendría que rellenar | Estado medido |
| --- | --- |
| `temperature` | clave presente en 17/17 filas pero **valor `null` JSON en 17/17** → no reconstruible. Ojo: `prompt_config ? 'temperature'` (clave) da 17 y `->> 'temperature' IS NOT NULL` (valor) da 0; mirar solo la clave saca la conclusión contraria |
| `provider` | **derivable por fila** por la cadena story → project → workspace → `workspace_llm_configs.provider` (17/17 con config). Es una *suposición*: la config de hoy no es necesariamente la del 3 de agosto |
| `version_number` | derivable ordenando `created_at` dentro de la historia; solo 2 historias tienen más de una extracción (9 y 4) |
| `tasks.extraction_id` | **esto es lo irreductible**: 28 de 42 tasks caen en historias con una sola extracción (derivable); **14 de 42** caen en las dos historias multi-run y no hay registro de qué run los produjo |

Y el costo de la purga era más chico y distinto del escrito: el `id` del punto de Qdrant **es** el
`extraction_id` (`qdrant_adapter.py:255`), y el payload se alcanza solo (`user_story_text`,
`tasks_summary`, `model_used`, `workspace_id`). Purgar no rompe el few-shot: lo que se pierde es
**procedencia**, no funcionamiento. Lo que se purga son 11 runs fallidos y 42 tareas que nunca salieron
de `backlog`.

Los tres caminos, ya evaluados:

1. **Ventana de purga.** ← **ELEGIDO y EJECUTADO el 2026-09-30 ~04:28 UTC.** Borrar los datos relacionales
   de las once tablas del esquema de negocio en Neon —y los puntos de las tres colecciones de Qdrant—
   antes de mergear, y dejar que `0028` corra sobre el par vacío. Es lo que el propio mensaje de la guarda
   indica. Sin respaldo: se reemplazó por inventario commiteado, que además fue la condición del interlock
   (ver "Ejecución real"). Corregido por medición: no "pierde la coherencia de los puntos de Qdrant", pierde
   la procedencia de 17 runs de prueba **y las dos únicas copias de dos API keys, eso último a sabiendas
   del owner**.
2. **Revisión de backfill aparte.** Descartada por costo: habría que afirmar tres cosas —`temperature`
   inventado en las 17 filas, `provider` por hipótesis de config actual, y un run elegido a mano para
   14/42 tasks— sobre datos que la medición describe como tráfico de prueba. Queda disponible si la
   evaluación de la tesis necesita conservar esos runs.
3. **No mergear todavía.** Descartado: fue lo que venía pasando hasta el 2026-09-30, y era el camino que
   el plan de slices asumía al decir que (a) no estaba desplegado. **Hoy (a) está desplegado**, así que esta
   opción ya no existe; queda anotada porque fue la opción por defecto durante todo el desarrollo del slice.

## Ejecución real (2026-09-30, ~04:28 UTC)

**EJECUTADO el 2026-09-30 ~04:28 UTC por orden del owner, sin respaldo.** Secuencia real y su evidencia:

1. **Interlock antes de romper.** Un script midió los once conteos, `alembic_version` y los tres
   conteos de Qdrant, y **se negó a ejecutar el `TRUNCATE` si algo no coincidía exactamente con el
   inventario commiteado en `9a5086c`.** Coincidieron los doce números, así que el borrado empezó con
   una prueba de que no había dato no inventariado. Esperado-vs-encontrado se comparó **en memoria**, no
   leído por mí: después de dos errores propios en esta sesión por leer mal una salida de herramienta,
   esa elección no es decoración.
2. **Purga relacional:** `TRUNCATE` de las once tablas en **una sola transacción**, `RESTART IDENTITY
   CASCADE`.
3. **Purga vectorial:** `POST /collections/{name}/points/delete?wait=true` con `"filter": {}` en las tres
   colecciones. La API key de `.env.prod.local` **sí tiene permisos de escritura** (operaciones 4, 4 y
   101, todas `completed`): la sospecha de clave de sólo lectura del runbook era falsa.
4. **Verificación con un proceso distinto**, releyendo desde cero: **once tablas en 0**, tres colecciones
   en **0 puntos** con `status=green`, `alembic_version` todavía **`0027`**, `task_invalidations`
   sigue sin existir (viene con `0028`, por el merge).
5. **La app no se cayó:** `GET /api/v1/health` → `status ok`, `database ok`, `schema ok`, `version
   0.8.0`. `ollama: not reachable` es opcional y ya era así antes.

⚠️ **Lo que hay que NO hacer desde ahora y hasta el merge.** La guarda de `0028` mira si hay filas. **Una
sola extracción ejecutada en producción vuelve a poblar `extractions` y devuelve el bloqueo exacto que
acabamos de pagar con datos.** Con `workspace_llm_configs` vacío el few-shot tampoco tiene de dónde
sacar, así que no hay ninguna ganancia en extraer ahora: **no correr extracciones en prod hasta que el
merge aplique `0028`**. No lo probé porque probarlo es escribir, y escribir ahora recrea el problema.

🔲 **Pendiente de datos: el merge** (decisión del owner). Recién con las tablas en cero, el merge a `main`
dispara `deploy-backend.yml`, `alembic upgrade head` corre `0028` sobre bases vacías y pasa la guarda.
Después: `alembic_version` = `0028`, `task_invalidations` existe, once tablas en 0, tres colecciones en 0.

**Corrección (2026-10-07), dejada junto a la frase original porque el paso que este marcador esperaba se
completó ese mismo día:** el merge a `main` entró (`1dcc716`) y el deploy (`run 36675276096`) corrió
`0028` sobre las bases vacías. La frase se conserva tal como se movió —el marcador 🔲 quedó abierto para
un paso completado—; la verificación posterior es el cierre marcado ✅ más abajo.

~~⚠️ **No correr extracciones en producción hasta el merge.**~~ **Hecho: el merge entró (`1dcc716`) y el
deploy aplicó `0028`.** La restricción dejó de tener efecto en el momento en que la guarda dejó de estar
en el camino: `0028` ya corrió, así que una extracción nueva ya no recrea el bloqueo. Lo que sí sigue
bloqueando es la credencial, abajo.

🔲 **Pendiente posterior, y es de uso — ahora con un detalle que no era obvio: la app no tiene cómo
extraer hasta que alguien cree un config.** Re-cargar la clave de AI Studio y la de nan.builders en
Configuración. No es un capricho: `resolve_llm_config` (`api/routes/workspace_settings.py:121-129`)
cuando el workspace **no tiene fila de config** devuelve `provider = "ollama"` con
`base_url = settings.ollama_host`, y en producción Ollama no existe (`health/services` → `ollama:
not reachable`, scope optional). O sea que el default tras la purga es **un proveedor inalcanzable**: la
primera extracción falla por configuración, no por código. Crear el config (`gemini` + `gemini-2.5-flash`
+ la clave de AI Studio) es el paso que destraba la app. El proveedor `Nan` se recrea con su nombre,
`api.nan.builders` y su clave. Y hace falta loguearse de nuevo: no hay ni `users` ni workspaces.

✅ **Cierre verificado (2026-09-30, post-deploy, lectura):** `alembic_version = 0028`,
`task_invalidations` existe con `fk_task_invalidations_revoked_by_users ... ON DELETE RESTRICT` — la
task 4.4 y la opción A del owner, ahora probada en el Postgres de producción y no sólo en el de CI —,
`uq_extractions_story_version`, `uq_task_invalidations_active_task` (parcial, `WHERE revoked_at IS
NULL`), `ck_task_invalidations_revoke_pair` y `ck_task_invalidations_reason_not_blank` presentes,
`tasks.extraction_id` `NOT NULL`, once tablas todavía en 0, y `/api/v1/health` → `ok` (`database ok`,
`schema ok`). Leída en ese instante la app todavía reportaba `0.8.0`: **el bump a `0.9.0` corrió
después, el mismo día** (sección "Release `v0.9.0`").

🔲 **No hace falta tocar la VM ni el `.env`:** `STORICO_ENCRYPTION_KEY` sigue ahí y ahora no tiene
ningún ciphertext que desencriptar; `STORICO_GOOGLE_API_KEY` sí sigue sirviendo, para el embedding.

~~**Modificado el 2026-09-30 por decisión del owner: no se toma respaldo.**~~ Se cumplió: en lugar del
respaldo quedó el inventario commiteado, que es lo que el interlock usó como condición de partida.

## El andamiaje de operación: los scripts viven en `~/storico-ops/` (fuera del repo, a propósito)

Las sondas y la purga de esta sección **no se escribieron dentro del repositorio ni corrieron por un
router de la app**: son scripts de un solo uso que hablan contra producción con el DSN de
`.env.prod.local`, y se ejecutan con `conda run -n storico python ~/storico-ops/<script>.py`.

Copiados de `/tmp` a `~/storico-ops/` el 2026-09-30, con su `README.md` al lado que los clasifica por
riesgo (🔴 muta producción / 🟢 lectura / 🟡 toca material sensible en memoria). Razón de ser de la
copia: `/tmp` se limpia al reiniciar, y esta sección describe un runbook que alguien va a tener que
volver a ejecutar.

**Ninguno está bajo control de versiones, y ninguno debería estarlo.** No embuten secretos: todos leen
`os.environ`. Dos cosas que hay que saber antes de reutilizarlos, del README:

- `d_a_3_purge.py` **no se vuelve a correr tal cual**: su interlock fija `EXPECTED_ALEMBIC = "0027"` y
  producción está en `0028`, así que hoy **se niega solo**. Eso es el diseño funcionando. Cualquier purga
  futura necesita un bloque `EXPECTED_*` freshly medido, nunca heredado.
- El patrón que vale la pena robar no es el script, es **el interlock**: una purga se ejecuta detrás de
  una re-medición que se niega a correr si la realidad cambió, no detrás de mi lectura de hace una hora.
  Esta sesión me equivoqué dos veces leyendo datos de producción (`provider = 'Nan'` y la tabla donde
  vivía el conteo de D-a-3); el interlock es lo que hizo que esas dos veces no fueran destructivas.

## El inventario que reemplazó al respaldo (medido antes de borrar)

Inventario medido el 2026-09-30, en lectura, contra la base y el cluster de producción. Ampliado el
mismo día: el owner eligió **todo el esquema de negocio, incluidas configs y prompts**, así que la lista
ya no es "el par" sino las once tablas que tienen filas. `alembic_version` **no se toca**: tiene que
quedar en `0027` para que el deploy siguiente aplique `0028`.

| Tabla | Filas | Qué se pierde |
| --- | --- | --- |
| `users` | 3 | las identidades (no hay passwords: es OAuth). **Vuelven solas**: el primer login crea usuario + workspace personal + rol admin + `workspace_prompt` (`api/routes/auth.py:119-126`) |
| `user_accounts` | 3 | los vínculos OAuth: hay que volver a loguearse con Google/GitHub |
| `workspaces` | 4 | toda la estructura de permisos |
| `workspace_members` | 4 | los roles, incluido el admin que crea workspaces |
| `projects` | 3 | — |
| `user_stories` | 6 | 5 en `extracted`, 1 en `pending_extraction` |
| `extractions` | 17 | 11 `failed`, 6 `completed`; span 2026-08-03 23:16 → 2026-09-24 20:17 UTC |
| `tasks` | 42 | los 42 con `status = backlog`; ninguno avanzó nunca de ahí |
| `workspace_llm_configs` | 4 | **incluye 2 `api_key` cifradas que no existen en ningún otro lugar de esta máquina** |
| `workspace_prompts` | 3 | `few_shot_enabled=true`, `limit=3`, `threshold=0.85`, `system_prompt` de 126 caracteres |
| `custom_providers` | 1 | el proveedor `Nan` |

**Las dos claves que no se recuperan desde acá, y el owner decidió borrarlas igual.** Desencripté en
memoria y comparé contra los 39 valores disponibles en esta máquina (los `STORICO_*` de
`.env.prod.local` + `.env`, más el entorno del proceso): **ninguna** de las dos `api_key` de producción
coincide con algo que exista acá. `Nan/qwen3.8-flash` (25 caracteres de plaintext) y
`gemini/gemini-2.5-flash` (39) viven únicamente en esas dos filas. Se le mostró esto al owner como el
único punto sin retorno de la operación, y la respuesta fue borrarlas igual. Consecuencia operativa:
antes de extraer nada después de la purga hay que volver a sacar la clave de AI Studio y la de
nan.builders y re-cargarlas en Configuración. Para reconstruir el config no hace falta recordar los
números: están acá.

| provider | model | host de `base_url` | `temperature` / `max_tokens` |
| --- | --- | --- | --- |
| `Nan` | `qwen3.8-flash` | `api.nan.builders` | 0.1 / 2048 |
| `gemini` | `gemini-2.5-flash` | `localhost:11434` | 0.1 / 2048 |
| `ollama` | — | — | sin clave, sin modelo |
| `ollama` | — | — | sin clave, sin modelo |

Raro, anotado sin concluir nada: el config `gemini` de producción tiene `base_url = localhost:11434`, una
URL de Ollama local en una fila de producción. Puede ser residuo de una prueba, y puede que el adapter de
Gemini la ignore y use `STORICO_GOOGLE_API_KEY`. No lo afirmo sin medirlo.

| Almacén vectorial | Contenido al momento de medir |
| --- | --- |
| Qdrant `storico_extractions_prod` | **1** punto, 768 dims |
| Qdrant `storico_extractions_dev` | **1** punto — esta colección **no existía el 2026-09-28**: alguien escribió desde dev contra el cluster de producción |
| Qdrant `storico_extractions` (legado) | **19** puntos |

## Runbook como se planificó (ya ejecutado; se conservan los pasos y las dos notas que cambió la medición)

0. **Ventana.** Avisar: entre el paso 2 y el 5 la API está caída o sirve contra un esquema viejo.
1. **Inventario, no respaldo.** Correr las dos mediciones de arriba y dejar los números acá antes de la
   purga. Sin esto, la destrucción no tiene testigo. (Opción conservadora si cambia el humor: un branch
   de Neon se toma en segundos y no gasta disco local — pero el owner decidió que no hace falta.)
2. **Purga relacional — las once tablas de arriba, en una sola transacción, con `user_stories` adentro.
   Este es el alcance que eligió el owner, y es más destructivo de lo que `0028` necesita.**
   `TRUNCATE TABLE users, user_accounts, workspaces, workspace_members, projects, user_stories,
   extractions, tasks, workspace_llm_configs, workspace_prompts, custom_providers RESTART IDENTITY
   CASCADE;` — el `CASCADE` es lo que hace que una sola sentencia alcance para todo: los FK de
   `tasks` y `extractions` hacia `user_stories` son `ON DELETE CASCADE` (medido en `models/task.py:24`
   y `models/extraction.py:37`), y borrar `user_stories` se lleva los 42 tasks y las 17 extracciones por
   arrastre. Confirmar contando: **las once tablas en 0 y `alembic_version` todavía `0027`.**
   Con `user_stories` adentro, el paso 3 desaparece: no quedan historias que mientan sobre su estado.
2b. **Purga vectorial — las tres colecciones, decisión del owner.** Vaciar `storico_extractions_prod`
   (1), `storico_extractions_dev` (1) y `storico_extractions` (19): 21 puntos fuera. Elegido "slate
   limpio", no sólo lo de producción: las otras dos son justamente la contaminación entre entornos que
   se documentó más abajo.
   Mecanismo: `POST /collections/{name}/points/delete` con `"filter": {}` y `?wait=true`.
   **Medido acá: la clave de `.env.prod.local` es de lectura** (`/collections` responde, y el `count(*)`
   de Postgres también); si el borrado da 403 hay que usar la clave de admin del cluster.
3. **El estado desnormalizado ya no es una decisión.** Con `user_stories` en la purga, no queda ninguna
   historia cuyo `status` diga `extracted` sobre cero extracciones. Si algún día se purga sólo el par,
   este punto vuelve: `user_stories.status` lo reescribe `extraction_repository` en cada run, y habría
   que decidir `UPDATE user_stories SET status = 'pending_extraction'` o convivir con la mentira.
4. **Mergear.** Recién con el par vacío: el merge a `main` dispara `deploy-backend.yml`, que corre
   `alembic upgrade head` y `0028` pasa la guarda. El orden es **purgar y después mergear**, nunca al
   revés: mergear primero deja el deploy fallando en cada push hasta que alguien purgue.
   El owner dejó explícitamente el merge afuera de esta autorización.
5. **Comprobación después del merge.** `alembic_version` = `0028`, `task_invalidations` existe, las once
   tablas siguen en 0, y las tres colecciones siguen en 0 puntos — **no"siguen ahí con sus puntos":
   esa frase de la versión anterior de este runbook era falsa con el alcance nuevo.** El few-shot no
   tiene de dónde sacar ejemplos hasta que haya runs nuevos, y `few_shot_enabled` va a quedar en `true`
   sobre una base vacía: no rompe, devuelve vacío, pero hay que saberlo.

Lo que **no** hace este runbook: no toca `alembic_version`, no re-escribe la historia de la feature, y no
borra el `.env` de la VM — `STORICO_ENCRYPTION_KEY` sigue siendo la única forma de desencriptar claves
que ya no existen, y `STORICO_GOOGLE_API_KEY` sigue ahí para el embedding.
los 17 runs quedan registrados solo en el inventario de arriba.

## Hallazgo del inventario: dev escribe contra el cluster de producción

Medido el 2026-09-30 al contar las colecciones. `storico_extractions_dev` existe con 1 punto y **no
existía el 2026-09-28**. La razón no es un bug del adaptador: el `.env` de desarrollo de esta máquina
apunta `STORICO_QDRANT_URL` al **mismo cluster** que producción, y lo único que separa un entorno del
otro es el nombre de colección (`_dev` vs `_prod`). Con una sola variable mal escrita —o sin escribirla,
cayendo al default `storico_extractions` del adaptador, que es lo que explican los 19 puntos de esa
colección legado— una corrida de desarrollo escribe en el clúster de producción.

Esto no rompe nada hoy, pero acota el sentido de "una colección por entorno" que documenta
`docs/deployment.md`: hay separación lógica, no física. Mientras el plan de aislamiento siga siendo ese,
la purga vectorial tiene que nombrar las tres colecciones explícitamente, no "la de producción".

🔲 **Pendiente (decisión de diseño, no de esta purga):** si los entornos tienen que estar separados de
verdad, o se usa un cluster/API key distinto para dev, o se documenta que la separación es sólo de
nombre y se controla por ahí.

## Corrección a un "hallazgo" que no era hallazgo: el `provider = 'Nan'` es legítimo

La versión anterior de esta sección afirmaba que alguien había guardado un `NaN` stringificado, y
abría un pendiente de validación. **Estaba mal.** Medido después, contra la tabla que define el valor:
`custom_providers` tiene **una** fila, su `name` mide 3 caracteres y su `md5()` es idéntico al de
`'Nan'`, y **exactamente una** fila de `workspace_llm_configs` referencia ese nombre (`provider =
cp.name`). No hay `psql` ni Docker acá, pero sí hay lectura: la fila trae `api_key` cifrada (123
 caracteres de ciphertext Fernet), `temperature = 0.1` y `max_tokens = 2048`.

O sea que `'Nan'` es un **proveedor personalizado creado a propósito** — `custom_providers` es una
feature desde la revisión `0021`, su `name` es texto libre y lo único que se rechaza son los nombres
reservados (`_reject_reserved_provider_name`, `api/routes/workspace_settings.py:264`). Es el proveedor al
que caen los 2 runs con `model_used = qwen3.8-flash`, y su `base_url` apunta a `api.nan.builders`: una
gateway propia sirviendo un modelo que no es de ningún built-in. Eso lo explica todo; los otros 15 runs
usan proveedores built-in.

**Lección, porque es la segunda vez en dos días que acuso un dato de producción sin leer la tabla que lo
define** (la primera fue "la temperatura es recuperable", que salió de medir la existencia de la clave
JSON y no su valor). Un `String(50)` que acepta cualquier cosa no es prueba de que nadie lo validó:
puede ser que no haya nada que validar.

🔲 **Lo único real que queda acá, y es chico:** `workspace_llm_configs.provider` es un string plano, sin
FK a `custom_providers`. Borrar una fila de `custom_providers` deja configs nombrándola sin que nada
proteste. Hoy no pasa nada con 1 proveedor y 4 configs; hay que mirarlo el día que se borre uno.
