import type { Workspace } from '@/types/workspace';

/**
 * The client mirror of the backend's owner-or-admin gate (`_is_owner_or_admin`).
 *
 * The server remains the authority in every case: this predicate only decides
 * which controls are hidden or disabled as a courtesy. A refusal that reaches
 * the client anyway renders `WORKSPACE_OWNER_OR_ADMIN_REQUIRED`'s localized
 * copy, so hiding a control must never be load-bearing.
 *
 * One home on purpose: deriving "is owner or admin" inline in each of the four
 * components that need it is how the two mirrors drift apart.
 */
export function canManageVersions(
  workspace: Workspace | null | undefined,
  userId: string | undefined,
): boolean {
  return (
    !!workspace && !!userId && (workspace.role === 'admin' || workspace.ownerId === userId)
  );
}
