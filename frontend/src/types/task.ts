/** Kanban column status for a task — matches backend TaskStatus enum. */
export type TaskStatus = 'backlog' | 'todo' | 'in_progress' | 'review' | 'done';

/** All valid TaskStatus values in Kanban flow order. */
export const TASK_STATUSES: TaskStatus[] = ['backlog', 'todo', 'in_progress', 'review', 'done'];

/** Valid Kanban transitions per column. */
export const VALID_TASK_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  backlog: ['todo'],
  todo: ['backlog', 'in_progress'],
  in_progress: ['todo', 'review'],
  review: ['in_progress', 'done'],
  done: [],
};

/** Check if a transition from current to next status is valid. */
export function isValidTaskTransition(current: TaskStatus, next: TaskStatus): boolean {
  // A no-op is not a transition: saving a task without changing its status
  // must not be rejected, and the backend allows it too.
  if (current === next) return true;
  return VALID_TASK_TRANSITIONS[current]?.includes(next) ?? false;
}

/** Get allowed transitions from a given status. */
export function getAllowedTaskTransitions(current: TaskStatus): TaskStatus[] {
  return VALID_TASK_TRANSITIONS[current] ?? [];
}

export interface Task {
  id: string;
  storyId: string;
  title: string;
  description: string;
  labels: string[];
  dependencies: string[];
  status: TaskStatus;
  priority: string;
  createdAt: string;
  updatedAt: string;
}

/** Raw task from API (snake_case). */
export interface RawTaskItem {
  id: string;
  user_story_id: string;
  title: string;
  description: string;
  status: TaskStatus;
  priority: string;
  labels: string[];
  dependencies: string[];
  created_at: string;
  updated_at: string;
}

/* ── Invalidation marks (0.9.0 slice b) ── */

/** Raw invalidation mark from the API (snake_case). */
export interface RawTaskInvalidation {
  id: string;
  reason: string;
  marked_by: string;
  marked_at: string;
  revoked_by: string | null;
  revoked_at: string | null;
}

/**
 * One invalidation mark (active or revoked) as the mark history returns it.
 * Mirrors the backend `InvalidationResponse`: no `task_id`, because the route
 * path is the task, so echoing it back says nothing the caller did not have.
 */
export interface TaskInvalidation {
  id: string;
  reason: string;
  markedBy: string;
  markedAt: string;
  revokedBy: string | null;
  revokedAt: string | null;
}

/** Raw story-scoped mark from `GET /stories/{id}/invalidations` (snake_case). */
export interface RawStoryInvalidation extends RawTaskInvalidation {
  task_id: string;
}

/**
 * One active mark of a story's tasks: the mark plus the task it belongs to.
 *
 * The per-task read's `TaskInvalidation` deliberately omits `taskId` — its route
 * path is the task, so echoing it back says nothing. A story-scoped read answers
 * many tasks, so the id is the answer's whole point. Revoked marks are not part
 * of this read; the history belongs to the task-scoped read.
 */
export interface StoryInvalidation extends TaskInvalidation {
  taskId: string;
}

/** Raw D16 repetition match from the API (snake_case). */
export interface RawRepetitionMatch {
  version_number: number;
  reason: string;
  marked_at: string;
}

/** One D16 match: a mark on another version whose normalized title equals the task's. */
export interface RepetitionMatch {
  versionNumber: number;
  reason: string;
  markedAt: string;
}

/** The D16 read's answer — a bare list inside an envelope. */
export interface RepetitionResponse {
  matches: RepetitionMatch[];
}
