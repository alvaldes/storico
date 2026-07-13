import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { UserStory } from '@/types/story';
import type { CreateStoryParams, UpdateStoryParams } from '@/schemas';
import type { PaginatedResponse } from './projects-api';

/** Create a new user story. */
export async function createStory(params: CreateStoryParams): Promise<UserStory> {
  const raw = await api.post<Record<string, unknown>>(
    '/api/v1/stories/',
    toSnakeCase(params),
  );
  return toCamelCase<UserStory>(raw);
}

/** List user stories with optional project filter and pagination. */
export async function listStories(
  projectId?: string,
  page = 1,
  size = 20,
): Promise<PaginatedResponse<UserStory>> {
  let path = `/api/v1/stories/?page=${page}&size=${size}`;
  if (projectId) {
    path += `&project_id=${projectId}`;
  }
  const raw = await api.get<Record<string, unknown>>(path);
  return toCamelCase<PaginatedResponse<UserStory>>(raw);
}

/** Get a single user story by ID. */
export async function getStory(id: string): Promise<UserStory> {
  const raw = await api.get<Record<string, unknown>>(`/api/v1/stories/${id}`);
  return toCamelCase<UserStory>(raw);
}

/** Update a user story. */
export async function updateStory(
  id: string,
  params: UpdateStoryParams,
): Promise<UserStory> {
  const raw = await api.put<Record<string, unknown>>(
    `/api/v1/stories/${id}`,
    toSnakeCase(params),
  );
  return toCamelCase<UserStory>(raw);
}

/** Delete a user story. */
export async function deleteStory(id: string): Promise<void> {
  await api.delete(`/api/v1/stories/${id}`);
}
