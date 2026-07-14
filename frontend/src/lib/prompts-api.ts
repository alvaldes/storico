import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { WorkspacePrompt } from '@/types/workspace';
import type { PromptConfigParams } from '@/schemas';

/** Get the prompt configuration for a workspace (admin only). Falls back to global defaults. */
export async function getPrompts(wsId: string): Promise<WorkspacePrompt> {
  const raw = await api.get<Record<string, unknown>>(
    `/api/v1/workspaces/${wsId}/settings/prompts`,
  );
  return toCamelCase<WorkspacePrompt>(raw);
}

/** Upsert the prompt configuration for a workspace (admin only). */
export async function upsertPrompts(
  wsId: string,
  prompts: PromptConfigParams,
): Promise<WorkspacePrompt> {
  const raw = await api.put<Record<string, unknown>>(
    `/api/v1/workspaces/${wsId}/settings/prompts`,
    toSnakeCase(prompts),
  );
  return toCamelCase<WorkspacePrompt>(raw);
}
