import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { WorkspaceLLMConfig } from '@/types/workspace';
import type { LLMConfigParams } from '@/schemas';

/** A model available from an LLM provider. */
export interface AvailableModel {
  id: string;
  name: string;
}

/**
 * The selection the model list must describe.
 *
 * Sent by the settings form so the answer names the provider the user has chosen
 * rather than the one already saved. A field left out is missing for this probe and
 * is never filled in from the saved row: the backend reads it as "that is all this
 * probe has", which keeps one provider's credential away from another's endpoint.
 */
export interface ModelProbe {
  provider: string;
  baseUrl?: string | null;
  apiKey?: string | null;
}

/** Get the LLM config for a workspace (admin only). Falls back to global defaults. */
export async function getLLMConfig(wsId: string): Promise<WorkspaceLLMConfig> {
  const raw = await api.get<Record<string, unknown>>(`/api/v1/workspaces/${wsId}/settings/llm`);
  return toCamelCase<WorkspaceLLMConfig>(raw);
}

/**
 * Fetch available models from the provider the given selection describes.
 *
 * ``POST`` rather than ``GET`` because the selection carries an API key, and a query
 * string writes it into access logs. Omit the probe to be answered for the saved
 * workspace config.
 */
export async function fetchAvailableModels(
  wsId: string,
  probe?: ModelProbe,
): Promise<AvailableModel[]> {
  const raw = await api.post<Array<{ id: string; name: string }>>(
    `/api/v1/workspaces/${wsId}/settings/llm/models`,
    probe === undefined ? undefined : toSnakeCase(probe),
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
