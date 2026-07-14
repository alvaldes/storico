import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { Project } from '@/types/project';
import type { CreateProjectParams, UpdateProjectParams } from '@/schemas';

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

/** Create a new project in a workspace. */
export async function createProject(
  workspaceId: string,
  params: CreateProjectParams,
): Promise<Project> {
  const raw = await api.post<Record<string, unknown>>(
    `/api/v1/workspaces/${workspaceId}/projects/`,
    toSnakeCase(params),
  );
  return toCamelCase<Project>(raw);
}

/** List projects in a workspace with pagination. */
export async function listProjects(
  workspaceId: string,
  page = 1,
  size = 20,
): Promise<PaginatedResponse<Project>> {
  const raw = await api.get<Record<string, unknown>>(
    `/api/v1/workspaces/${workspaceId}/projects/?page=${page}&size=${size}`,
  );
  return toCamelCase<PaginatedResponse<Project>>(raw);
}

/** Get a single project by ID within a workspace. */
export async function getProject(workspaceId: string, id: string): Promise<Project> {
  const raw = await api.get<Record<string, unknown>>(
    `/api/v1/workspaces/${workspaceId}/projects/${id}`,
  );
  return toCamelCase<Project>(raw);
}

/** Update a project. */
export async function updateProject(
  workspaceId: string,
  id: string,
  params: UpdateProjectParams,
): Promise<Project> {
  const raw = await api.put<Record<string, unknown>>(
    `/api/v1/workspaces/${workspaceId}/projects/${id}`,
    toSnakeCase(params),
  );
  return toCamelCase<Project>(raw);
}

/** Delete a project. */
export async function deleteProject(workspaceId: string, id: string): Promise<void> {
  await api.delete(`/api/v1/workspaces/${workspaceId}/projects/${id}`);
}
