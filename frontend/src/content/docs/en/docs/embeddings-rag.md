---
title: Historical context
description: Where the examples in an extraction prompt come from, the three per-workspace settings, and what happens when the vector store is unreachable.
---

## Where the examples come from

When a run completes, the server writes it to a vector database (Qdrant) as a point that pairs an embedding of the user story with a summary of the tasks that run produced. When you extract a story, the server embeds the story text and searches the points of the same workspace for the most similar past extractions. The best matches are injected into the prompt as **few-shot examples**: complete past cases of "this user story produced these tasks".

A search is scoped to the workspace and carries three unconditional rules: it never reads another workspace's points, it never returns a past extraction whose tasks include one marked invalid, and it never returns the story's own previous runs as examples for itself.

The invalid-task rule is written as a **requirement that the point's validity flag be `false`**, not as a prohibition on `true`. The practical difference is what happens to a point that does not carry the flag at all: a positive requirement does not match it, so an old point whose validity is unknown is left out of the examples rather than assumed good.

## The three settings

Few-shot retrieval is configured per workspace, and it is **on by default**:

| Setting | Default | What it controls |
| --- | --- | --- |
| Few-shot enabled | on | Whether retrieval runs at all |
| Few-shot limit | 3 | How many examples the search may return |
| Few-shot threshold | 0.85 | The minimum similarity score for a point to count |

The threshold is applied by the vector store itself: a point only comes back if its similarity to the story being extracted is at least 0.85 (or whatever the workspace set). An example in the prompt is a past extraction's user story text followed by its tasks; when a run's judge score existed, it is shown next to the example.

## Where the points live

Each environment uses its own collection, because vectors from different embedding models are not comparable. The collection name comes from the `STORICO_QDRANT_COLLECTION` setting and defaults to `storico_extractions`; the value each deployment actually uses is part of that environment's configuration. The configured vector dimensions must match the embedding model that fills the collection, or the adapter refuses to start rather than store vectors that cannot be searched.

Besides the vector, a stored point carries the story text, the task summary, the model used, the run's version number, the workspace, project and story ids, a validity flag, the run's optional judge score, and the creation date.

A point's **id is the extraction's id**. That is what makes invalidation work without a search: marking a task invalid flips the validity flag on exactly the point that produced it, by id. Deleting a story removes its points the same way.

## When the vector store is unreachable

Retrieval and storage are both best-effort during an extraction, and neither can fail it:

- If the embedding service cannot be reached, the embedding comes back empty, the search returns nothing, and the extraction proceeds without examples.
- If Qdrant cannot be reached, the search returns nothing, and the extraction proceeds without examples.
- Storing a finished run's point can also fail silently: the failure is logged, and the extraction — already saved in the database — stays successful.

In other words, an extraction still succeeds with no examples when the vector store is unavailable. The only cost is context: the prompt is rendered without the few-shot examples section until the store is back.

The same tolerance does **not** extend to the operations that keep the two stores consistent. Marking or revoking an invalidation, and deleting a story, must update or delete points; if Qdrant is configured but unreachable, those operations are refused with HTTP 503 and `VECTOR_STORE_UNAVAILABLE` instead of leaving the database and the vector store disagreeing about what is valid.

## What this feature does not do

The web app never asks for automatic validation of an extraction: no LLM-as-a-Judge pass runs, and no confidence score is produced for runs started from the app.
