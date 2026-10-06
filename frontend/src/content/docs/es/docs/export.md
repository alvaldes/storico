---
title: Exportación
description: Descarga las tareas de tu espacio de trabajo como JSON o Markdown.
---

## Exportación a JSON y Markdown

Exporta tus tareas a JSON o Markdown con un clic. Compatible con tu flujo de trabajo existente.

Abre la página de exportación, selecciona un espacio de trabajo, elige **JSON** o **Markdown** y haz clic en **Descargar**. El backend devuelve el archivo como descarga: JSON como un arreglo de tareas y Markdown con una sección por historia. Un espacio de trabajo vacío descarga un arreglo JSON válido (`[]`) o un documento Markdown con solo el encabezado `# Tasks Export`.

Estos son los únicos dos formatos disponibles: CSV y XML no están soportados. Cualquier otro valor de formato se rechaza con HTTP 400 y el código de error `UNSUPPORTED_EXPORT_FORMAT`.

## El formato JSON

La exportación a JSON es un arreglo de objetos de tarea con formato legible (sangría de dos espacios), uno por tarea exportada, servido como `application/json`. Cada objeto lleva exactamente estos campos:

| Campo | Significado |
| --- | --- |
| `id` | El identificador de la tarea |
| `user_story_id` | La historia a la que pertenece la tarea |
| `title` | El título de la tarea |
| `description` | La descripción de la tarea |
| `status` | El estado Kanban de la tarea |
| `priority` | La prioridad de la tarea |
| `labels` | Las etiquetas de la tarea |
| `dependencies` | Las dependencias de la tarea |
| `created_at` | Cuándo se creó la tarea |
| `updated_at` | Cuándo se actualizó la tarea por última vez |

## El formato Markdown

La exportación a Markdown, servida como `text/markdown`, empieza con un encabezado `# Tasks Export` y tiene una sección `## {story}` por historia, donde `{story}` es el texto original de la historia —o `Untitled story` cuando no tiene—. Dentro de cada sección, cada tarea es una viñeta con la forma `- **{title}** — {description}`, con las etiquetas de la tarea añadidas como marcadores `#label` y sus dependencias añadidas como `→ {resolved title}`. Una dependencia se resuelve al título de la tarea referenciada y vuelve a la referencia original cuando ningún título coincide.

## La descarga

La respuesta lleva un encabezado `Content-Disposition: attachment`, así que el navegador descarga el archivo en lugar de mostrarlo: `tasks-export-{workspace_id}.json` para JSON y `tasks-export-{workspace_id}.md` para Markdown.

## Qué se exporta

Solo se exportan las tareas que pertenecen a una ejecución de extracción **completada**: una ejecución que sigue pendiente, o que falló, no aporta nada al archivo. De las ejecuciones completadas de una historia se incluye solo la de número más alto —su versión **actual**, la que el selector de versiones de la página de la historia marca como actual—. Las tareas producidas por versiones reemplazadas nunca llegan al archivo. El export toma siempre la versión actual: elegir otra en la página de la historia no cambia lo que contiene el export de un espacio de trabajo.
