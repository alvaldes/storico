# Deuda conocida y notas aceptadas

> Hechos y racionales de la deuda **aceptada**. Sin propuestas de fix: nada de lo que está acá vuelve a
> un archivo de TODO; el seguimiento ocurre fuera del repositorio.
> Última actualización: 2026-09-23

## Falso positivo de pyright en `users.py:101:34`

El diagnóstico real es `users.py:101:34`, sobre la llamada `OnboardingRequest()` en el endpoint
`PATCH /me/onboarding` (`backend/src/storico/api/routes/users.py`). La llamada es válida: los dos
campos de `OnboardingRequest` (los campos con default están en
`backend/src/storico/api/schemas/user.py:43-44`; la clase, en `:38`) tienen default (`None`),
así que construirla sin argumentos es correcto. El checker ve una firma stale del schema; no hay
ningún defecto de producción. Verificado el 2026-09-23 **sólo el lado del código**, leyendo ambos
archivos: la columna 34 cae exactamente sobre el constructor, y el modelo sigue teniendo sus dos
campos con default. **La emisión del diagnóstico no fue re-medida**: no hay pyright ni mypy
instalados en `backend/.venv`, así que lo verificado es que el código no tiene defecto, no que el
checker siga reportándolo.

**No se agregó ninguna supresión** (ni `# type: ignore` ni `cast`), a propósito: el defecto es del
checker, no del código, y una supresión enseñaría a los lectores del archivo que hay algo que esconder
cuando no lo hay. No hay mypy ni pyright configurados en el gate, así que la supresión no compraría
nada. La rama sólo-icono del onboarding (`users.py:126-129`), que en su momento estuvo sin cubrir, ya
tiene test.

## Diagnósticos de tipado preexistentes en `api/app.py`

Última medición registrada: **12 diagnósticos** de rigidez de overloads de FastAPI, con el probe LSP
de `pi-lens` a `severity=error` (medida durante el sweep de `schema-drift-gate`, 2026-09-21; antes de
esa medición el número que circulaba era 22 y era falso). **Re-medición en este retiro: no fue
posible** — el instrumento (`pi-lens`, probe LSP) no está disponible para este agente y no hay mypy ni
pyright instalados en `backend/.venv` que la repliquen. El 12 queda entonces como *último valor
medido*, con su instrumento nombrado para que el próximo lector lo re-derive, no como verdad actual.

No hay mypy ni pyright configurados y ninguno de esos diagnósticos está en el gate. Arreglarlos pide
`cast`s o `type: ignore`, o sea cambio de lógica o de señal: quedan reportados, no arreglados.

## Ruido heurístico de pi-lens en la capa de datos

Marca *Potential SQL injection sink* en cualquier `session.execute(...)` y
`Cannot access attribute "rowcount" for class "Result[Any]"`. Verificado uno por uno en su momento:
`workspaces.py:290` es una llamada a un *use case* con UUIDs (cero SQL, no hay statement), y los
repositorios pasan `select(...)` / `delete(...)` de SQLAlchemy construidos con `==`, o sea
parametrizados; `rowcount` sí existe en runtime (`CursorResult`), es un hueco de los stubs. El diff de
esos archivos en su día fue **puro rewrap** de `ruff format`: un formateador no puede crear un error
de SQL ni de tipos.

**Decisión explícita**: no re-investigar este ruido hasta que el backend tenga un type-check gate.
Hasta entonces no hay instrumento contra el cual distinguir señal de ruido, y "arreglarlo" pediría
`cast` / `type: ignore`, que es ruido, no seguridad.
