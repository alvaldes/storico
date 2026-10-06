---
title: Roles and permissions
description: The two workspace roles, who owns a workspace, and a per-operation table of who may do what.
---

## Two roles, and an owner that is not a role

A member of a workspace has exactly one of two roles: **admin** or **member**. Those are the only roles in the system — there is no system-level admin and no owner role. Ownership is a field on the workspace (the owner's user id), and the owner may hold either role.

## Who can create a workspace

Any authenticated user can create a workspace. The creator automatically becomes its owner and an admin member. No other permission is involved.

## Who may do what

| Operation | Who |
| --- | --- |
| Create a workspace | Any authenticated user, becoming its owner and an admin |
| Read, update or delete a workspace | Owner or admin |
| List members, add a member, change a member's role, remove a member | Owner or admin |
| Transfer ownership to another admin | **Owner only** |
| Read the LLM configuration, change it, edit prompts, manage custom providers, probe a provider's models | Admin |
| Read whether the workspace can extract, and which fields are missing | Any member — this is the one configuration read a plain member may call |
| Start an extraction | Owner or admin |
| Delete a story | Owner or admin |
| Mark a task invalid, or revoke an invalidation mark | Owner or admin |
| Create, list, update or delete projects | Any member |
| Create and edit user stories; read stories, their versions and their invalidation history | Any member |
| Import stories from a CSV | Any member |
| Check the status of a running extraction | Any member |
| Export the workspace's tasks | Any member |
| Read tasks and update them — their state and labels anywhere, their dependencies only on the current version | Any member |

Two footnotes to that table:

- **Starting an extraction mints a new version of the story**, so it is reserved to the owner or an admin. Deleting a user story takes the same gate, and so do the mutating ends of the invalidation history.
- **`POST /api/v1/llm/test` is not workspace-scoped.** It exists so a caller can test credentials before saving them, and it requires only an authenticated user; it does not check membership in any workspace. Every other LLM route here is scoped and gated.

## The protections around membership

- The owner's role cannot be changed: ownership has to be transferred first.
- The owner cannot be removed from the workspace.
- An admin cannot remove themselves while they are the workspace's last admin — the request is refused with HTTP 400 and `LAST_ADMIN_ERROR`.
- Adding a member always assigns the **member** role; becoming an admin is a role change, not an invite option.

## Operations that depend on another service

Some permission-gated operations can fail for a reason that has nothing to do with permissions: deleting a story, and marking or revoking an invalidation, must update the vector store. When Qdrant is configured but unreachable they are refused with HTTP 503 and `VECTOR_STORE_UNAVAILABLE`. See [Historical context](/en/docs/embeddings-rag).
