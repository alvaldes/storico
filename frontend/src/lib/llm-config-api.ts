import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { WorkspaceLLMConfig } from '@/types/workspace';
import type { LLMConfigParams } from '@/schemas';

/** Get the LLM config for a workspace (admin only). Falls back to global defaults. */
export async function getLLMConfig(wsId: string): Promise<WorkspaceLLMConfig> {
  const raw = await api.get<Record<string, unknown>>(
    `/api/v1/workspaces/${wsId}/settings/llm`,
  );
  return toCamelCase<WorkspaceLLMConfig>(raw);
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
