---
title: Kanban board
description: The five task states, the moves the server allows, and what dragging a card actually does.
---

## The five states

Every task sits in exactly one of five states, and the board shows them in flow order:

1. **Backlog**
2. **To Do**
3. **In Progress**
4. **Review**
5. **Done**

New tasks start in **Backlog**. Tasks are born from an extraction run — they cannot be created or deleted by hand, and a task is only removed together with its story.

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

## What dragging a card does

When you drag a card to another column, the board moves it immediately, then sends `PUT /api/v1/tasks/{task_id}` with the new state to the server. If the server rejects the move, the card returns to its original column and a message lists the allowed destinations.
