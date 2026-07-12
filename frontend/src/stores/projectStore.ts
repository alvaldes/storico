import { create } from 'zustand';
import type { Project, CreateProjectParams, UpdateProjectParams } from '@/types/project';
import * as api from '@/lib/projects-api';

interface ProjectState {
  projects: Project[];
  loading: boolean;
  saving: boolean;
  error: string | null;

  /** Fetch all projects from the API. */
  fetchProjects: () => Promise<void>;
  /** Create a new project. */
  createProject: (params: CreateProjectParams & { ownerId: string }) => Promise<Project>;
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
    set({ loading: true, error: null });
    try {
      const response = await api.listProjects(1, 100);
      set({ projects: response.items, loading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch projects';
      set({ error: message, loading: false });
    }
  },

  createProject: async (params) => {
    set({ saving: true, error: null });
    try {
      const project = await api.createProject(params);
      set((state) => ({ projects: [...state.projects, project], saving: false }));
      return project;
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to create project';
      set({ error: message, saving: false });
      throw err;
    }
  },

  updateProject: async (id, params) => {
    set({ saving: true, error: null });
    try {
      const updated = await api.updateProject(id, params);
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
    set({ saving: true, error: null });
    try {
      await api.deleteProject(id);
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
