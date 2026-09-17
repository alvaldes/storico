/**
 * The single authority for "which workspace do the workspace-scoped store slices
 * belong to".
 *
 * `workspaceStore` imports `projectStore`, `storyStore` and `taskStore`, so none of them
 * can import `workspaceStore` back to ask it what the current workspace is without
 * creating a real import cycle. This module holds that one fact instead: the stores read
 * it, and it reads no store, so it can never take part in a cycle.
 *
 * The fact lives here rather than duplicated inside a store so that every guard reads the
 * same value: a store that kept its own copy could disagree with the switch that moved it.
 */

/**
 * Invariant: the pair ("observed", `scopedWorkspaceId`) is the workspace that
 * `taskStore.workspaceTasks`, `taskStore.extractions`, `projectStore.projects` and
 * `storyStore.stories` belong to.
 *
 * While no switch has been observed the scope is unknown, so `isScopedWorkspace` is fail-open
 * and `getScopedWorkspaceId()` reports `undefined`: callers and tests that never switch a
 * workspace keep the behavior they had before this guard existed. Only `resetScopedWorkspace`
 * returns to that state.
 *
 * A real switch observes the scope and it never lapses on its own: `scopedWorkspaceId` is then
 * the new workspace id, or `null` when no workspace remains. An observed `null` is a real
 * observation that denies every id, because the two states are different facts — "nothing was
 * ever switched" is not "the workspace was switched away from". That distinction is what lets
 * a continuation started before the switch always tell that it was discarded, including when
 * the switch landed on "no workspace" and the id it compares against is the one that vanished.
 */
let scopeObserved = false;
let scopedWorkspaceId: string | null = null;

/** Observe `workspaceId` as the workspace the scoped slices belong to. Called by the switch itself. */
export function setScopedWorkspaceId(id: string | null): void {
  scopeObserved = true;
  scopedWorkspaceId = id;
}

/**
 * The observed workspace: its id, `null` for an observed "no workspace remains", or
 * `undefined` when no switch has been observed yet.
 */
export function getScopedWorkspaceId(): string | null | undefined {
  return scopeObserved ? scopedWorkspaceId : undefined;
}

/**
 * Whether a workspace-scoped write for `id` still applies to the store.
 *
 * Fail-open only while no switch has been observed: every id is accepted, so code paths and
 * tests that never switch keep their existing behavior. Once observed, only a non-null `id`
 * that equals the observed workspace is accepted, so an observed `null` denies every id.
 */
export function isScopedWorkspace(id: string | null | undefined): boolean {
  if (!scopeObserved) return true;
  return scopedWorkspaceId !== null && id === scopedWorkspaceId;
}

/** Return to the unobserved state. Only tests and a full reset of the scoped slices need this. */
export function resetScopedWorkspace(): void {
  scopeObserved = false;
  scopedWorkspaceId = null;
}
