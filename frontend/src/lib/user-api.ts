import { api } from './api';
import { toCamelCase } from './utils';
import type { AuthUser } from '@/stores/authStore';

export interface UserProfileResponse {
  id: string;
  email: string;
  name: string;
  authProvider: string;
  authId: string;
  avatarUrl?: string;
  isFirstLogin: boolean;
  createdAt: string;
}

export interface WorkspaceSummary {
  id: string;
  name: string;
  slug: string;
  role: string;
  createdAt: string;
}

export interface FullUserProfile {
  user: UserProfileResponse;
  workspaces: WorkspaceSummary[];
}

/** Fetch the current user profile from the backend. */
export async function fetchCurrentUser(): Promise<UserProfileResponse> {
  const raw = await api.get<Record<string, unknown>>('/api/v1/users/me');
  const profile = raw as { user: Record<string, unknown> };
  return toCamelCase<UserProfileResponse>(profile.user);
}

/** Fetch the full user profile including workspaces. */
export async function fetchFullUserProfile(): Promise<FullUserProfile> {
  const raw = await api.get<Record<string, unknown>>('/api/v1/users/me');
  return toCamelCase<FullUserProfile>(raw);
}

/** Mark onboarding as completed, optionally renaming the workspace. */
export async function completeOnboarding(workspaceName?: string): Promise<void> {
  const body = workspaceName ? { workspace_name: workspaceName } : undefined;
  await api.patch('/api/v1/users/me/onboarding', body);
}
