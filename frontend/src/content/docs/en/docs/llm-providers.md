---
title: LLM providers
description: The backends Storico can extract with, the fields each one needs, custom providers, and how model lists are fetched.
---

Storico has **four first-class providers** — Ollama, OpenAI, Anthropic and Gemini — and **custom providers**: any other name a workspace registers for an endpoint that speaks the OpenAI dialect. Routing is by exact name, so a name outside the four is, by definition, a custom provider, and the OpenAI-compatible adapter is what calls it.

| Provider | API key | Models are listed from | Endpoint used when Base URL is empty |
| --- | --- | --- | --- |
| Ollama | not used | `/api/tags` | `http://localhost:11434` (the `STORICO_OLLAMA_HOST` setting) |
| OpenAI | required | `/models` | `https://api.openai.com/v1` |
| Anthropic | required | `/v1/models` | `https://api.anthropic.com` |
| Gemini | required | `/models`, keeping only the models that advertise `generateContent` | `https://generativelanguage.googleapis.com/v1beta` |
| Custom | optional | `/models`, then `/v1/models` if the first is empty | none — a custom provider needs its Base URL |

## The configuration fields

A workspace holds one LLM configuration. These are its fields, with the lengths the API enforces:

| Field | Type | Default | Notes |
| --- | --- | --- | --- |
| `provider` | string, up to 50 characters | `ollama` | Free text; the four names route to their adapters, anything else routes to the OpenAI-compatible one |
| `model` | string, up to 100 characters | unset | Required by every provider |
| `api_key` | string, up to 500 characters | unset | Required by OpenAI, Anthropic and Gemini; optional for Ollama and custom providers |
| `base_url` | string, up to 500 characters | unset (the Ollama host when the provider is Ollama) | Optional for the cloud providers, where it overrides the default endpoint; required by a custom provider |
| `temperature` | number | `0.1` | The settings form restricts it to 0–2 in steps of 0.1; the API itself accepts any number |
| `max_tokens` | integer | `2048` | The settings form restricts it to 256–8192 in steps of 256; the API itself accepts any integer |

Saving is a **partial merge**: the configuration endpoint updates only the fields present in the request, and a blank value is stored as unset, not as an empty string.

## Required fields

What a provider cannot be called without:

| Provider | Required |
| --- | --- |
| Ollama | `model` |
| OpenAI, Anthropic, Gemini | `model`, `api_key` |
| Custom | `model`, `base_url` — the API key stays optional, because a self-hosted gateway commonly accepts unauthenticated requests |

A value made only of whitespace counts as **unset**, so a form saved with blanks leaves the same gaps as one never filled. When a field is missing, extraction is refused with HTTP 400 and the error code `LLM_CONFIG_INCOMPLETE`, naming the missing fields; the story page shows which ones are undefined instead of starting a run.

`GET /api/v1/workspaces/{workspace_id}/settings/llm/status` answers the same question for any member of the workspace — a boolean, the effective provider, and the list of missing field names. It is the one settings route a plain member can read, and it never carries the key or the endpoint those fields hold.

## Custom providers

A custom provider is a **name registered per workspace**, for an endpoint that speaks the OpenAI dialect — a self-hosted gateway, a proxy, or a vendor the four built-ins do not cover.

- **The name** is free-form text of 1 to 50 characters once trimmed, saved exactly as typed: surrounding whitespace is ignored, casing is kept. Uniqueness is case-sensitive, so `Groq` and `groq` can coexist.
- **Refused names.** A built-in name in any casing is answered with HTTP 409 and `PROVIDER_NAME_BUILTIN`; the provider selector's own control value (`__add_custom_provider__`) is answered with HTTP 409 and `PROVIDER_NAME_RESERVED`; a name already registered in the workspace is answered with HTTP 409 and `PROVIDER_DUPLICATE_NAME`.
- **What a custom provider row stores.** Only its name. The Base URL, the API key and the model belong to the workspace's LLM configuration, so registering a provider makes it selectable but not yet callable: until the configuration has a model and a Base URL, extraction stays blocked by the same readiness rule as any other provider.
- **Operations.** A workspace can list its providers, create one (HTTP 201) and rename one. Renaming a provider that the saved configuration points at also repoints the configuration, so the selection does not break. There is no delete endpoint.

| Operation | Endpoint |
| --- | --- |
| List | `GET /api/v1/workspaces/{workspace_id}/settings/providers` |
| Create | `POST /api/v1/workspaces/{workspace_id}/settings/providers` |
| Rename | `PATCH /api/v1/workspaces/{workspace_id}/settings/providers/{provider_id}` |

## Finding a provider's models

`POST /api/v1/workspaces/{workspace_id}/settings/llm/models` proxies the provider's own model list and answers with an array of `{id, name}`. The body is optional and describes the selection in hand — provider, Base URL and API key — so the answer describes the provider just picked rather than the one already saved; a probe never borrows the saved credential for a different provider. With no body, the saved configuration is probed.

The answer is an **empty list**, not an error, when there is nothing to ask with:

- a cloud provider with no API key in the body;
- a custom provider with no Base URL;
- nothing saved at all and no provider in the body.

When the provider itself cannot be reached, the route answers HTTP 502 and `PROVIDER_MODELS_UNREACHABLE`.

`POST /api/v1/workspaces/{workspace_id}/settings/llm/test` is the sibling that tests a connection instead of listing models: it sends a minimal prompt (`Hello`) through the same adapter routing extraction uses and reports the result. When the connection fails, the response names the provider and a classified reason — an HTTP status, or the fact that the provider could not be reached — while the dependency's own error text goes to the log instead of the response. Both routes carry pending credentials in a body rather than a query string, so an API key never lands in an access log.

## Where the API key lives

An API key is encrypted before it is stored. Reading the workspace configuration requires the admin role, and that response returns the key as it was configured; the member-readable status endpoint above is deliberately narrow and never includes it. A key that cannot be decrypted is reported as such rather than silently treated as absent.

## Automatic validation does not run

One caveat that applies to every provider: when you extract from the web app, it never asks for automatic validation of the extraction — no LLM-as-a-Judge pass runs and no confidence score is produced. The capability exists in the engine; the app simply does not request it.

## Error codes

| Code | HTTP | Meaning |
| --- | --- | --- |
| `LLM_CONFIG_INCOMPLETE` | 400 | The workspace is missing a required field for its provider |
| `CUSTOM_PROVIDER_NOT_FOUND` | 404 | The provider id does not exist |
| `PROVIDER_NOT_IN_WORKSPACE` | 403 | The provider id belongs to another workspace |
| `PROVIDER_DUPLICATE_NAME` | 409 | A custom provider with that name already exists in the workspace |
| `PROVIDER_NAME_BUILTIN` | 409 | The name is one of the four built-in providers |
| `PROVIDER_NAME_RESERVED` | 409 | The name is reserved by the provider selector |
| `PROVIDER_MODELS_UNREACHABLE` | 502 | The provider could not be reached to list its models |
| `REQUEST_VALIDATION_FAILED` | 422 | A field breaks its declared type or length |
