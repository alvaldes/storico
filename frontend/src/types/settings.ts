export type ExportFormat = 'trello' | 'json' | 'markdown';

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
