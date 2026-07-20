import { create } from 'zustand';
import type { Task } from '@/types/task';
import * as api from '@/lib/tasks-api';

// ── Types ──

export type ExtractionStatus = 'idle' | 'pending' | 'completed' | 'failed';
export type ExtractionErrorCode = 'unauthorized' | 'network' | 'server' | null;

export interface ExtractionState {
  extractionId: string | null;
  status: ExtractionStatus;
  error: string | null;
  /** Categorized failure cause so consumers can react specifically (e.g. 401 → re-auth). */
  errorCode: ExtractionErrorCode;
}

// ── Store ──

interface TaskState {
  tasks: Record<string, Task[]>;
  workspaceTasks: Task[];
  extractions: Record<string, ExtractionState>;
  loading: boolean;
  error: string | null;
  /** ID of the task currently being PUT-updated, or null when idle. Enables per-task spinners. */
  updatingTaskId: string | null;

  fetchTasks: (storyId: string) => Promise<void>;
  /** Start an asynchronous extraction and begin polling for completion. */
  extractTasks: (storyId: string, workspaceId: string) => Promise<void>;
  /** Poll extraction status until completion or failure. */
  pollExtraction: (storyId: string, extractionId: string) => Promise<void>;
  fetchTasksForWorkspace: (workspaceId: string) => Promise<void>;
  setTasks: (storyId: string, tasks: Task[]) => void;
  /**
   * Optimistic PUT update with rollback.
   * - Applies `updates` immediately to `tasks` and `workspaceTasks`.
   * - Sets `updatingTaskId` while the request is in flight.
   * - On success, overwrites the optimistic with the server-returned Task.
   * - On failure, rolls back to the previous snapshot and re-throws so the caller can toast.
   */
  updateTask: (taskId: string, updates: Partial<Task>) => Promise<void>;
  updateTaskStatus: (taskId: string, status: string) => Promise<void>;
  resetExtraction: (storyId: string) => void;
}

const INITIAL_EXTRACTION: ExtractionState = {
  extractionId: null,
  status: 'idle',
  error: null,
  errorCode: null,
};

/**
 * Categorize a thrown error from the LLM extraction start call into a stable
 * `errorCode` so consumers can react without parsing message strings.
 */
function categorizeExtractionError(err: unknown): ExtractionErrorCode {
  if (!err) return 'server';
  // Shapes thrown by `lib/api.ts`: { status?: number; code?: number|string; message?: string }
  const anyErr = err as { status?: number; code?: number | string; message?: string };
  const status = anyErr.status ?? (typeof anyErr.code === 'number' ? anyErr.code : null);
  if (status === 401 || status === 403) return 'unauthorized';
  if (err instanceof TypeError) return 'network';
  if (typeof anyErr.message === 'string' && /network|fetch|Failed to fetch/i.test(anyErr.message)) {
    return 'network';
  }
  return 'server';
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: {},
  workspaceTasks: [],
  extractions: {},
  loading: false,
  error: null,
  updatingTaskId: null,

  // ── Fetching ──

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

  // ── Async extraction ──

  extractTasks: async (storyId: string, workspaceId: string) => {
    // Mark extraction as pending
    set((state) => ({
      extractions: {
        ...state.extractions,
        [storyId]: { extractionId: null, status: 'pending', error: null, errorCode: null },
      },
    }));

    try {
      const result = await api.startExtraction(storyId, workspaceId);
      // Store the extraction ID and start polling
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: { extractionId: result.extractionId, status: 'pending', error: null, errorCode: null },
        },
      }));

      // Start polling in the background
      get().pollExtraction(storyId, result.extractionId);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Extraction failed to start';
      const errorCode = categorizeExtractionError(err);
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: { extractionId: null, status: 'failed', error: message, errorCode },
        },
      }));
    }
  },

  pollExtraction: async (storyId: string, extractionId: string) => {
    try {
      const status = await api.getExtractionStatus(extractionId);

      if (status.status === 'completed') {
        // Fetch the tasks
        await get().fetchTasks(storyId);
        set((state) => ({
          extractions: {
            ...state.extractions,
            [storyId]: { extractionId, status: 'completed', error: null, errorCode: null },
          },
        }));
      } else if (status.status === 'failed') {
        set((state) => ({
          extractions: {
            ...state.extractions,
            [storyId]: {
              extractionId,
              status: 'failed',
              error: status.errorInfo ?? 'Extraction failed',
              errorCode: 'server',
            },
          },
        }));
      } else {
        // Still pending — poll again after a short delay
        setTimeout(() => {
          // Check that the extraction hasn't been reset in the meantime
          const current = get().extractions[storyId];
          if (current && current.extractionId === extractionId && current.status === 'pending') {
            get().pollExtraction(storyId, extractionId);
          }
        }, 2000);
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Polling failed';
      const errorCode = categorizeExtractionError(err);
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: { extractionId, status: 'failed', error: message, errorCode },
        },
      }));
    }
  },

  // ── Workspace tasks ──

  fetchTasksForWorkspace: async (workspaceId: string) => {
    set({ loading: true, error: null });
    try {
      const items = await api.listTasksByWorkspace(workspaceId);
      set({ workspaceTasks: items, loading: false });
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch tasks';
      set({ error: message, loading: false });
    }
  },

  // ── Mutations ──

  setTasks: (storyId, tasks) =>
    set((state) => ({ tasks: { ...state.tasks, [storyId]: tasks } })),

  /**
   * Optimistic PUT with rollback.
   * 1. Snapshot prev task from `tasks` and `workspaceTasks`.
   * 2. Apply optimistic in both stores. Set `updatingTaskId`.
   * 3. Await `api.updateTask` — returns server-authoritative Task.
   * 4. On success, overwrite optimistic with server response.
   * 5. On error, roll back to prev snapshot and re-throw.
   * 6. Always clear `updatingTaskId` in `finally`.
   */
  updateTask: async (taskId, updates) => {
    const state = get();
    // Snapshot prev (first match wins; ids are unique across stories).
    let prevTask: Task | null = null;
    for (const storyId of Object.keys(state.tasks)) {
      const found = state.tasks[storyId].find((t) => t.id === taskId);
      if (found) {
        prevTask = { ...found };
        break;
      }
    }
    if (!prevTask) {
      const wsFound = state.workspaceTasks.find((t) => t.id === taskId);
      if (wsFound) prevTask = { ...wsFound };
    }
    if (!prevTask) {
      throw new Error(`Task ${taskId} not found in store`);
    }

    // Apply optimistic update across `tasks` and `workspaceTasks`.
    set((s) => {
      const newTasks = { ...s.tasks };
      for (const storyId of Object.keys(newTasks)) {
        newTasks[storyId] = newTasks[storyId].map((t) =>
          t.id === taskId ? { ...t, ...updates } : t,
        );
      }
      return {
        tasks: newTasks,
        workspaceTasks: s.workspaceTasks.map((t) =>
          t.id === taskId ? { ...t, ...updates } : t,
        ),
        updatingTaskId: taskId,
      };
    });

    try {
      const serverTask = await api.updateTask(taskId, updates);
      // Overwrite the optimistic with the server-authoritative Task.
      set((s) => {
        const newTasks = { ...s.tasks };
        for (const storyId of Object.keys(newTasks)) {
          newTasks[storyId] = newTasks[storyId].map((t) =>
            t.id === taskId ? { ...t, ...serverTask } : t,
          );
        }
        return {
          tasks: newTasks,
          workspaceTasks: s.workspaceTasks.map((t) =>
            t.id === taskId ? { ...t, ...serverTask } : t,
          ),
        };
      });
    } catch (err) {
      // Roll back to prev snapshot.
      set((s) => {
        const newTasks = { ...s.tasks };
        for (const storyId of Object.keys(newTasks)) {
          newTasks[storyId] = newTasks[storyId].map((t) =>
            t.id === taskId ? { ...t, ...prevTask! } : t,
          );
        }
        return {
          tasks: newTasks,
          workspaceTasks: s.workspaceTasks.map((t) =>
            t.id === taskId ? { ...t, ...prevTask! } : t,
          ),
        };
      });
      throw err;
    } finally {
      set({ updatingTaskId: null });
    }
  },

  updateTaskStatus: async (taskId: string, status: string) => {
    try {
      await api.updateTaskStatus(taskId, status);
      // Optimistic update
      set((state) => {
        const newTasks = { ...state.tasks };
        for (const storyId of Object.keys(newTasks)) {
          newTasks[storyId] = newTasks[storyId].map((t) =>
            t.id === taskId ? { ...t, status } : t,
          );
        }
        return {
          tasks: newTasks,
          workspaceTasks: state.workspaceTasks.map((t) =>
            t.id === taskId ? { ...t, status } : t,
          ),
        };
      });
    } catch {
      // Revert will be handled by re-fetching
    }
  },

  // ── Reset ──

  resetExtraction: (storyId: string) => {
    set((state) => ({
      extractions: {
        ...state.extractions,
        [storyId]: { ...INITIAL_EXTRACTION },
      },
    }));
  },
}));
