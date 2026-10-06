---
title: Quickstart
description: Install Storico, create the schema, start both halves, and configure a model before your first extraction.
---

## What you need

- **Python 3.12** for the backend;
- **Node.js 20+ and pnpm 10** for the frontend — pnpm is the only package manager this repository uses;
- **PostgreSQL**, where every story, task and workspace lives;
- **A model to extract with** — a local Ollama, or an API key for OpenAI, Anthropic or Gemini.

Qdrant is optional in the sense that an extraction still succeeds without it: it only supplies the few-shot examples described under [Historical context](/en/docs/embeddings-rag).

## 1. Install the backend

The repository does not mandate an environment manager; it needs one with the `dev` extra installed, the same way CI installs it. The project's own canonical choice is a conda environment named `storico`:

```bash
cd backend
python -m pip install -e ".[dev]"
```

## 2. Configure the environment

Copy `.env.example` to `.env`. The settings that matter before anything else:

| Variable | Default | What it does |
| --- | --- | --- |
| `STORICO_DATABASE_URL` | `postgresql+asyncpg://storico:storico@localhost:5432/storico` | Where the relational data lives |
| `STORICO_ENCRYPTION_KEY` | none | **Required to store workspace credentials.** Without it, saving an API key fails |
| `STORICO_QDRANT_URL` | `http://localhost:6333` | The vector store, for historical context |
| `STORICO_QDRANT_COLLECTION` | `storico_extractions` | The collection holding the extraction vectors. A collection belongs to the embedding model that fills it, so each environment sets its own value |
| `STORICO_OLLAMA_HOST` | `http://localhost:11434` | The Ollama host the default provider calls |
| `STORICO_AUTH_JWT_SECRET` | a development placeholder | Verifies the JWTs the frontend proxy issues. Replace it outside development |
| `STORICO_AUTH_ALLOWED_ORIGINS` | `http://localhost:4321` | Comma-separated CORS origins |

The embedding settings (`STORICO_EMBEDDING_PROVIDER`, `STORICO_EMBEDDING_MODEL`, `STORICO_EMBEDDING_DIMENSIONS`, and the per-provider models and API keys) determine the vectors. The dimensions must match the embedding model and the collection, because vectors from different models are not comparable.

## 3. Create the schema

Migrations are not applied for you, by any launcher in this repository. From `backend/`, with the environment active and `STORICO_DATABASE_URL` pointing at your database:

```bash
alembic upgrade head
```

## 4. Start the API

```bash
python -m uvicorn storico.api.app:create_app --factory --port 8000
```

The `--factory` flag is not optional. Without it, uvicorn takes `create_app` itself as the ASGI application and starts a broken server instead of failing; with it, a failure inside the factory stops the process with the real error.

`GET /api/v1/health` should answer `ok`. The interactive OpenAPI page is at `/docs` on the API, and every endpoint is also listed in the [API reference](/en/docs/api-reference).

## 5. Start the frontend

```bash
cd frontend
pnpm install
pnpm run dev
```

The app is at **http://localhost:4321**. The documentation you are reading is served by the same project, at `/en/docs` and `/es/docs`.

## 6. Configure a model before extracting

This is the step that blocks the first extraction, so it is worth doing before anything else:

1. **Sign in.** Authentication is OAuth only — Google or GitHub. There are no passwords.
2. **Create a workspace** if you do not have one. Any authenticated user can, and the creator becomes its owner and an admin.
3. **Open Settings and save the LLM configuration**: a provider and a model, plus an API key for the cloud providers. For Ollama, pull a model first (`ollama pull llama3.2`) and make sure the host in `STORICO_OLLAMA_HOST` is reachable. See [LLM providers](/en/docs/llm-providers) for the field-by-field detail.

:::caution
Extraction needs a saved model and provider configuration. Until a workspace has one, **task extraction
cannot start**: the API refuses with `LLM_CONFIG_INCOMPLETE` and the story page lists what is still
undefined instead of generating tasks. An unconfigured workspace resolves to Ollama, so the missing
field is usually the model.
:::

## 7. Extract your first story

Create a project, add a story in the [standard format](/en/docs/story-format), and start the extraction. It runs asynchronously: the request answers immediately and the story page reports progress. The tasks it produces start in **Backlog** on the [Kanban board](/en/docs/kanban).

If there are several stories, [import them from a CSV](/en/docs/story-import) instead of typing each one.

## When something does not work

| Symptom | Likely cause |
| --- | --- |
| `LLM_CONFIG_INCOMPLETE` | The workspace has no model, or a cloud provider has no API key |
| `LLM_CONNECTION_ERROR`, `LLM_RESPONSE_ERROR` | The provider host is unreachable or refused the request. An API key that is wrong or empty looks like this |
| The extraction succeeds with fewer examples, or none | Qdrant or the embedding service is unreachable. This never fails an extraction |
| The extraction times out | The model took too long to answer. A smaller model is the usual fix |

## Running everything with Docker Compose

The repository also carries a Compose file with four services — the API, Ollama, PostgreSQL and Qdrant. `make build` builds the images and `make up` starts them, with the API on port 8000.

The Compose stack **does not apply migrations**, so the schema has to be created once before the first request:

```bash
cd backend
alembic upgrade head
```

And because the database in that stack is the Compose container, the same value has to reach it — the Compose file sets `STORICO_DATABASE_URL` for the API container, but your shell needs its own.
