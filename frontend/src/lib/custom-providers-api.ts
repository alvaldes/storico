import { api } from './api';
import { toCamelCase, toSnakeCase } from './utils';
import type { CustomProvider } from '@/types/workspace';
import type { CustomProviderNameParams } from '@/schemas';

/** Path of the workspace's custom provider registry. */
function providersPath(wsId: string): string {
  return `/api/v1/workspaces/${wsId}/settings/providers`;
}

/** List the custom providers registered for a workspace (admin only). */
export async function listCustomProviders(wsId: string): Promise<CustomProvider[]> {
  const raw = await api.get<Array<Record<string, unknown>>>(providersPath(wsId));
  return toCamelCase<CustomProvider[]>(raw);
}

/** Register a custom provider name for a workspace (admin only). */
export async function createCustomProvider(
  wsId: string,
  provider: CustomProviderNameParams,
): Promise<CustomProvider> {
  const raw = await api.post<Record<string, unknown>>(providersPath(wsId), toSnakeCase(provider));
  return toCamelCase<CustomProvider>(raw);
}

/**
 * Rename a custom provider (admin only).
 *
 * The backend also follows this into the workspace's provider selection when that
 * selection names this provider, so a caller only has to re-point the field it is
 * displaying rather than persisting the change twice.
 */
export async function renameCustomProvider(
  wsId: string,
  providerId: string,
  provider: CustomProviderNameParams,
): Promise<CustomProvider> {
  const raw = await api.patch<Record<string, unknown>>(
    `${providersPath(wsId)}/${providerId}`,
    toSnakeCase(provider),
  );
  return toCamelCase<CustomProvider>(raw);
}
