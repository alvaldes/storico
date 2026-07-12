import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  type AppSettings,
  type LLMProvider,
  type ExportFormat,
  DEFAULT_SETTINGS,
} from '@/types/settings';

interface SettingsState {
  settings: AppSettings;
  setLLMProvider: (provider: LLMProvider) => void;
  setOllamaConfig: (config: Partial<AppSettings['llm']['ollama']>) => void;
  setOpenAIConfig: (config: Partial<AppSettings['llm']['openai']>) => void;
  setAnthropicConfig: (config: Partial<AppSettings['llm']['anthropic']>) => void;
  setExportFormat: (format: ExportFormat) => void;
  resetSettings: () => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set) => ({
      settings: DEFAULT_SETTINGS,

      setLLMProvider: (provider) =>
        set((state) => ({
          settings: { ...state.settings, llm: { ...state.settings.llm, provider } },
        })),

      setOllamaConfig: (config) =>
        set((state) => ({
          settings: {
            ...state.settings,
            llm: {
              ...state.settings.llm,
              ollama: { ...state.settings.llm.ollama, ...config },
            },
          },
        })),

      setOpenAIConfig: (config) =>
        set((state) => ({
          settings: {
            ...state.settings,
            llm: {
              ...state.settings.llm,
              openai: { ...state.settings.llm.openai, ...config },
            },
          },
        })),

      setAnthropicConfig: (config) =>
        set((state) => ({
          settings: {
            ...state.settings,
            llm: {
              ...state.settings.llm,
              anthropic: { ...state.settings.llm.anthropic, ...config },
            },
          },
        })),

      setExportFormat: (defaultFormat) =>
        set((state) => ({
          settings: {
            ...state.settings,
            export: { ...state.settings.export, defaultFormat },
          },
        })),

      resetSettings: () => set({ settings: DEFAULT_SETTINGS }),
    }),
    {
      name: 'storico-settings',
    },
  ),
);
