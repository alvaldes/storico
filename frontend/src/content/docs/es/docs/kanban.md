---
title: Tablero Kanban
description: Los cinco estados de una tarea, los movimientos que el servidor permite y qué hace realmente arrastrar una tarjeta.
---

## Los cinco estados

Cada tarea está en exactamente uno de cinco estados, y el tablero los muestra en orden de flujo:

1. **Pendiente**
2. **Por Hacer**
3. **En Progreso**
4. **Revisión**
5. **Terminado**

Las tareas nuevas empiezan en **Pendiente**. Las tareas nacen de una extracción: no se pueden crear ni eliminar a mano, y una tarea solo se elimina junto con su historia.

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

## Qué hace arrastrar una tarjeta

Cuando arrastras una tarjeta a otra columna, el tablero la mueve de inmediato y después envía `PUT /api/v1/tasks/{task_id}` con el nuevo estado al servidor. Si el servidor rechaza el movimiento, la tarjeta regresa a su columna original y un aviso enumera los destinos permitidos.
