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
  createdAt: string;
}

/** Fetch the current user profile from the backend. */
export async function fetchCurrentUser(): Promise<UserProfileResponse> {
  const raw = await api.get<Record<string, unknown>>('/api/v1/users/me');
  return toCamelCase<UserProfileResponse>(raw);
}
