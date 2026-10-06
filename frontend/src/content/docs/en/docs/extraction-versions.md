---
title: Extraction versions
description: What an extraction version is, how versions are numbered, how to revisit one, and what happens to a version when a new one replaces it.
---

## What a version is

Every time you extract a story, the run becomes a **version** of that story. Versions are numbered per story, and every task belongs to the run that produced it: tasks cannot be created or deleted by hand, and a task is only removed together with its story.

The number is allocated when the run **starts**, not when it finishes: the server takes the highest number the story already has, adds one, and writes the pending run under it. That is why the version selector can list a run that is still in flight or that failed — its number is already spent. Two runs started at the same instant can collide on the number; the server retries the allocation and, if every attempt loses the race, refuses the new run with HTTP 409 and `VERSION_ALLOCATION_CONFLICT`. Nothing was created in that case, so retrying is safe.

## Reading a story's versions

The story detail shows a version selector that lists every run, newest first. Each entry names the version number, the model used, and the date; failed runs are listed too. The most recent completed run is the **current** version. Selecting a version shows that version's own tasks, not the current version's.

`GET /api/v1/stories/{story_id}/versions` returns that list, ordered by version number descending, with two derived booleans per entry: `is_current` marks the first completed entry — a story with no completed run has no current entry at all — and `has_output` says whether the run produced tasks.

## What happens when a version is superseded

When a newer run completes, the old version's tasks stay viewable through the selector, but the version becomes **frozen**. A story with no completed run has no current version either, so its tasks are frozen too. On a frozen version you cannot:

- edit a task's dependencies,
- mark a task as invalid,
- revoke an invalidation mark.

Any of these is refused with HTTP 409 and the error code `TASK_VERSION_FROZEN`; the response names the story's current version number, or `null` when it has none. A task's state and labels stay editable in every version.

## Invalidations

Marking a task **invalid** requires a reason and records which user marked it and when. Only the workspace owner or an admin can mark a task invalid or revoke a mark. The reason must not be blank and is at most 500 characters; a blank or over-long one is refused at body validation with HTTP 422.

- A task carries at most one active mark; marking it again is refused with HTTP 409 and the error code `TASK_ALREADY_MARKED`, and the response carries the live mark's reason.
- Revoking a mark does not delete anything: the mark's history — its reason, who marked it, who revoked it, and when — is preserved.
- Revoking a task that has no active mark is refused with HTTP 404 and `ENTITY_NOT_FOUND`.
- Both operations update the story's stored vectors, so if Qdrant is configured but unreachable they are refused with HTTP 503 and `VECTOR_STORE_UNAVAILABLE`.

You can read a task's full mark history (`GET /api/v1/tasks/{task_id}/invalidations`, revoked marks included), and the story page shows the active mark of each of its tasks at a glance (`GET /api/v1/stories/{story_id}/invalidations`).

## Asking whether a mark repeats across versions

Because re-extracting a story produces a fresh set of tasks, the same problem can be marked invalid, fixed, and then marked invalid again in the next version without anyone noticing. `GET /api/v1/tasks/{task_id}/invalidations/repetition` answers exactly that: it looks for **active** marks on the story's *other* versions whose task title matches this task's title after normalization, and returns their version number, reason and date.

## Error codes

| Code | HTTP | Meaning |
| --- | --- | --- |
| `TASK_VERSION_FROZEN` | 409 | The task belongs to a superseded version |
| `TASK_ALREADY_MARKED` | 409 | The task already carries an active mark |
| `VERSION_ALLOCATION_CONFLICT` | 409 | The version number could not be minted; no run was created |
| `ENTITY_NOT_FOUND` | 404 | No such task, story or active mark |
| `VECTOR_STORE_UNAVAILABLE` | 503 | The vector store is configured but unreachable |
| `REQUEST_VALIDATION_FAILED` | 422 | The reason is blank, or longer than 500 characters |
