import { api } from './api';
import type { AppSettings } from '@/types/settings';

export interface SettingsApiResponse {
  preferences: AppSettings;
  updated_at: string;
}

/** Fetch user preferences from the backend. */
export async function fetchSettings(): Promise<SettingsApiResponse> {
  return api.get<SettingsApiResponse>('/api/v1/users/me/settings');
}

/** Save user preferences to the backend. */
export async function saveSettings(preferences: AppSettings): Promise<SettingsApiResponse> {
  return api.put<SettingsApiResponse>('/api/v1/users/me/settings', { preferences });
}
