import { create } from 'zustand';
import { getAllowedTaskTransitions, type Task, type TaskStatus } from '@/types/task';
import type { UserStory, UserStoryStatus } from '@/types/story';
import * as api from '@/lib/tasks-api';
import { ApiRequestError, type RawBackendError } from '@/lib/api';
import { useStoryStore } from '@/stores/storyStore';

// ── Types ──

export type ExtractionStatus = 'idle' | 'pending' | 'completed' | 'failed';
export type ExtractionErrorCode = 'unauthorized' | 'network' | 'server' | null;

export interface ExtractionErrorInfo {
  friendlyMessage: string;
  rawDetail: unknown;
  status?: number;
  errorCode?: string;
}

export interface ExtractionState {
  extractionId: string | null;
  status: ExtractionStatus;
  userStoryStatus: UserStoryStatus | null;
  error: ExtractionErrorInfo | null;
  /** Categorized failure cause so consumers can react specifically (e.g. 401 → re-auth). */
  errorCode: ExtractionErrorCode;
}

export interface TaskState {
  tasks: Record<string, Task[]>;
  workspaceTasks: Task[];
  extractions: Record<string, ExtractionState>;
  loading: boolean;
  error: string | null;
  /** ID of the task currently being PUT-updated, or null when idle. Enables per-task spinners. */
  updatingTaskId: string | null;
  /** Store allowed transitions per task for client-side validation. */
  allowedTransitions: Record<string, TaskStatus[]>;

  fetchTasks: (storyId: string) => Promise<void>;
  /** Start an asynchronous extraction and begin polling for completion. */
  extractTasks: (storyId: string, workspaceId: string) => Promise<void>;
  /** Poll extraction status until completion or failure. */
  pollExtraction: (storyId: string, workspaceId: string, extractionId: string) => Promise<void>;
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
  updateTaskStatus: (taskId: string, status: TaskStatus) => Promise<void>;
  resetExtraction: (storyId: string) => void;
  /** Set allowed transitions for a task (fetched from API or computed client-side). */
  setAllowedTransitions: (taskId: string, transitions: TaskStatus[]) => void;
}

const INITIAL_EXTRACTION: ExtractionState = {
  extractionId: null,
  status: 'idle',
  userStoryStatus: null,
  error: null,
  errorCode: null,
};

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

function extractExtractionErrorInfo(err: unknown): ExtractionErrorInfo {
  if (err instanceof ApiRequestError) {
    return err.toErrorInfo();
  }
  if (err instanceof Error) {
    return {
      friendlyMessage: err.message,
      rawDetail: err.message,
    };
  }
  if (typeof err === 'string') {
    return {
      friendlyMessage: err,
      rawDetail: err,
    };
  }
  return {
    friendlyMessage: 'Extraction failed',
    rawDetail: err,
  };
}

export const useTaskStore = create<TaskState>((set, get) => ({
  tasks: {},
  workspaceTasks: [],
  extractions: {},
  loading: false,
  error: null,
  updatingTaskId: null,
  allowedTransitions: {},

  // ── Fetching ──

  fetchTasks: async (storyId: string) => {
    set({ loading: true, error: null });
    try {
      const items = await api.listTasks(storyId);
      set((state) => ({
        tasks: { ...state.tasks, [storyId]: items },
        loading: false,
      }));
      // Store allowed transitions for each task
      set((state) => {
        const newTransitions = { ...state.allowedTransitions };
        for (const task of items) {
          newTransitions[task.id] = getAllowedTaskTransitions(task.status);
        }
        return { allowedTransitions: newTransitions };
      });
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
        [storyId]: { extractionId: null, status: 'pending', userStoryStatus: null, error: null, errorCode: null },
      },
    }));

    try {
      const result = await api.startExtraction(storyId, workspaceId);
      // Store the extraction ID and start polling
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: { extractionId: result.extractionId, status: 'pending', userStoryStatus: null, error: null, errorCode: null },
        },
      }));

      // Start polling in the background
      get().pollExtraction(storyId, workspaceId, result.extractionId);
    } catch (err) {
      const errorInfo = extractExtractionErrorInfo(err);
      const errorCode = categorizeExtractionError(err);
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: { extractionId: null, status: 'failed', userStoryStatus: 'failed_extraction', error: errorInfo, errorCode },
        },
      }));
    }
  },

  pollExtraction: async (storyId: string, workspaceId: string, extractionId: string) => {
    try {
      const status = await api.getExtractionStatus(extractionId);

      if (status.status === 'completed') {
        // Fetch the tasks
        await get().fetchTasks(storyId);
        // Refresh the workspace-wide cache so KanbanBoard / ExportPanel reflect newly-created tasks.
        if (workspaceId) {
          try { await get().fetchTasksForWorkspace(workspaceId); } catch { /* workspaceTasks is best-effort; per-story fetch already succeeded */ }
        }
        set((state) => ({
          extractions: {
            ...state.extractions,
            [storyId]: { extractionId, status: 'completed', userStoryStatus: status.userStoryStatus as UserStoryStatus, error: null, errorCode: null },
          },
        }));
        // Refresh the story to get updated status from backend
        try { await useStoryStore.getState().fetchStory(storyId); } catch { /* best effort */ }
      } else if (status.status === 'failed') {
        const errorInfo: ExtractionErrorInfo = {
          friendlyMessage: status.errorInfo ?? 'Extraction failed',
          rawDetail: status.errorInfo ?? 'Extraction failed',
          status: 500,
          errorCode: 'EXTRACTION_FAILED',
        };
        set((state) => ({
          extractions: {
            ...state.extractions,
            [storyId]: {
              extractionId,
              status: 'failed',
              userStoryStatus: status.userStoryStatus as UserStoryStatus,
              error: errorInfo,
              errorCode: 'server',
            },
          },
        }));
        // Refresh the story to get updated status from backend
        try { await useStoryStore.getState().fetchStory(storyId); } catch { /* best effort */ }
      } else {
        // Still pending — poll again after a short delay, update userStoryStatus
        set((state) => ({
          extractions: {
            ...state.extractions,
            [storyId]: {
              ...state.extractions[storyId],
              userStoryStatus: status.userStoryStatus as UserStoryStatus,
            },
          },
        }));

        setTimeout(() => {
          // Check that the extraction hasn't been reset in the meantime
          const current = get().extractions[storyId];
          if (current && current.extractionId === extractionId && current.status === 'pending') {
            get().pollExtraction(storyId, workspaceId, extractionId);
          }
        }, 2000);
      }
    } catch (err) {
      const errorInfo = extractExtractionErrorInfo(err);
      const errorCode = categorizeExtractionError(err);
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: { extractionId, status: 'failed', userStoryStatus: 'failed_extraction', error: errorInfo, errorCode },
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
      // Store allowed transitions
      set((state) => {
        const newTransitions = { ...state.allowedTransitions };
        for (const task of items) {
          newTransitions[task.id] = getAllowedTaskTransitions(task.status);
        }
        return { allowedTransitions: newTransitions };
      });
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
    // Snapshot prev task from `tasks` and `workspaceTasks`.
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

  updateTaskStatus: async (taskId: string, status: TaskStatus) => {
    const state = get();

    // Find the task to get its current status for validation
    let currentStatus: TaskStatus | null = null;
    for (const storyId of Object.keys(state.tasks)) {
      const found = state.tasks[storyId].find((t) => t.id === taskId);
      if (found) {
        currentStatus = found.status;
        break;
      }
    }
    if (!currentStatus) {
      const wsFound = state.workspaceTasks.find((t) => t.id === taskId);
      if (wsFound) currentStatus = wsFound.status;
    }
    if (!currentStatus) {
      throw new Error(`Task ${taskId} not found in store`);
    }

    // Client-side validation before sending
    const allowedTransitions = getAllowedTaskTransitions(currentStatus);
    if (!allowedTransitions.includes(status)) {
      const error = new Error(`Invalid transition from ${currentStatus} to ${status}`) as Error & {
        errorCode: string;
        currentState: TaskStatus;
        attemptedState: TaskStatus;
        allowedTransitions: TaskStatus[];
      };
      error.errorCode = 'INVALID_STATE_TRANSITION';
      error.currentState = currentStatus;
      error.attemptedState = status;
      error.allowedTransitions = allowedTransitions;
      throw error;
    }

    try {
      await api.updateTaskStatus(taskId, status, currentStatus);
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
    } catch (err) {
      // Check if it's an INVALID_STATE_TRANSITION from backend
      if (err instanceof Error && 'errorCode' in err && (err as any).errorCode === 'INVALID_STATE_TRANSITION') {
        // Update allowed transitions from backend response
        const apiError = err as any;
        if (apiError.allowedTransitions) {
          set((state) => ({
            allowedTransitions: {
              ...state.allowedTransitions,
              [taskId]: apiError.allowedTransitions,
            },
          }));
        }
      }
      // Revert will be handled by re-fetching
      throw err;
    }
  },

  // ── Transition management ──

  setAllowedTransitions: (taskId: string, transitions: TaskStatus[]) =>
    set((state) => ({
      allowedTransitions: {
        ...state.allowedTransitions,
        [taskId]: transitions,
      },
    })),

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
