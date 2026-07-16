import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { WorkspaceLLMConfig } from '@/types/workspace';
import type { LLMConfigParams } from '@/schemas';

/** A model available from an LLM provider. */
export interface AvailableModel {
  id: string;
  name: string;
}

/** Get the LLM config for a workspace (admin only). Falls back to global defaults. */
export async function getLLMConfig(wsId: string): Promise<WorkspaceLLMConfig> {
  const raw = await api.get<Record<string, unknown>>(
    `/api/v1/workspaces/${wsId}/settings/llm`,
  );
  return toCamelCase<WorkspaceLLMConfig>(raw);
}

/** Fetch available models from the configured provider for this workspace. */
export async function fetchAvailableModels(
  wsId: string,
): Promise<AvailableModel[]> {
  const raw = await api.get<Array<{ id: string; name: string }>>(
    `/api/v1/workspaces/${wsId}/settings/llm/models`,
  );
  return raw.map((m) => ({ id: m.id, name: m.name }));
}

/** Upsert the LLM config for a workspace (admin only). */
export async function upsertLLMConfig(
  wsId: string,
  config: LLMConfigParams,
): Promise<WorkspaceLLMConfig> {
  const raw = await api.put<Record<string, unknown>>(
    `/api/v1/workspaces/${wsId}/settings/llm`,
    toSnakeCase(config),
  );
  return toCamelCase<WorkspaceLLMConfig>(raw);
}
