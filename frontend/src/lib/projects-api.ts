import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { Project, CreateProjectParams, UpdateProjectParams } from '@/types/project';

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

/** Create a new project. */
export async function createProject(
  params: CreateProjectParams & { ownerId: string },
): Promise<Project> {
  const raw = await api.post<Record<string, unknown>>(
    '/api/v1/projects/',
    toSnakeCase(params),
  );
  return toCamelCase<Project>(raw);
}

/** List all projects with pagination. */
export async function listProjects(
  page = 1,
  size = 20,
): Promise<PaginatedResponse<Project>> {
  const raw = await api.get<Record<string, unknown>>(
    `/api/v1/projects/?page=${page}&size=${size}`,
  );
  return toCamelCase<PaginatedResponse<Project>>(raw);
}

/** Get a single project by ID. */
export async function getProject(id: string): Promise<Project> {
  const raw = await api.get<Record<string, unknown>>(`/api/v1/projects/${id}`);
  return toCamelCase<Project>(raw);
}

/** Update a project. */
export async function updateProject(
  id: string,
  params: UpdateProjectParams,
): Promise<Project> {
  const raw = await api.put<Record<string, unknown>>(
    `/api/v1/projects/${id}`,
    toSnakeCase(params),
  );
  return toCamelCase<Project>(raw);
}

/** Delete a project. */
export async function deleteProject(id: string): Promise<void> {
  await api.delete(`/api/v1/projects/${id}`);
}
