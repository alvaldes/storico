import { create } from 'zustand';
import type { Project } from '@/types/project';
import type { CreateProjectParams, UpdateProjectParams } from '@/schemas';
import * as api from '@/lib/projects-api';
import { useWorkspaceStore } from '@/stores/workspaceStore';

interface ProjectState {
  projects: Project[];
  loading: boolean;
  saving: boolean;
  error: string | null;

  /** Fetch all projects for the current workspace. */
  fetchProjects: () => Promise<void>;
  /** Create a new project in the current workspace. */
  createProject: (params: CreateProjectParams) => Promise<Project>;
  /** Update an existing project. */
  updateProject: (id: string, params: UpdateProjectParams) => Promise<void>;
  /** Delete a project. */
  deleteProject: (id: string) => Promise<void>;
  /** Find a project by ID in the local cache. */
  getById: (id: string) => Project | undefined;
}

export const useProjectStore = create<ProjectState>((set, get) => ({
  projects: [],
  loading: false,
  saving: false,
  error: null,

  fetchProjects: async () => {
    const ws = useWorkspaceStore.getState().currentWorkspace;
    if (!ws) {
      set({ projects: [], loading: false });
      return;
    }
    set({ loading: true, error: null });
    try {
      const response = await api.listProjects(ws.id, 1, 100);
      set({ projects: response.items, loading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch projects';
      set({ error: message, loading: false });
    }
  },

  createProject: async (params) => {
    const ws = useWorkspaceStore.getState().currentWorkspace;
    if (!ws) throw new Error('No workspace selected');
    set({ saving: true, error: null });
    try {
      const project = await api.createProject(ws.id, params);
      set((state) => ({ projects: [...state.projects, project], saving: false }));
      return project;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create project';
      set({ error: message, saving: false });
      throw err;
    }
  },

  updateProject: async (id, params) => {
    const ws = useWorkspaceStore.getState().currentWorkspace;
    if (!ws) throw new Error('No workspace selected');
    set({ saving: true, error: null });
    try {
      const updated = await api.updateProject(ws.id, id, params);
      set((state) => ({
        projects: state.projects.map((p) => (p.id === id ? updated : p)),
        saving: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update project';
      set({ error: message, saving: false });
      throw err;
    }
  },

  deleteProject: async (id) => {
    const ws = useWorkspaceStore.getState().currentWorkspace;
    if (!ws) throw new Error('No workspace selected');
    set({ saving: true, error: null });
    try {
      await api.deleteProject(ws.id, id);
      set((state) => ({
        projects: state.projects.filter((p) => p.id !== id),
        saving: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to delete project';
      set({ error: message, saving: false });
      throw err;
    }
  },

  getById: (id) => get().projects.find((p) => p.id === id),
}));
