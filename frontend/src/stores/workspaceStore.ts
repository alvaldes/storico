import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Workspace } from '@/types/workspace';
import type { CreateWorkspaceParams, UpdateWorkspaceParams } from '@/schemas';
import * as api from '@/lib/workspace-api';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useTaskStore } from '@/stores/taskStore';
import { createInflightTracker } from '@/stores/_inflight';

// Dedupe of inflight fetchWorkspaces calls. Astro View Transitions may remount
// the sidebar while a prior fetch is still inflight; without this, two
// /workspaces requests fire in parallel. Slot is freed on settle so explicit
// refresh (OnboardingModal after rename, MemberManagement after member changes)
// still issues a fresh request.
const workspacesInflight = createInflightTracker<string>();

interface WorkspaceState {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  loading: boolean;
  saving: boolean;

  /** Fetch all workspaces the current user belongs to. Auto-selects the first one if none selected. */
  fetchWorkspaces: () => Promise<void>;
  /** Set the current workspace and fetch its projects. */
  setCurrentWorkspace: (workspace: Workspace) => void;
  /** Create a new workspace and set it as current. */
  createWorkspace: (params: CreateWorkspaceParams) => Promise<Workspace>;
  /** Update an existing workspace. */
  updateWorkspace: (id: string, params: UpdateWorkspaceParams) => Promise<void>;
  /** Delete a workspace. Resets currentWorkspace if deleted. */
  deleteWorkspace: (id: string) => Promise<void>;
  /** Find a workspace by ID in the local cache. */
  getById: (id: string) => Workspace | undefined;
}

type WorkspaceSetter = (partial: Partial<WorkspaceState>) => void;

/**
 * Drop every workspace-scoped slice of the switching stores.
 *
 * `taskStore.tasks` (keyed by storyId) and `taskStore.allowedTransitions` (keyed by
 * taskId) are deliberately kept: both are refetched per story and clearing them would
 * blank an open story view mid-visit. `workspaceTasks` and `extractions` are
 * workspace-scoped and must never survive a switch, so they are dropped by
 * `taskStore.setScopeWorkspace`, which also moves the store's workspace scope and
 * thereby invalidates any inflight continuation from the workspace being left.
 */
function clearWorkspaceScopedState(workspaceId: string | null): void {
  useProjectStore.getState().reset();
  useStoryStore.getState().reset();
  useTaskStore.getState().setScopeWorkspace(workspaceId);
}

/**
 * Make `next` the current workspace and load its projects.
 * The single entry point for an actual workspace change: it clears the previous
 * workspace's slices before the new fetch resolves, so no stale data can leak.
 */
function switchWorkspace(set: WorkspaceSetter, next: Workspace | null): void {
  set({ currentWorkspace: next });
  clearWorkspaceScopedState(next?.id ?? null);
  useProjectStore.getState().fetchProjects();
}

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set, get) => ({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      saving: false,

      fetchWorkspaces: async () => {
        set({ loading: true });
        try {
          const response = await workspacesInflight.run('workspaces', () => api.listWorkspaces());
          const workspaces = response.workspaces;
          // Auto-select the first workspace if none is currently selected.
          // Hydrate from persisted workspace.id if the workspace still exists.
          const persisted = get().currentWorkspace;
          const match = persisted && workspaces.find((w) => w.id === persisted.id);
          const nextWorkspace = match ?? (workspaces.length > 0 ? workspaces[0] : null);
          set({ workspaces, loading: true, currentWorkspace: nextWorkspace });
          if ((nextWorkspace?.id ?? null) !== (persisted?.id ?? null)) {
            // Hydration landed on a different workspace: drop the previous one's slices.
            clearWorkspaceScopedState(nextWorkspace?.id ?? null);
          }
          // Fetch projects for the (possibly auto-selected) workspace. This is the
          // only projects request here — it dedupes on `projects:{wsId}` when the
          // id did not change.
          useProjectStore.getState().fetchProjects();
        } catch {
          // Deliberately silent, as it was before: this store recorded the failure in an `error`
          // field that no component ever read, so removing the field changes nothing the user
          // can see. `loading` is the only thing a surface observes here. Surfacing this
          // failure would be new behaviour, and it is recorded as a follow-up rather than
          // invented in a change whose subject is deleting a dead field.
          set({ loading: false });
        }
      },

      setCurrentWorkspace: (workspace) => {
        if (get().currentWorkspace?.id === workspace.id) {
          // Same workspace (e.g. a rename): refresh the cached metadata, never wipe data.
          set({ currentWorkspace: workspace });
          useProjectStore.getState().fetchProjects();
          return;
        }
        switchWorkspace(set, workspace);
      },

      createWorkspace: async (params) => {
        set({ saving: true });
        try {
          const workspace = await api.createWorkspace(params);
          set((state) => ({
            workspaces: [...state.workspaces, workspace],
            saving: false,
          }));
          switchWorkspace(set, workspace);
          return workspace;
        } catch (err) {
          set({ saving: false });
          throw err;
        }
      },

      updateWorkspace: async (id, params) => {
        set({ saving: true });
        try {
          const updated = await api.updateWorkspace(id, params);
          set((state) => {
            const workspaces = state.workspaces.map((w) => (w.id === id ? updated : w));
            const currentWorkspace =
              state.currentWorkspace?.id === id ? updated : state.currentWorkspace;
            return { workspaces, currentWorkspace, saving: false };
          });
        } catch (err) {
          set({ saving: false });
          throw err;
        }
      },

      deleteWorkspace: async (id) => {
        set({ saving: true });
        try {
          await api.deleteWorkspace(id);
          const wasCurrent = get().currentWorkspace?.id === id;
          const workspaces = get().workspaces.filter((w) => w.id !== id);
          set({ workspaces, saving: false });
          if (wasCurrent) {
            // Route the replacement through the same switch so projects are not stale.
            switchWorkspace(set, workspaces.length > 0 ? workspaces[0] : null);
          }
        } catch (err) {
          set({ saving: false });
          throw err;
        }
      },

      getById: (id) => get().workspaces.find((w) => w.id === id),
    }),
    {
      name: 'workspace-storage',
      // Only persist which workspace is selected — workspaces list is re-fetched
      partialize: (state) => ({
        currentWorkspace: state.currentWorkspace,
      }),
    },
  ),
);
