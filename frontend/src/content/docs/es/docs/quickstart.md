---
title: Inicio rápido
description: Configura Storico y extrae tus primeras tareas a partir de una historia de usuario.
---

## Primeros pasos

1. **Ejecuta Storico localmente** — clona el repositorio y sigue la guía de instalación en el README.
2. **Configura tu LLM** — elige entre Ollama (local), OpenAI, Anthropic o Gemini. Ollama no necesita API key, pero todos los proveedores necesitan un modelo.
3. **Crea un proyecto** — organiza tus historias de usuario en proyectos.
4. **Pega una historia de usuario** — usa el formato estándar "As a… I want… so that…".
5. **Extrae tareas** — deja que la IA descomponga tu historia en tareas estructuradas.
6. **Revisa y exporta** — edita las tareas según sea necesario y expórtalas a JSON o Markdown.

:::caution
La extracción necesita un modelo y una configuración del proveedor guardados. Hasta que un espacio de
trabajo los tenga, **la extracción no puede comenzar**, y la página de la historia indica qué falta por
definir en lugar de generar tareas.
:::

Para el formato exacto que Storico espera, consulta [Formato de historia de usuario](/es/docs/story-format).
