import { api, ApiRequestError } from './api';
import type { Task, TaskStatus, RawTaskItem } from '@/types/task';
import { getAllowedTaskTransitions, isValidTaskTransition } from '@/types/task';

// ── Mapping helpers ──

function mapTaskItem(raw: RawTaskItem): Task {
  return {
    id: raw.id,
    storyId: raw.user_story_id,
    title: raw.title,
    description: raw.description,
    status: raw.status as TaskStatus,
    priority: raw.priority,
    labels: raw.labels,
    dependencies: raw.dependencies,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

/** Fetch tasks for a specific user story. */
export async function listTasks(storyId: string): Promise<Task[]> {
  const raw = await api.get<{ items: RawTaskItem[] }>(
    `/api/v1/tasks/?user_story_id=${storyId}&page=1&size=100`,
  );
  return raw.items.map(mapTaskItem);
}

/** Fetch all tasks for a workspace (for the Kanban board / export). */
export async function listTasksByWorkspace(workspaceId: string): Promise<Task[]> {
  const raw = await api.get<{ items: RawTaskItem[] }>(
    `/api/v1/tasks/?workspace_id=${workspaceId}&page=1&size=100`,
  );
  return raw.items.map(mapTaskItem);
}

/** Update a task status (used by Kanban drag-and-drop).
 * Performs client-side validation before sending to backend. */
export async function updateTaskStatus(
  taskId: string,
  status: TaskStatus,
  currentStatus?: TaskStatus,
): Promise<Task> {
  // Client-side pre-validation when the caller knows the current status.
  // The backend re-validates (and allows no-ops).
  if (currentStatus !== undefined && !isValidTaskTransition(currentStatus, status)) {
    const allowed = getAllowedTaskTransitions(currentStatus);
    const error = new Error(`Invalid transition from ${currentStatus} to ${status}`) as Error & {
      errorCode: string;
      currentState: TaskStatus;
      attemptedState: TaskStatus;
      allowedTransitions: TaskStatus[];
    };
    error.errorCode = 'INVALID_STATE_TRANSITION';
    error.currentState = currentStatus;
    error.attemptedState = status;
    error.allowedTransitions = allowed;
    throw error;
  }

  const raw = await api.put<RawTaskItem>(`/api/v1/tasks/${taskId}`, { status });
  return mapTaskItem(raw);
}

/** Fields `updateTask` writes.
 *
 * D5/D21 field matrix (WU2): the backend's `UpdateTaskRequest` carries only
 * `status`, `labels` and `dependencies` with `extra="forbid"`, so any other
 * key in the PUT body is a 422. This type is the whole write contract: a
 * caller that names a removed field (`title`, `description`, `priority`)
 * fails to compile instead of silently getting that key discarded at
 * runtime. Deliberate runtime-discard probes (tests) admit the stale literal
 * through a local cast, never through a permissive export.
 */
export type TaskUpdateFields = {
  status?: TaskStatus;
  labels?: string[];
  dependencies?: string[];
};

/** Update a task's editable fields (used by TaskEditor).
 *
 * Sends ONLY what the caller actually passed: the `dependencies` key appears
 * in the body only when the caller passed it (its presence is the write — it
 * must never be materialized as `[]` or `undefined`), and the removed legacy
 * fields never reach the body even if a caller still names them.
 */
export async function updateTask(taskId: string, fields: TaskUpdateFields): Promise<Task> {
  const body: { status?: TaskStatus; labels?: string[]; dependencies?: string[] } = {};
  if (fields.status !== undefined) body.status = fields.status;
  if (fields.labels !== undefined) body.labels = fields.labels;
  if (fields.dependencies !== undefined) body.dependencies = fields.dependencies;
  const raw = await api.put<RawTaskItem>(`/api/v1/tasks/${taskId}`, body);
  return mapTaskItem(raw);
}

/** Start an asynchronous extraction for a user story.
 *
 * Returns **immediately** with ``status: "pending"`` and an ``extractionId``.
 * The client must poll ``getExtractionStatus()`` until status changes to
 * ``"completed"`` or ``"failed"``.
 *
 * Uses the workspace-scoped endpoint so workspace membership is validated
 * server-side. The legacy `/api/v1/extract/` endpoint now returns 410 Gone.
 */
export async function startExtraction(
  storyId: string,
  workspaceId: string,
  options?: { model?: string; temperature?: number },
): Promise<{
  extractionId: string;
  status: string;
  modelUsed: string;
}> {
  const raw = await api.post<{ extraction_id: string; status: string; model_used: string }>(
    `/api/v1/workspaces/${workspaceId}/extract/`,
    {
      user_story_id: storyId,
      model: options?.model ?? null,
      temperature: options?.temperature ?? null,
      run_validation: false,
    },
  );
  return {
    extractionId: raw.extraction_id,
    status: raw.status,
    modelUsed: raw.model_used,
  };
}

/** Poll the status of an extraction by its ID.
 *
 * Returns the current status, error info (if any), and confidence score.
 * When status is ``"completed"``, use ``listTasks(storyId)`` to fetch the
 * generated tasks.
 * Now includes ``user_story_status`` to show the UserStory lifecycle state.
 */
export async function getExtractionStatus(extractionId: string): Promise<{
  id: string;
  userStoryId: string;
  modelUsed: string;
  status: string;
  userStoryStatus: string;
  errorInfo: string | null;
  confidenceScore: number | null;
}> {
  const raw = await api.get<{
    id: string;
    user_story_id: string;
    model_used: string;
    status: string;
    user_story_status: string;
    error_info: string | null;
    confidence_score: number | null;
  }>(`/api/v1/extractions/${extractionId}`);
  return {
    id: raw.id,
    userStoryId: raw.user_story_id,
    modelUsed: raw.model_used,
    status: raw.status,
    userStoryStatus: raw.user_story_status,
    errorInfo: raw.error_info,
    confidenceScore: raw.confidence_score,
  };
}

/** @deprecated Use ``startExtraction()`` + ``getExtractionStatus()`` instead. */
export async function extractTasks(
  storyId: string,
  workspaceId: string,
  options?: { model?: string; temperature?: number },
): Promise<{
  extractionId: string;
  status: string;
  tasks: Task[];
  modelUsed: string;
  errorInfo?: string;
}> {
  const result = await startExtraction(storyId, workspaceId, options);
  if (result.status !== 'pending') {
    return { ...result, tasks: [] };
  }
  const pollStatus = await pollUntilComplete(result.extractionId);
  if (pollStatus.status === 'completed') {
    const tasks = await listTasks(storyId);
    return { ...result, status: 'completed', tasks };
  }
  return {
    ...result,
    status: pollStatus.status,
    tasks: [],
    errorInfo: pollStatus.errorInfo ?? undefined,
  };
}

async function pollUntilComplete(
  extractionId: string,
  maxAttempts = 60,
  intervalMs = 2000,
): Promise<{ status: string; errorInfo: string | null }> {
  for (let i = 0; i < maxAttempts; i++) {
    const status = await getExtractionStatus(extractionId);
    if (status.status === 'completed' || status.status === 'failed') {
      return { status: status.status, errorInfo: status.errorInfo };
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  return { status: 'failed', errorInfo: 'Polling timed out' };
}
