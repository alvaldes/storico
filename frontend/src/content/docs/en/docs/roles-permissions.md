---
title: Roles and permissions
description: The two workspace roles, who owns a workspace, and what each of them may do.
---

## Two roles, and an owner that is not a role

A member of a workspace has exactly one of two roles: **admin** or **member**. Those are the only roles in the system — there is no system-level admin and no owner role. Ownership is a field on the workspace (the owner's user id), and the owner may hold either role.

## Who can create a workspace

Any authenticated user can create a workspace. The creator automatically becomes its owner and an admin member. No other permission is involved.

## What admins may do

Only admins can:

- update or delete the workspace;
- manage its members: list them, add a user by email, change a member's role, and remove a member;
- read and change the workspace's LLM configuration, custom providers, and prompts, and probe which models a provider offers.

Two protections sit on top of member management: the owner's role cannot be changed (ownership must be transferred first), and the owner cannot be removed from the workspace.

## What only the owner may do

Transferring ownership of the workspace to another admin is the one owner-only operation.

## What requires the owner or an admin

Starting an extraction mints a new version of the story, so it is reserved to the workspace owner or an admin. The same gate applies to deleting a user story, and to marking a task invalid or revoking an invalidation mark — the mutating ends of the invalidation history.

## What every member may do

Plain members can work with content inside the workspace:

- create, list, update, and delete projects;
- create and edit user stories, and read stories, their versions, and their invalidation history;
- check the status of a running extraction;
- export the workspace's tasks;
- read tasks and update them (their state and their labels; dependencies only on the current version).

Deleting a story is the exception: it needs the owner or an admin, like starting an extraction.
