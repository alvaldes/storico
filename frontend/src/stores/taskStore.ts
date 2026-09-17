import { create } from 'zustand';
import { getAllowedTaskTransitions, type Task, type TaskStatus } from '@/types/task';
import type { UserStory, UserStoryStatus } from '@/types/story';
import * as api from '@/lib/tasks-api';
import { ApiRequestError, type RawBackendError } from '@/lib/api';
import { isScopedWorkspace, setScopedWorkspaceId } from '@/lib/workspace-scope';
import { useStoryStore } from '@/stores/storyStore';

// Monotonic token of the newest fetchTasksForWorkspace call. Two workspace fetches can
// settle out of order and only the newest one may write the workspace-scoped slices.
// The workspace scope itself — which workspace those slices belong to — lives in
// `@/lib/workspace-scope`, so every guard here reads the same value as the switch that
// moved it instead of keeping a second copy that could disagree.
let workspaceTasksRequestSeq = 0;

// ── Types ──

export type ExtractionStatus = 'idle' | 'pending' | 'completed' | 'failed' | 'unauthorized';
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
  /**
   * Point the workspace-scoped slices at `workspaceId` and drop them.
   * The single place a switch resets `workspaceTasks` and `extractions`: a switch must never
   * leave the previous workspace's data behind, and the scope must move with the drop so
   * an inflight continuation can tell that it was discarded. `null` means "no workspace
   * remains".
   *
   * The invariant the workspace guards rest on: an entry can only be **added** by a call that
   * names the workspace it belongs to (`extractTasks`, `pollExtraction`, both gated by
   * `isScopedWorkspace`). `resetExtraction` names no workspace because it only **deletes** one
   * story's entry, so a cleanup that runs after a switch clears an already-empty slice and
   * leaves nothing behind.
   */
  setScopeWorkspace: (workspaceId: string | null) => void;
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
    // The request is tagged with its workspace, so a call that is already stale — a
    // component the user just left — must not even mark the story as pending: that entry
    // would survive the switch with no poll to ever settle it.
    if (!isScopedWorkspace(workspaceId)) return;

    // Mark extraction as pending
    set((state) => ({
      extractions: {
        ...state.extractions,
        [storyId]: {
          extractionId: null,
          status: 'pending',
          userStoryStatus: null,
          error: null,
          errorCode: null,
        },
      },
    }));

    try {
      const result = await api.startExtraction(storyId, workspaceId);

      // The POST may land after the workspace it belongs to was discarded. Writing the
      // extraction id now would resurrect that departed workspace's entry as `pending` in
      // the new workspace, and starting a poll for it would keep the ghost alive.
      if (!isScopedWorkspace(workspaceId)) return;

      // Store the extraction ID and start polling
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: {
            extractionId: result.extractionId,
            status: 'pending',
            userStoryStatus: null,
            error: null,
            errorCode: null,
          },
        },
      }));

      // Start polling in the background
      get().pollExtraction(storyId, workspaceId, result.extractionId);
    } catch (err) {
      // A failure of the discarded workspace's extraction must not leave an entry behind
      // in the new workspace's slices either.
      if (!isScopedWorkspace(workspaceId)) return;
      const errorInfo = extractExtractionErrorInfo(err);
      const errorCode = categorizeExtractionError(err);
      // A 401 is an auth failure, not an extraction failure: the store must
      // NOT mark the extraction as `failed`, it must surface an auth-specific
      // error so the UI can prompt re-authentication.
      const unauthorized = errorCode === 'unauthorized';
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: {
            extractionId: null,
            status: unauthorized ? 'unauthorized' : 'failed',
            userStoryStatus: unauthorized ? null : 'failed_extraction',
            error: errorInfo,
            errorCode,
          },
        },
      }));
    }
  },

  pollExtraction: async (storyId: string, workspaceId: string, extractionId: string) => {
    // Every write below belongs to the workspace this poll started in. When that
    // workspace was discarded meanwhile, the continuation must not land on the new
    // workspace's slices. The scope check is read fresh right before each write.
    const scopeCurrent = () => isScopedWorkspace(workspaceId);
    try {
      const status = await api.getExtractionStatus(extractionId);

      if (status.status === 'completed') {
        // Checked before the refresh, not only after it: this poll belongs to a workspace that
        // may already be gone, and `tasks` is keyed by *that* workspace's story, so the refresh
        // would be a request nobody is waiting for. `tasks` surviving a switch is what makes the
        // refresh safe to keep for the current workspace, not what makes it right to issue for a
        // discarded one.
        if (!scopeCurrent()) return;
        await get().fetchTasks(storyId);
        if (!scopeCurrent()) return;
        // Refresh the workspace-wide cache so KanbanBoard / ExportPanel reflect newly-created tasks.
        if (workspaceId) {
          try {
            await get().fetchTasksForWorkspace(workspaceId);
          } catch {
            /* workspaceTasks is best-effort; per-story fetch already succeeded */
          }
        }
        // Re-checked after the await above: a switch during it must not resurrect the entry.
        if (!scopeCurrent()) return;
        set((state) => ({
          extractions: {
            ...state.extractions,
            [storyId]: {
              extractionId,
              status: 'completed',
              userStoryStatus: status.userStoryStatus as UserStoryStatus,
              error: null,
              errorCode: null,
            },
          },
        }));
        // Refresh the story to get updated status from backend
        try {
          await useStoryStore.getState().fetchStory(storyId);
        } catch {
          /* best effort */
        }
      } else if (status.status === 'failed') {
        if (!scopeCurrent()) return;
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
        try {
          await useStoryStore.getState().fetchStory(storyId);
        } catch {
          /* best effort */
        }
      } else {
        // Still pending — poll again after a short delay, update userStoryStatus
        if (!scopeCurrent()) return;
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
      // A failure of the discarded workspace's poll must not surface on the new one.
      if (!scopeCurrent()) return;
      const errorInfo = extractExtractionErrorInfo(err);
      const errorCode = categorizeExtractionError(err);
      const unauthorized = errorCode === 'unauthorized';
      set((state) => ({
        extractions: {
          ...state.extractions,
          [storyId]: {
            extractionId,
            status: unauthorized ? 'unauthorized' : 'failed',
            userStoryStatus: unauthorized ? null : 'failed_extraction',
            error: errorInfo,
            errorCode,
          },
        },
      }));
    }
  },

  // ── Workspace tasks ──

  setScopeWorkspace: (workspaceId: string | null) => {
    // The scope moves first, so an inflight continuation from the workspace being left
    // already reads the new scope and drops its write; only then are the slices cleared.
    setScopedWorkspaceId(workspaceId);
    set({ workspaceTasks: [], extractions: {} });
  },

  fetchTasksForWorkspace: async (workspaceId: string) => {
    // Claimed before the request starts: this call owns `loading` until it settles.
    const requestId = ++workspaceTasksRequestSeq;
    set({ loading: true, error: null });
    try {
      const items = await api.listTasksByWorkspace(workspaceId);
      if (requestId !== workspaceTasksRequestSeq) return;
      if (!isScopedWorkspace(workspaceId)) {
        // No newer request exists, so nobody else owns `loading`: release it, but never
        // apply the discarded workspace's tasks or transitions.
        set({ loading: false });
        return;
      }
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
      if (requestId !== workspaceTasksRequestSeq) return;
      if (!isScopedWorkspace(workspaceId)) {
        // Same as above: drop the discarded workspace's error along with its data.
        set({ loading: false });
        return;
      }
      const message = err instanceof Error ? err.message : 'Failed to fetch tasks';
      set({ error: message, loading: false });
    }
  },

  // ── Mutations ──

  setTasks: (storyId, tasks) => set((state) => ({ tasks: { ...state.tasks, [storyId]: tasks } })),

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
        workspaceTasks: s.workspaceTasks.map((t) => (t.id === taskId ? { ...t, ...updates } : t)),
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
          workspaceTasks: state.workspaceTasks.map((t) => (t.id === taskId ? { ...t, status } : t)),
        };
      });
    } catch (err) {
      // Check if it's an INVALID_STATE_TRANSITION from backend
      if (
        err instanceof Error &&
        'errorCode' in err &&
        (err as any).errorCode === 'INVALID_STATE_TRANSITION'
      ) {
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
    // Dropped, never replaced by an all-null placeholder. `extractions` is workspace-scoped,
    // and this call also runs from a component unmount — which can happen *after* the switch
    // already cleared the slice. Writing a placeholder there would add an entry for the
    // workspace the user has left.
    //
    // Deleting is not merely tidier: every *render* reader treats a missing entry exactly like
    // an `idle` one. The toast effect is the only reader that tells them apart — it skips
    // `setPrevExtractionStatus` — and it cannot observe that difference either, because the
    // unmount cleanup is this method's only live caller.
    if (!get().extractions[storyId]) return;
    set((state) => {
      const extractions = { ...state.extractions };
      delete extractions[storyId];
      return { extractions };
    });
  },
}));
