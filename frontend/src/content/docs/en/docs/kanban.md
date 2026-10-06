---
title: Kanban board
description: The five task states, the moves the server allows, what else a task carries, and what dragging a card actually does.
---

## The five states

Every task sits in exactly one of five states, and the board shows them in flow order:

1. **Backlog**
2. **To Do**
3. **In Progress**
4. **Review**
5. **Done**

New tasks start in **Backlog**. Tasks are born from an extraction run — they cannot be created or deleted by hand, and a task is only removed together with its story. The two write routes that would do it answer with a refusal rather than a 404: `POST /api/v1/tasks/` returns HTTP 410 and `TASK_CREATION_ENDPOINT_REMOVED`, and `DELETE /api/v1/tasks/{task_id}` returns HTTP 410 and `TASK_DELETE_ENDPOINT_REMOVED`.

## The moves the server allows

The server enforces a state machine: a task can move one step forward, one step back for rework, and nothing else.

| From | Allowed moves |
| --- | --- |
| Backlog | To Do |
| To Do | Backlog, In Progress |
| In Progress | To Do, Review |
| Review | In Progress, Done |
| Done | — Done is terminal; a task there never moves again |

Saving a task without changing its state is never treated as a move, so an edit that echoes the current state is always accepted.

## When a move is invalid

Anything outside the table above is rejected with HTTP 400 and the error code `INVALID_STATE_TRANSITION`. The response names the current state, the attempted state, and the allowed transitions.

## What else a task carries

A task is more than its state. These are its other fields, and — importantly — which of them you can change afterwards:

| Field | Written by | Editable through the API |
| --- | --- | --- |
| `title` | The extraction | No |
| `description` | The extraction | No |
| `priority` | The extraction; `medium` when the model does not say otherwise | No |
| `status` | The extraction (`backlog`) | Yes, subject to the state machine above |
| `labels` | The extraction | Yes, in every version |
| `dependencies` | The extraction | Only while the task's version is the story's current one |

Only `status`, `labels` and `dependencies` are accepted by `PUT /api/v1/tasks/{task_id}`. A body carrying `title`, `description` or `priority` is refused with HTTP 422 and `REQUEST_VALIDATION_FAILED`, because the schema forbids unknown fields rather than ignoring them. To change a task's wording, re-extract the story and work with the new version.

`dependencies` is the privileged one: writing it on a task whose version has been superseded is refused with HTTP 409 and `TASK_VERSION_FROZEN` — see [Extraction versions](/en/docs/extraction-versions).

## Marking a task invalid

A task can be marked **invalid** instead of deleted. The mark needs a reason (mandatory, up to 500 characters, and it cannot be blank or only whitespace) and it records who marked it and when.

- Only the workspace owner or an admin may mark a task invalid or revoke a mark.
- A task carries at most one active mark; marking it again is refused with HTTP 409 and `TASK_ALREADY_MARKED`, and the response carries the live mark's reason.
- Revoking with no active mark is refused with HTTP 404 and `ENTITY_NOT_FOUND`.
- A task on a superseded version cannot be marked or revoked: HTTP 409 and `TASK_VERSION_FROZEN`.
- Marking and revoking change what the historical context may use as an example, so if Qdrant is configured but unreachable they are refused with HTTP 503 and `VECTOR_STORE_UNAVAILABLE` rather than leaving the two stores disagreeing.

## Ordering

Task lists are returned newest first: by creation time descending, and by id descending to break ties.

## What dragging a card does

When you drag a card to another column, the board moves it immediately, then sends `PUT /api/v1/tasks/{task_id}` with the new state to the server. If the server rejects the move, the card returns to its original column and a message lists the allowed destinations.

## Error codes

| Code | HTTP | Meaning |
| --- | --- | --- |
| `INVALID_STATE_TRANSITION` | 400 | The requested move is not in the table above |
| `TASK_VERSION_FROZEN` | 409 | The task belongs to a superseded version |
| `TASK_ALREADY_MARKED` | 409 | The task already carries an active invalidation mark |
| `TASK_CREATION_ENDPOINT_REMOVED` | 410 | Tasks cannot be created by hand |
| `TASK_DELETE_ENDPOINT_REMOVED` | 410 | Tasks cannot be deleted by hand |
| `VECTOR_STORE_UNAVAILABLE` | 503 | Marking or revoking needs the vector store, and it is unreachable |
| `REQUEST_VALIDATION_FAILED` | 422 | The body carries a field that is not writable, or a value that breaks its type |
