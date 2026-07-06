import { create } from 'zustand';
import type { Task } from '@/types/task';

interface TaskState {
  tasks: Record<string, Task[]>;
  loading: boolean;
  error: string | null;
  setTasks: (storyId: string, tasks: Task[]) => void;
  updateTask: (taskId: string, updates: Partial<Task>) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useTaskStore = create<TaskState>((set) => ({
  tasks: {},
  loading: false,
  error: null,
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
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));
