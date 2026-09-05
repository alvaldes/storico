import { api, ApiRequestError } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { Task, TaskStatus, RawTaskItem } from '@/types/task';
import type { ExtractionResponse, ExtractResponse, ExtractRequest, ExtractionTask, ExtractionUserStory } from '@/types/extraction';
import type { UserStory } from '@/types/story';
import type { PaginatedResponse } from './projects-api';

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
  currentStatus: TaskStatus,
): Promise<Task> {
  // Client-side validation before sending to backend
  if (!isValidTransition(currentStatus, status)) {
    const allowed = getAllowedTransitions(currentStatus);
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

/** Update arbitrary task fields (used by TaskEditor). */
export async function updateTask(
  taskId: string,
  fields: {
    title?: string;
    description?: string;
    labels?: string[];
    dependencies?: string[];
    status?: TaskStatus;
    priority?: string;
  },
): Promise<Task> {
  // If status is being updated, validate client-side
  if (fields.status !== undefined) {
    // We need the current status - fetch it first
    // Note: In practice, the caller (TaskEditor) should pass currentStatus
    // For now, we'll let the backend validate and catch the error
  }

  const raw = await api.put<RawTaskItem>(
    `/api/v1/tasks/${taskId}`,
    toSnakeCase(fields),
  );
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
export async function getExtractionStatus(
  extractionId: string,
): Promise<{
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
  return { ...result, status: pollStatus.status, tasks: [], errorInfo: pollStatus.errorInfo ?? undefined };
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

/** Client-side transition validation helpers. */
export function isValidTransition(current: string, next: string): boolean {
  const validTransitions: Record<string, string[]> = {
    backlog: ['backlog', 'todo'],
    todo: ['backlog', 'in_progress'],
    in_progress: ['todo', 'review'],
    review: ['in_progress', 'done'],
    done: ['done'],
  };
  return validTransitions[current]?.includes(next) ?? false;
}

export function getAllowedTransitions(current: string): string[] {
  const validTransitions: Record<string, string[]> = {
    backlog: ['backlog', 'todo'],
    todo: ['backlog', 'in_progress'],
    in_progress: ['todo', 'review'],
    review: ['in_progress', 'done'],
    done: ['done'],
  };
  return validTransitions[current] ?? [];
}