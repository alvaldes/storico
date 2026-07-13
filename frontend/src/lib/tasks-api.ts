import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { Task } from '@/types/task';
import type { PaginatedResponse } from './projects-api';

/** Fetch tasks for a specific user story. */
export async function listTasks(storyId: string): Promise<Task[]> {
  const raw = await api.get<Record<string, unknown>>(
    `/api/v1/tasks/?user_story_id=${storyId}&page=1&size=100`,
  );
  const parsed = toCamelCase<PaginatedResponse<Record<string, unknown>>>(raw);
  return parsed.items.map((item) => toCamelCase<Task>(item));
}

/** Trigger extraction for a user story. Returns extraction result with tasks. */
export async function extractTasks(
  storyId: string,
  options?: { model?: string; temperature?: number },
): Promise<{
  extractionId: string;
  status: string;
  tasks: Task[];
  modelUsed: string;
  errorInfo?: string;
}> {
  const raw = await api.post<Record<string, unknown>>('/api/v1/extract/', {
    user_story_id: storyId,
    model: options?.model ?? null,
    temperature: options?.temperature ?? null,
    run_validation: false,
  });
  return toCamelCase<{
    extractionId: string;
    status: string;
    tasks: Task[];
    modelUsed: string;
    errorInfo?: string;
  }>(raw);
}
