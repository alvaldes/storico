/** Kanban column status for a task — matches backend TaskStatus enum. */
export type TaskStatus = 'backlog' | 'todo' | 'in_progress' | 'review' | 'done';

/** All valid TaskStatus values in Kanban flow order. */
export const TASK_STATUSES: TaskStatus[] = ['backlog', 'todo', 'in_progress', 'review', 'done'];

/** Valid Kanban transitions per column. */
export const VALID_TASK_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  backlog: ['backlog', 'todo'],
  todo: ['backlog', 'in_progress'],
  in_progress: ['todo', 'review'],
  review: ['in_progress', 'done'],
  done: ['done'],
};

/** Check if a transition from current to next status is valid. */
export function isValidTaskTransition(current: TaskStatus, next: TaskStatus): boolean {
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