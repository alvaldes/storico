---
title: Proveedores de LLM
description: Los backends LLM que Storico soporta y lo que cada uno necesita.
---

## Backends LLM soportados

- **Ollama** — LLaMA 3.2, Mistral y otros modelos locales.
- **OpenAI** — modelos GPT (requiere API key).
- **Anthropic** — Claude (requiere API key).
- **Gemini** — Gemini 2.0 Flash (requiere API key).

Ollama corre localmente y no necesita API key; los proveedores en la nube sí. Con cualquier proveedor, se debe configurar un modelo antes de poder extraer tareas.

Una aclaración: al extraer desde la aplicación web, esta nunca pide la validación automática de la extracción —no se ejecuta ningún paso de LLM-as-a-Judge y no se produce ninguna puntuación de confianza—. La capacidad existe en el motor; la app simplemente no la solicita.
