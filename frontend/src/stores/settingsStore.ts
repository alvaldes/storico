import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import {
  type AppSettings,
  type LLMProvider,
  type ExportFormat,
  DEFAULT_SETTINGS,
} from '@/types/settings';
import { fetchSettings, saveSettings } from '@/lib/settings-api';

interface SettingsState {
  settings: AppSettings;
  apiLoaded: boolean;
  apiSaving: boolean;
  apiError: string | null;
  loadFromApi: () => Promise<void>;
  syncToApi: () => Promise<void>;
  setLLMProvider: (provider: LLMProvider) => void;
  setOllamaConfig: (config: Partial<AppSettings['llm']['ollama']>) => void;
  setOpenAIConfig: (config: Partial<AppSettings['llm']['openai']>) => void;
  setAnthropicConfig: (config: Partial<AppSettings['llm']['anthropic']>) => void;
  setExportFormat: (format: ExportFormat) => void;
  resetSettings: () => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      settings: DEFAULT_SETTINGS,
      apiLoaded: false,
      apiSaving: false,
      apiError: null,

      loadFromApi: async () => {
        try {
          const response = await fetchSettings();
          set({
            settings: response.preferences,
            apiLoaded: true,
            apiError: null,
          });
        } catch {
          // API unavailable — keep localStorage cache
          set({ apiLoaded: true, apiError: null });
        }
      },

      syncToApi: async () => {
        const { settings } = get();
        set({ apiSaving: true, apiError: null });
        try {
          await saveSettings(settings);
          set({ apiSaving: false });
        } catch (e) {
          const message = e instanceof Error ? e.message : 'Failed to save settings';
          set({ apiSaving: false, apiError: message });
        }
      },

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
      // Only persist the settings field, not API state
      partialize: (state) => ({ settings: state.settings }),
    },
  ),
);
