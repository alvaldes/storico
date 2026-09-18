import { isKnownProvider, type KnownProvider } from '@/lib/llm-providers';

/**
 * The workspace LLM configuration completeness rule, as the frontend reads it.
 *
 * Extraction cannot run against an incomplete configuration, so the settings form has
 * to say *which* field is missing and the extraction button has to refuse before the
 * request. Both read this module; both speak the same vocabulary as the API —
 * `model`, `api_key`, `base_url` — because these are wire codes, not labels. The
 * translated copy lives in the i18n files, one key per code per surface.
 *
 * The rule is declared twice, in two languages, and the backend is authoritative
 * (`backend/src/storico/domain/services/llm_config_readiness.py`). The two declarations
 * are kept in step by `__tests__/llm-config-readiness-mirror.test.ts`, which reads the
 * Python file and fails on any drift — the same guard the provider vocabulary has.
 *
 * Why the rule exists at all: the four known cloud providers cannot call anything
 * without a workspace credential (the API deliberately never falls back to an ambient
 * key), a custom OpenAI-compatible provider cannot be called without an endpoint, and
 * Ollama's host falls back to the configured default, so its base URL is never
 * required.
 */

/** Every field a workspace configuration can be missing, in the order the API reports them. */
export const READINESS_FIELDS = ['model', 'api_key', 'base_url'] as const;

export type ReadinessField = (typeof READINESS_FIELDS)[number];

/**
 * The structured error code the API answers with when it refuses an extraction.
 *
 * Mirrored from `LLM_CONFIG_INCOMPLETE_CODE` in the Python module above; the mirror
 * guard pins the spelling, because the UI maps this exact string to its copy.
 */
export const LLM_CONFIG_INCOMPLETE_CODE = 'LLM_CONFIG_INCOMPLETE';

/** Fields each known provider cannot be called without. */
export const REQUIRED_FIELDS_BY_PROVIDER = {
  ollama: ['model'],
  openai: ['model', 'api_key'],
  anthropic: ['model', 'api_key'],
  gemini: ['model', 'api_key'],
} as const satisfies Record<KnownProvider, readonly ReadinessField[]>;

/**
 * Fields a custom provider cannot be called without.
 *
 * `api_key` stays optional: a self-hosted gateway commonly accepts unauthenticated
 * requests, and the backend substitutes a placeholder key in that case.
 */
export const CUSTOM_PROVIDER_REQUIRED_FIELDS: readonly ReadinessField[] = ['model', 'base_url'];

/**
 * The form field each code names, so a validation issue can find its input.
 *
 * The wire vocabulary is snake_case and the form is camelCase, so this is the one
 * translation between them, kept beside the rule instead of inline at each use.
 */
export const READINESS_FIELD_TO_FORM_KEY = {
  model: 'model',
  api_key: 'apiKey',
  base_url: 'baseUrl',
} as const satisfies Record<ReadinessField, 'model' | 'apiKey' | 'baseUrl'>;

/** The configuration values the rule reads, in the form's camelCase spelling. */
export interface LLMConfigValues {
  provider: string;
  model?: string | null;
  apiKey?: string | null;
  baseUrl?: string | null;
}

/**
 * The fields `provider` cannot be called without.
 *
 * An unknown name is not an error: routing already treats anything outside the four
 * known names as a custom OpenAI-compatible provider, so the rule does too — and the
 * comparison is exact, like `_build_llm_port`'s, so a mis-cased built-in is a custom
 * provider on both sides.
 */
export function requiredFieldsFor(provider: string): readonly ReadinessField[] {
  return isKnownProvider(provider)
    ? REQUIRED_FIELDS_BY_PROVIDER[provider]
    : CUSTOM_PROVIDER_REQUIRED_FIELDS;
}

/**
 * Which required fields are unset, in {@link READINESS_FIELDS} order.
 *
 * A blank or whitespace-only value counts as unset, matching the backend rule: the
 * form holds `''` where the API would store `null`, and an endpoint or a key made of
 * spaces would fail the call just as loudly.
 */
export function missingLLMConfigFields(config: LLMConfigValues): ReadinessField[] {
  const required = requiredFieldsFor(config.provider);
  const present = {
    model: isSet(config.model),
    api_key: isSet(config.apiKey),
    base_url: isSet(config.baseUrl),
  } satisfies Record<ReadinessField, boolean>;
  return READINESS_FIELDS.filter((field) => required.includes(field) && !present[field]);
}

/** Whether the configuration holds everything `provider` needs to be called. */
export function isLLMConfigComplete(config: LLMConfigValues): boolean {
  return missingLLMConfigFields(config).length === 0;
}

/** Whether a configured value is actually present. */
function isSet(value: string | null | undefined): boolean {
  return typeof value === 'string' && value.trim() !== '';
}
