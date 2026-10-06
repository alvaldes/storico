---
title: Tablero Kanban
description: Los cinco estados de una tarea, los movimientos que el servidor permite, qué más lleva una tarea y qué hace realmente arrastrar una tarjeta.
---

## Los cinco estados

Cada tarea está en exactamente uno de cinco estados, y el tablero los muestra en orden de flujo:

1. **Pendiente**
2. **Por Hacer**
3. **En Progreso**
4. **Revisión**
5. **Terminado**

Las tareas nuevas empiezan en **Pendiente**. Las tareas nacen de una extracción: no se pueden crear ni eliminar a mano, y una tarea solo se elimina junto con su historia. Las dos rutas de escritura que lo harían responden con un rechazo en lugar de un 404: `POST /api/v1/tasks/` devuelve HTTP 410 y `TASK_CREATION_ENDPOINT_REMOVED`, y `DELETE /api/v1/tasks/{task_id}` devuelve HTTP 410 y `TASK_DELETE_ENDPOINT_REMOVED`.

## Los movimientos que el servidor permite

El servidor aplica una máquina de estados: una tarea puede avanzar un paso, retroceder un paso para rehacer trabajo, y nada más.

| Desde | Movimientos permitidos |
| --- | --- |
| Pendiente | Por Hacer |
| Por Hacer | Pendiente, En Progreso |
| En Progreso | Por Hacer, Revisión |
| Revisión | En Progreso, Terminado |
| Terminado | — Terminado es final; una tarea allí no vuelve a moverse |

Guardar una tarea sin cambiar su estado nunca cuenta como movimiento, así que una edición que repite el estado actual siempre se acepta.

## Cuando un movimiento es inválido

Todo lo que esté fuera de la tabla anterior se rechaza con HTTP 400 y el código de error `INVALID_STATE_TRANSITION`. La respuesta indica el estado actual, el estado intentado y los movimientos permitidos.

## Qué más lleva una tarea

Una tarea es más que su estado. Estos son sus otros campos y —esto importa— cuáles se pueden cambiar después:

| Campo | Lo escribe | Editable por la API |
| --- | --- | --- |
| `title` | La extracción | No |
| `description` | La extracción | No |
| `priority` | La extracción; `medium` cuando el modelo no dice otra cosa | No |
| `status` | La extracción (`backlog`) | Sí, sujeto a la máquina de estados de arriba |
| `labels` | La extracción | Sí, en todas las versiones |
| `dependencies` | La extracción | Solo mientras la versión de la tarea sea la actual de la historia |

`PUT /api/v1/tasks/{task_id}` acepta únicamente `status`, `labels` y `dependencies`. Un cuerpo que lleve `title`, `description` o `priority` se rechaza con HTTP 422 y `REQUEST_VALIDATION_FAILED`, porque el esquema prohíbe los campos desconocidos en lugar de ignorarlos. Para cambiar el texto de una tarea, vuelve a extraer la historia y trabaja con la versión nueva.

`dependencies` es la privilegiada: escribirla en una tarea cuya versión fue reemplazada se rechaza con HTTP 409 y `TASK_VERSION_FROZEN`. Consulta [Versiones de extracción](/es/docs/extraction-versions).

## Marcar una tarea como inválida

Una tarea se puede marcar como **inválida** en lugar de eliminarla. La marca exige un motivo (obligatorio, de hasta 500 caracteres, y no puede estar en blanco ni ser solo espacios) y registra qué usuario la marcó y cuándo.

- Solo el propietario del espacio de trabajo o un administrador puede marcar una tarea como inválida o quitar una marca.
- Una tarea lleva como máximo una marca activa; marcarla de nuevo se rechaza con HTTP 409 y `TASK_ALREADY_MARKED`, y la respuesta lleva el motivo de la marca vigente.
- Quitar una marca cuando no hay ninguna activa se rechaza con HTTP 404 y `ENTITY_NOT_FOUND`.
- Una tarea de una versión reemplazada no se puede marcar ni desmarcar: HTTP 409 y `TASK_VERSION_FROZEN`.
- Marcar y desmarcar cambian qué puede usar el contexto histórico como ejemplo, así que si Qdrant está configurado pero no es accesible, se rechazan con HTTP 503 y `VECTOR_STORE_UNAVAILABLE` en lugar de dejar los dos almacenes en desacuerdo.

## Orden

Las listas de tareas se devuelven de la más nueva a la más antigua: por fecha de creación descendente y, para romper empates, por identificador descendente.

## Qué hace arrastrar una tarjeta

Cuando arrastras una tarjeta a otra columna, el tablero la mueve de inmediato y después envía `PUT /api/v1/tasks/{task_id}` con el nuevo estado al servidor. Si el servidor rechaza el movimiento, la tarjeta regresa a su columna original y un aviso enumera los destinos permitidos.

## Códigos de error

| Código | HTTP | Significado |
| --- | --- | --- |
| `INVALID_STATE_TRANSITION` | 400 | El movimiento pedido no está en la tabla de arriba |
| `TASK_VERSION_FROZEN` | 409 | La tarea pertenece a una versión reemplazada |
| `TASK_ALREADY_MARKED` | 409 | La tarea ya lleva una marca de invalidación activa |
| `TASK_CREATION_ENDPOINT_REMOVED` | 410 | Las tareas no se pueden crear a mano |
| `TASK_DELETE_ENDPOINT_REMOVED` | 410 | Las tareas no se pueden eliminar a mano |
| `VECTOR_STORE_UNAVAILABLE` | 503 | Marcar o desmarcar necesita el almacén vectorial, y no es accesible |
| `REQUEST_VALIDATION_FAILED` | 422 | El cuerpo lleva un campo que no es escribible, o un valor que incumple su tipo |
