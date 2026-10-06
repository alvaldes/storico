---
title: Extraction versions
description: What an extraction version is, how to revisit one, and what happens to a version when a new one replaces it.
---

## What a version is

Every time you extract a story, the run becomes a **version** of that story. Versions are numbered per story, and every task belongs to the run that produced it: tasks cannot be created or deleted by hand, and a task is only removed together with its story.

## Reading a story's versions

The story detail shows a version selector that lists every run, newest first. Each entry names the version number, the model used, and the date; failed runs are listed too. The most recent completed run is the **current** version. Selecting a version shows that version's own tasks, not the current version's.

## What happens when a version is superseded

When a newer run completes, the old version's tasks stay viewable through the selector, but the version becomes **frozen**. A story with no completed run has no current version either, so its tasks are frozen too. On a frozen version you cannot:

- edit a task's dependencies,
- mark a task as invalid,
- revoke an invalidation mark.

Any of these is refused with HTTP 409 and the error code `TASK_VERSION_FROZEN`. A task's state and labels stay editable in every version.

## Invalidations

Marking a task **invalid** requires a reason and records which user marked it and when. Only the workspace owner or an admin can mark a task invalid or revoke a mark.

- A reason is mandatory.
- A task carries at most one active mark; marking it again is refused with HTTP 409 and the error code `TASK_ALREADY_MARKED`.
- Revoking a mark does not delete anything: the mark's history — its reason, who marked it, who revoked it, and when — is preserved.

You can read a task's full mark history, and the story page shows the active mark of each of its tasks at a glance.
