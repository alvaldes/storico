---
title: LLM providers
description: The LLM backends Storico supports and what each one needs.
---

## Supported LLM backends

- **Ollama** — LLaMA 3.2, Mistral, and other local models.
- **OpenAI** — GPT models (requires API key).
- **Anthropic** — Claude (requires API key).
- **Gemini** — Gemini 2.0 Flash (requires API key).

Ollama runs locally and needs no API key; the cloud providers require one. Whichever provider you choose, a model must be configured before you can extract tasks.

One caveat: when you extract from the web app, it never asks for automatic validation of the extraction — no LLM-as-a-Judge pass runs and no confidence score is produced. The capability exists in the engine; the app simply does not request it.
