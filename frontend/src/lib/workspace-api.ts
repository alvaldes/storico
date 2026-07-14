import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { Workspace, WorkspaceMember } from '@/types/workspace';
import type { CreateWorkspaceParams, UpdateWorkspaceParams } from '@/schemas';

/** Create a new workspace. */
export async function createWorkspace(params: CreateWorkspaceParams): Promise<Workspace> {
  const raw = await api.post<Record<string, unknown>>(
    '/api/v1/workspaces/',
    toSnakeCase(params),
  );
  return toCamelCase<Workspace>(raw);
}

/** List all workspaces the current user belongs to. */
export async function listWorkspaces(): Promise<{ workspaces: Workspace[] }> {
  const raw = await api.get<Record<string, unknown>>('/api/v1/workspaces/');
  return toCamelCase<{ workspaces: Workspace[] }>(raw);
}

/** Get a single workspace by ID. */
export async function getWorkspace(id: string): Promise<Workspace> {
  const raw = await api.get<Record<string, unknown>>(`/api/v1/workspaces/${id}`);
  return toCamelCase<Workspace>(raw);
}

/** Update workspace name/slug. */
export async function updateWorkspace(
  id: string,
  params: UpdateWorkspaceParams,
): Promise<Workspace> {
  const raw = await api.put<Record<string, unknown>>(
    `/api/v1/workspaces/${id}`,
    toSnakeCase(params),
  );
  return toCamelCase<Workspace>(raw);
}

/** Delete a workspace. */
export async function deleteWorkspace(id: string): Promise<void> {
  await api.delete(`/api/v1/workspaces/${id}`);
}

/** List members of a workspace (admin only). */
export async function listMembers(wsId: string): Promise<{ members: WorkspaceMember[] }> {
  const raw = await api.get<Record<string, unknown>>(`/api/v1/workspaces/${wsId}/members`);
  return toCamelCase<{ members: WorkspaceMember[] }>(raw);
}

/** Add a member to a workspace (admin only). */
export async function addMember(wsId: string, userId: string): Promise<void> {
  await api.post(
    `/api/v1/workspaces/${wsId}/members`,
    toSnakeCase({ userId }),
  );
}

/** Update a member's role (admin only). */
export async function updateMemberRole(
  wsId: string,
  userId: string,
  role: string,
): Promise<void> {
  await api.put(
    `/api/v1/workspaces/${wsId}/members/${userId}`,
    toSnakeCase({ role }),
  );
}

/** Remove a member from a workspace (admin only). */
export async function removeMember(wsId: string, userId: string): Promise<void> {
  await api.delete(`/api/v1/workspaces/${wsId}/members/${userId}`);
}

/** Transfer workspace ownership to another admin. */
export async function transferOwnership(wsId: string, newOwnerId: string): Promise<void> {
  await api.post(
    `/api/v1/workspaces/${wsId}/transfer`,
    toSnakeCase({ newOwnerId }),
  );
}
