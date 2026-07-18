import { create } from 'zustand';
import type { Task } from '@/types/task';
import * as api from '@/lib/tasks-api';

interface TaskState {
  tasks: Record<string, Task[]>;
  loading: boolean;
  extracting: boolean;
  error: string | null;

  fetchTasks: (storyId: string) => Promise<void>;
  extractTasks: (storyId: string, workspaceId: string) => Promise<void>;
  setTasks: (storyId: string, tasks: Task[]) => void;
  updateTask: (taskId: string, updates: Partial<Task>) => void;
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: {},
  loading: false,
  extracting: false,
  error: null,

  fetchTasks: async (storyId: string) => {
    set({ loading: true, error: null });
    try {
      const items = await api.listTasks(storyId);
      set((state) => ({
        tasks: { ...state.tasks, [storyId]: items },
        loading: false,
      }));
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tasks';
      set({ error: message, loading: false });
    }
  },

  extractTasks: async (storyId: string, workspaceId: string) => {
    set({ extracting: true, error: null });
    try {
      const result = await api.extractTasks(storyId, workspaceId);
      if (result.status === 'completed') {
        set((state) => ({
          tasks: { ...state.tasks, [storyId]: result.tasks },
          extracting: false,
        }));
      } else {
        set({
          error: result.errorInfo ?? 'Extraction failed',
          extracting: false,
        });
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Extraction failed';
      set({ error: message, extracting: false });
    }
  },

  setTasks: (storyId, tasks) =>
    set((state) => ({ tasks: { ...state.tasks, [storyId]: tasks } })),

  updateTask: (taskId, updates) =>
    set((state) => {
      const newTasks = { ...state.tasks };
      for (const storyId of Object.keys(newTasks)) {
        newTasks[storyId] = newTasks[storyId].map((t) =>
          t.id === taskId ? { ...t, ...updates } : t,
        );
      }
      return { tasks: newTasks };
    }),
}));
