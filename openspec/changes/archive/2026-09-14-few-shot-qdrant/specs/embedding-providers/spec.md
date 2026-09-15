# embedding-providers Specification

> **Change**: `few-shot-qdrant`

## ADDED Requirements

### Requirement: Embedding provider abstraction

An `EmbeddingPort` selects Ollama, Google, or OpenAI by setting.

#### Scenario: Factory selects by provider

- **WHEN** `STORICO_EMBEDDING_PROVIDER=google`
- **THEN** a Google adapter is returned with `dimensions == 768`

#### Scenario: Unknown provider rejected

- **WHEN** an unknown provider is configured
- **THEN** the factory raises `ValueError`

### Requirement: Cloud adapters emit 768d

Google and OpenAI adapters request 768 output dimensions.

#### Scenario: Google 768d

- **WHEN** `embed()` runs on the Google adapter
- **THEN** a 768-length vector is returned

#### Scenario: OpenAI 768d

- **WHEN** `embed()` runs on the OpenAI adapter
- **THEN** a 768-length vector is returned

### Requirement: Embedding failures degrade gracefully

An embedding failure yields no vector without failing extraction.

#### Scenario: API failure returns empty

- **WHEN** the embedding API errors
- **THEN** `embed()` returns an empty list
