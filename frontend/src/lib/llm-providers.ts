/**
 * The LLM provider vocabulary shared by the workspace settings UI.
 *
 * A provider is either first-class — one of the four names the backend routes to a
 * dedicated adapter and exposes a model-discovery endpoint for — or a custom name
 * a workspace registered for an OpenAI-compatible endpoint.
 */

/** Providers with first-class support (known model-fetch endpoints). */
export const KNOWN_PROVIDERS = ['ollama', 'openai', 'anthropic', 'gemini'] as const;

export type KnownProvider = (typeof KNOWN_PROVIDERS)[number];

/**
 * Select option that opens the add-provider dialog.
 *
 * It is a control, never a provider value: choosing it must leave the current
 * selection untouched, so it is spelled to be impossible to mistake for a name the
 * registry could hold.
 */
export const ADD_CUSTOM_PROVIDER_VALUE = '__add_custom_provider__';

/**
 * Mirrors the rule in `backend/src/storico/api/schemas/custom_provider.py`.
 *
 * Kept in step by hand, with the backend authoritative: this copy only spares the
 * user a round trip to be told the name is unusable.
 */
const PROVIDER_NAME_PATTERN = /^[a-z0-9][a-z0-9._-]{0,49}$/;

export function isKnownProvider(provider: string): provider is KnownProvider {
  return (KNOWN_PROVIDERS as readonly string[]).includes(provider);
}

/** Trim and lowercase a submitted name, matching the backend's normalization. */
export function normalizeProviderName(raw: string): string {
  return raw.trim().toLowerCase();
}

/** Whether an already-normalized name is a provider slug the backend accepts. */
export function isValidProviderName(name: string): boolean {
  return PROVIDER_NAME_PATTERN.test(name);
}
