---
title: Versiones de extracción
description: Qué es una versión de extracción, cómo revisitarla y qué le pasa a una versión cuando otra la reemplaza.
---

## Qué es una versión

Cada vez que extraes una historia, la ejecución se convierte en una **versión** de esa historia. Las versiones se numeran por historia, y cada tarea pertenece a la ejecución que la produjo: las tareas no se pueden crear ni eliminar a mano, y una tarea solo se elimina junto con su historia.

## Leer las versiones de una historia

El detalle de la historia muestra un selector de versiones que enumera cada ejecución, de la más reciente a la más antigua. Cada entrada indica el número de versión, el modelo usado y la fecha; las ejecuciones fallidas también aparecen. La ejecución completada más reciente es la versión **actual**. Al seleccionar una versión se muestran las tareas de esa versión, no las de la actual.

## Qué pasa cuando una versión es reemplazada

Cuando una ejecución más reciente se completa, las tareas de la versión anterior siguen visibles desde el selector, pero la versión queda **congelada**. Una historia sin ninguna ejecución completada tampoco tiene versión actual, así que sus tareas también quedan congeladas. En una versión congelada no puedes:

- editar las dependencias de una tarea,
- marcar una tarea como inválida,
- quitar una marca de invalidación.

Cualquiera de estas acciones se rechaza con HTTP 409 y el código de error `TASK_VERSION_FROZEN`. El estado y las etiquetas de una tarea siguen editables en todas las versiones.

## Invalidaciones

Marcar una tarea como **inválida** exige un motivo y registra qué usuario la marcó y cuándo. Solo el propietario del espacio de trabajo o un administrador puede marcar una tarea como inválida o quitar una marca.

- El motivo es obligatorio.
- Una tarea lleva como máximo una marca activa; marcarla de nuevo se rechaza con HTTP 409 y el código de error `TASK_ALREADY_MARKED`.
- Quitar una marca no elimina nada: el historial de la marca —su motivo, quién la marcó, quién la quitó y cuándo— se conserva.

Puedes leer el historial completo de marcas de una tarea, y la página de la historia muestra de un vistazo la marca activa de cada una de sus tareas.
