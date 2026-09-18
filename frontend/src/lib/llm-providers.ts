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
 * registry could hold — and the backend refuses to register it, so that spelling
 * stays true.
 */
export const ADD_CUSTOM_PROVIDER_VALUE = '__add_custom_provider__';

/**
 * Longest provider name the backend stores.
 *
 * Mirrors `NAME_MAX_LENGTH` in `backend/src/storico/api/schemas/custom_provider.py`,
 * which matches the `String(50)` column the selection is saved in. Kept in step by
 * hand, with the backend authoritative: this copy drives the input's `maxLength` and
 * the `(0/50)` counter, so the limit is visible instead of arriving as a rejection.
 */
export const PROVIDER_NAME_MAX_LENGTH = 50;

/**
 * Whether a name is one of the four first-class providers, by exact match.
 *
 * Deliberately case-sensitive even though the *reservation* below is not: this
 * predicate derives routing and UI state from a value that is already stored, and
 * `_build_llm_port` compares exactly. Treating `OLLAMA` as known here would make a
 * legacy row read as the built-in adapter while the select offers it as a custom
 * entry that owns its own base URL.
 */
export function isKnownProvider(provider: string): provider is KnownProvider {
  return (KNOWN_PROVIDERS as readonly string[]).includes(provider);
}

/** Trim a submitted name, matching the backend's normalization (which keeps casing). */
export function normalizeProviderName(raw: string): string {
  return raw.trim();
}

/**
 * Whether a name is already taken by something that is not a provider entry.
 *
 * Mirrors `_reject_reserved_provider_name` in
 * `backend/src/storico/api/routes/workspace_settings.py`: the four built-in names in
 * any casing, and the select's own control value. Both are refusals the backend
 * answers with `409`, not with a rule violation.
 */
export function isReservedProviderName(name: string): boolean {
  const trimmed = normalizeProviderName(name);
  if (trimmed === ADD_CUSTOM_PROVIDER_VALUE) return true;
  return (KNOWN_PROVIDERS as readonly string[]).includes(trimmed.toLowerCase());
}

/**
 * Whether the backend will accept this name.
 *
 * Mirrors the rule in `backend/src/storico/api/schemas/custom_provider.py`: the name
 * is free-form text of 1 to `PROVIDER_NAME_MAX_LENGTH` characters once trimmed, and
 * nothing else. The trim happens here as well because the backend validates the
 * trimmed value; the casing is left alone, since the name is stored as typed.
 */
export function isValidProviderName(name: string): boolean {
  const trimmed = normalizeProviderName(name);
  if (trimmed.length === 0 || trimmed.length > PROVIDER_NAME_MAX_LENGTH) return false;
  return !isReservedProviderName(trimmed);
}
