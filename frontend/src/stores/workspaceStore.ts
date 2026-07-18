import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Workspace } from '@/types/workspace';
import type { CreateWorkspaceParams, UpdateWorkspaceParams } from '@/schemas';
import * as api from '@/lib/workspace-api';
import { useProjectStore } from '@/stores/projectStore';

interface WorkspaceState {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  loading: boolean;
  saving: boolean;
  error: string | null;

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

export const useWorkspaceStore = create<WorkspaceState>()(
  persist(
    (set, get) => ({
      workspaces: [],
      currentWorkspace: null,
      loading: false,
      saving: false,
      error: null,

      fetchWorkspaces: async () => {
        set({ loading: true, error: null });
        try {
          const response = await api.listWorkspaces();
          const workspaces = response.workspaces;
          set((state) => {
            // Auto-select the first workspace if none is currently selected.
            // Hydrate from persisted workspace.id if the workspace still exists.
            const persisted = state.currentWorkspace;
            const match =
              persisted && workspaces.find((w) => w.id === persisted.id);
            return {
              workspaces,
      loading: true,
              currentWorkspace:
                match ?? (workspaces.length > 0 ? workspaces[0] : null),
            };
          });
          // Fetch projects for the (possibly auto-selected) workspace
          useProjectStore.getState().fetchProjects();
        } catch (err) {
          const message =
            err instanceof Error ? err.message : 'Failed to fetch workspaces';
          set({ error: message, loading: false });
        }
      },

      setCurrentWorkspace: (workspace) => {
        set({ currentWorkspace: workspace });
        useProjectStore.getState().fetchProjects();
      },

      createWorkspace: async (params) => {
        set({ saving: true, error: null });
        try {
          const workspace = await api.createWorkspace(params);
          set((state) => ({
            workspaces: [...state.workspaces, workspace],
            currentWorkspace: workspace,
            saving: false,
          }));
          useProjectStore.getState().fetchProjects();
          return workspace;
        } catch (err) {
          const message =
            err instanceof Error ? err.message : 'Failed to create workspace';
          set({ error: message, saving: false });
          throw err;
        }
      },

      updateWorkspace: async (id, params) => {
        set({ saving: true, error: null });
        try {
          const updated = await api.updateWorkspace(id, params);
          set((state) => {
            const workspaces = state.workspaces.map((w) =>
              w.id === id ? updated : w,
            );
            const currentWorkspace =
              state.currentWorkspace?.id === id
                ? updated
                : state.currentWorkspace;
            return { workspaces, currentWorkspace, saving: false };
          });
        } catch (err) {
          const message =
            err instanceof Error ? err.message : 'Failed to update workspace';
          set({ error: message, saving: false });
          throw err;
        }
      },

      deleteWorkspace: async (id) => {
        set({ saving: true, error: null });
        try {
          await api.deleteWorkspace(id);
          set((state) => {
            const workspaces = state.workspaces.filter((w) => w.id !== id);
            const currentWorkspace =
              state.currentWorkspace?.id === id
                ? workspaces.length > 0
                  ? workspaces[0]
                  : null
                : state.currentWorkspace;
            return { workspaces, currentWorkspace, saving: false };
          });
        } catch (err) {
          const message =
            err instanceof Error ? err.message : 'Failed to delete workspace';
          set({ error: message, saving: false });
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
