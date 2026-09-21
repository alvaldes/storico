export type ExportFormat = 'json' | 'markdown';

/**
 * Export formats a previous version offered and this one does not.
 *
 * A retired value cannot be dropped the way a retired key can: `extra="forbid"` never sees a
 * value, so the API rewrites it on read instead of refusing it. This map is the client's half
 * of that rewrite — `RETIRED_EXPORT_FORMATS` in the backend schema is the other half — and it
 * is needed here at all because `settingsStore` persists to localStorage: a browser that
 * stored `trello` would otherwise render a blank Select label and PUT a value the API refuses.
 */
export const RETIRED_EXPORT_FORMATS: Record<string, ExportFormat> = { trello: 'json' };

export interface ExportConfig {
  defaultFormat: ExportFormat;
}

/**
 * The user's application preferences, as the API carries them.
 *
 * Deliberately holds no LLM configuration. This type used to mirror a per-user `llm` block —
 * a provider selection plus a `model`/`api_key`/`base_url` per provider — which the
 * preferences endpoint round-tripped and nothing ever read: the live configuration is per
 * *workspace* (`workspace_llm_configs`), a different row with a different owner. The backend
 * removed the field from its schema and from storage (revision `0022`), and its
 * `extra="forbid"` is what keeps a credential from being posted back through that endpoint.
 */
export interface AppSettings {
  export: ExportConfig;
}

export const DEFAULT_SETTINGS: AppSettings = {
  export: {
    defaultFormat: 'json',
  },
};

/**
 * The export format a stored or returned value actually means.
 *
 * Never throws, because both inputs are untrusted runtime data: an API response and a
 * localStorage blob, either of which a build before this one could have written as `trello`.
 * A value this build does not recognise falls back to the default rather than producing a
 * blank Select label, which is the failure this guards against.
 */
export function normalizeExportFormat(value: unknown): ExportFormat {
  if (value === 'json' || value === 'markdown') return value;
  if (
    typeof value === 'string' &&
    Object.prototype.hasOwnProperty.call(RETIRED_EXPORT_FORMATS, value)
  ) {
    return RETIRED_EXPORT_FORMATS[value];
  }
  return DEFAULT_SETTINGS.export.defaultFormat;
}
