import { api } from './api';
import type { AppSettings } from '@/types/settings';

export interface SettingsApiResponse {
  preferences: AppSettings;
  updated_at: string;
}

export interface LLMTestParams {
  provider: string;
  base_url?: string;
  api_key?: string;
  model: string;
}

export interface LLMTestResult {
  success: boolean;
  message: string;
  model?: string;
  latency_ms?: number;
}

/** Fetch user preferences from the backend. */
export async function fetchSettings(): Promise<SettingsApiResponse> {
  return api.get<SettingsApiResponse>('/api/v1/users/me/settings');
}

/** Save user preferences to the backend. */
export async function saveSettings(preferences: AppSettings): Promise<SettingsApiResponse> {
  return api.put<SettingsApiResponse>('/api/v1/users/me/settings', { preferences });
}

/** Test an LLM connection. */
export async function testLLMConnection(params: LLMTestParams): Promise<LLMTestResult> {
  return api.post<LLMTestResult>('/api/v1/llm/test', params);
}
