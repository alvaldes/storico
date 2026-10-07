---
title: Versiones de extracción
description: Qué es una versión de extracción, cómo se numeran las versiones, cómo revisitarlas y qué le pasa a una versión cuando otra la reemplaza.
---

## Qué es una versión

Cada vez que extraes una historia, la ejecución se convierte en una **versión** de esa historia. Las versiones se numeran por historia, y cada tarea pertenece a la ejecución que la produjo: las tareas no se pueden crear ni eliminar a mano, y una tarea solo se elimina junto con su historia.

El número se asigna cuando la ejecución **empieza**, no cuando termina: el servidor toma el número más alto que la historia ya tiene, le suma uno y escribe la ejecución pendiente bajo ese número. Por eso el selector de versiones puede listar una ejecución en curso o fallida: su número ya está gastado. Dos ejecuciones iniciadas en el mismo instante pueden chocar en el número; el servidor reintenta la asignación y, si todos los intentos pierden la carrera, rechaza la ejecución nueva con HTTP 409 y `VERSION_ALLOCATION_CONFLICT`. En ese caso no se creó nada, así que reintentar es seguro.

## Leer las versiones de una historia

El detalle de la historia muestra un selector de versiones que enumera cada ejecución, de la más reciente a la más antigua. Cada entrada indica el número de versión, el modelo usado y la fecha; las ejecuciones fallidas también aparecen. La ejecución completada más reciente es la versión **actual**. Al seleccionar una versión se muestran las tareas de esa versión, no las de la actual.

`GET /api/v1/stories/{story_id}/versions` devuelve esa lista, ordenada por número de versión descendente, con dos booleanos derivados por entrada: `is_current` marca la primera entrada completada —una historia sin ninguna ejecución completada no tiene entrada actual— y `has_output` indica si la ejecución produjo tareas.

## Qué pasa cuando una versión es reemplazada

Cuando una ejecución más reciente se completa, las tareas de la versión anterior siguen visibles desde el selector, pero la versión queda **congelada**. Una historia sin ninguna ejecución completada tampoco tiene versión actual, así que sus tareas también quedan congeladas. En una versión congelada no puedes:

- editar las dependencias de una tarea,
- marcar una tarea como inválida,
- quitar una marca de invalidación.

Cualquiera de estas acciones se rechaza con HTTP 409 y el código de error `TASK_VERSION_FROZEN`; la respuesta indica el número de la versión actual de la historia, o `null` cuando no tiene ninguna. El estado y las etiquetas de una tarea siguen editables en todas las versiones.

## Invalidaciones

Marcar una tarea como **inválida** exige un motivo y registra qué usuario la marcó y cuándo. Solo el propietario del espacio de trabajo o un administrador puede marcar una tarea como inválida o quitar una marca. El motivo no puede estar en blanco y ocupa como máximo 500 caracteres; uno en blanco o demasiado largo se rechaza en la validación del cuerpo con HTTP 422.

- Una tarea lleva como máximo una marca activa; marcarla de nuevo se rechaza con HTTP 409 y el código de error `TASK_ALREADY_MARKED`, y la respuesta lleva el motivo de la marca vigente.
- Quitar una marca no elimina nada: el historial de la marca —su motivo, quién la marcó, quién la quitó y cuándo— se conserva.
- Quitar una marca a una tarea que no tiene ninguna activa se rechaza con HTTP 404 y `ENTITY_NOT_FOUND`.
- Ambas operaciones actualizan los vectores guardados de la historia, así que si Qdrant está configurado pero no es accesible se rechazan con HTTP 503 y `VECTOR_STORE_UNAVAILABLE`.

Puedes leer el historial completo de marcas de una tarea (`GET /api/v1/tasks/{task_id}/invalidations`, marcas quitadas incluidas), y la página de la historia muestra de un vistazo la marca activa de cada una de sus tareas (`GET /api/v1/stories/{story_id}/invalidations`).

## Preguntar si una marca se repite entre versiones

Como volver a extraer una historia produce un conjunto nuevo de tareas, el mismo problema puede marcarse como inválido, corregirse y volver a marcarse como inválido en la versión siguiente sin que nadie lo note. `GET /api/v1/tasks/{task_id}/invalidations/repetition` responde exactamente eso: busca marcas **activas** en las *otras* versiones de la historia cuyo título de tarea coincida con el de esta tarea después de normalizarlo, y devuelve su número de versión, su motivo y su fecha.

## Códigos de error

| Código | HTTP | Significado |
| --- | --- | --- |
| `TASK_VERSION_FROZEN` | 409 | La tarea pertenece a una versión reemplazada |
| `TASK_ALREADY_MARKED` | 409 | La tarea ya lleva una marca activa |
| `VERSION_ALLOCATION_CONFLICT` | 409 | No se pudo asignar el número de versión; no se creó ninguna ejecución |
| `ENTITY_NOT_FOUND` | 404 | No existe esa tarea, esa historia o esa marca activa |
| `VECTOR_STORE_UNAVAILABLE` | 503 | El almacén vectorial está configurado pero no es accesible |
| `REQUEST_VALIDATION_FAILED` | 422 | El motivo está en blanco o supera los 500 caracteres |
