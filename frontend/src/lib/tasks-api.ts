import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { Task } from '@/types/task';
import type { PaginatedResponse } from './projects-api';

// ── Mapping helpers ──

interface RawTaskItem {
  id: string;
  user_story_id: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  labels: string[];
  dependencies: string[];
  created_at: string;
  updated_at: string;
}

function mapTaskItem(raw: RawTaskItem): Task {
  return {
    id: raw.id,
    storyId: raw.user_story_id,
    title: raw.title,
    description: raw.description,
    status: raw.status,
    priority: raw.priority,
    labels: raw.labels,
    dependencies: raw.dependencies,
    createdAt: raw.created_at,
    updatedAt: raw.updated_at,
  };
}

interface RawExtractResult {
  extraction_id: string;
  status: string;
  tasks: RawTaskItem[];
  model_used: string;
  error_info?: string;
  confidence_score?: number;
}

function mapExtractResult(raw: RawExtractResult): {
  extractionId: string;
  status: string;
  tasks: Task[];
  modelUsed: string;
  errorInfo?: string;
} {
  return {
    extractionId: raw.extraction_id,
    status: raw.status,
    tasks: raw.tasks.map(mapTaskItem),
    modelUsed: raw.model_used,
    errorInfo: raw.error_info,
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

/** Update a task status (used by Kanban drag-and-drop). */
export async function updateTaskStatus(
  taskId: string,
  status: string,
): Promise<Task> {
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
    status?: string;
    priority?: string;
  },
): Promise<Task> {
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
 */
export async function getExtractionStatus(
  extractionId: string,
): Promise<{
  id: string;
  userStoryId: string;
  modelUsed: string;
  status: string;
  errorInfo: string | null;
  confidenceScore: number | null;
}> {
  const raw = await api.get<{
    id: string;
    user_story_id: string;
    model_used: string;
    status: string;
    error_info: string | null;
    confidence_score: number | null;
  }>(`/api/v1/extractions/${extractionId}`);
  return {
    id: raw.id,
    userStoryId: raw.user_story_id,
    modelUsed: raw.model_used,
    status: raw.status,
    errorInfo: raw.error_info,
    confidenceScore: raw.confidence_score,
  };
}

/** @deprecated Use ``startExtraction()`` + ``getExtractionStatus()`` instead.
 *
 * The old synchronous extraction endpoint is now asynchronous. This function
 * is kept for backward compatibility but will be removed.
 */
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
  // Poll until complete or failed
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
