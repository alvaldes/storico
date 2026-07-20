export type LLMProvider = 'ollama' | 'openai' | 'anthropic' | 'gemini';

export interface OllamaConfig {
  baseUrl: string;
  model: string;
  temperature: number;
  maxTokens: number;
}

export interface OpenAIConfig {
  apiKey: string;
  model: string;
  temperature: number;
  maxTokens: number;
}

export interface AnthropicConfig {
  apiKey: string;
  model: string;
  temperature: number;
  maxTokens: number;
}

export interface GeminiConfig {
  apiKey: string;
  model: string;
  temperature: number;
  maxTokens: number;
}

export interface LLMConfig {
  provider: LLMProvider;
  ollama: OllamaConfig;
  openai: OpenAIConfig;
  anthropic: AnthropicConfig;
  gemini: GeminiConfig;
}

export type ExportFormat = 'trello' | 'json' | 'markdown';

export interface ExportConfig {
  defaultFormat: ExportFormat;
}

export interface AppSettings {
  llm: LLMConfig;
  export: ExportConfig;
}

export const DEFAULT_SETTINGS: AppSettings = {
  llm: {
    provider: 'ollama',
    ollama: {
      baseUrl: 'http://localhost:11434',
      model: 'llama3.2',
      temperature: 0.1,
      maxTokens: 2048,
    },
    openai: {
      apiKey: '',
      model: 'gpt-4o-mini',
      temperature: 0.1,
      maxTokens: 2048,
    },
    anthropic: {
      apiKey: '',
      model: 'claude-3-haiku',
      temperature: 0.1,
      maxTokens: 2048,
    },
    gemini: {
      apiKey: '',
      model: 'gemini-2.0-flash',
      temperature: 0.1,
      maxTokens: 2048,
    },
  },
  export: {
    defaultFormat: 'json',
  },
};
