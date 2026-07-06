import { create } from 'zustand';
import type { Project } from '@/types/project';

interface ProjectState {
  projects: Project[];
  loading: boolean;
  error: string | null;
  setProjects: (projects: Project[]) => void;
  addProject: (project: Project) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  projects: [],
  loading: false,
  error: null,
  setProjects: (projects) => set({ projects }),
  addProject: (project) =>
    set((state) => ({ projects: [...state.projects, project] })),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));
