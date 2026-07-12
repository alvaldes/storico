import { create } from "zustand";
import { persist } from "zustand/middleware";
import { toast } from "sonner";
import {
  type AppSettings,
  type LLMProvider,
  type ExportFormat,
  DEFAULT_SETTINGS,
} from "@/types/settings";
import { fetchSettings, saveSettings } from "@/lib/settings-api";

type SaveResult = "idle" | "success" | "error";

export interface ToastLabels {
  loading: string;
  success: string;
  successDesc: string;
  error: string;
}

interface SettingsState {
  settings: AppSettings;
  apiLoaded: boolean;
  apiSaving: boolean;
  lastSaveResult: SaveResult;
  loadFromApi: () => Promise<void>;
  syncToApi: (toastLabels?: ToastLabels) => Promise<void>;
  setLLMProvider: (provider: LLMProvider) => void;
  setOllamaConfig: (config: Partial<AppSettings["llm"]["ollama"]>) => void;
  setOpenAIConfig: (config: Partial<AppSettings["llm"]["openai"]>) => void;
  setAnthropicConfig: (
    config: Partial<AppSettings["llm"]["anthropic"]>,
  ) => void;
  setExportFormat: (format: ExportFormat) => void;
  resetSettings: () => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      settings: DEFAULT_SETTINGS,
      apiLoaded: false,
      apiSaving: false,
      lastSaveResult: "idle",

      loadFromApi: async () => {
        try {
          const response = await fetchSettings();
          set({
            settings: response.preferences,
            apiLoaded: true,
          });
        } catch {
          // API unavailable — settings from defaults + localStorage
          set({ apiLoaded: true });
        }
      },

      syncToApi: async (toastLabels) => {
        const { settings } = get();
        const t = toastLabels ?? {
          loading: "Saving LLM configuration…",
          success: "LLM configuration saved",
          successDesc: "Settings saved to database",
          error: "Could not save settings",
        };
        set({ apiSaving: true, lastSaveResult: "idle" });
        const toastId = toast.loading(t.loading);
        try {
          await saveSettings(settings);
          set({ apiSaving: false, lastSaveResult: "success" });
          toast.success(t.success, {
            id: toastId,
            description: t.successDesc,
          });
          // Reset button state after 3s
          setTimeout(() => {
            const { lastSaveResult } = get();
            if (lastSaveResult === "success") set({ lastSaveResult: "idle" });
          }, 3000);
        } catch (e) {
          const message =
            e instanceof Error ? e.message : "Failed to save settings";
          set({ apiSaving: false, lastSaveResult: "error" });
          toast.error(t.error, {
            id: toastId,
            description: message,
          });
          // Reset button state after 4s
          setTimeout(() => {
            const { lastSaveResult } = get();
            if (lastSaveResult === "error") set({ lastSaveResult: "idle" });
          }, 4000);
        }
      },

      setLLMProvider: (provider) =>
        set((state) => ({
          settings: {
            ...state.settings,
            llm: { ...state.settings.llm, provider },
          },
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
      // New key — old 'storico-settings' still has API keys persisted, clean slate
      name: "storico-settings-v2",
      // Persist only export config (not LLM — API keys don't belong in localStorage)
      partialize: (state) => ({
        settings: { export: state.settings.export },
      }),
      // Default merge is shallow — deep-merge settings so llm comes from current state
      merge: (persisted, current) => {
        const p = persisted as { settings?: Partial<AppSettings> } | undefined;
        if (!p?.settings) return current;
        return {
          ...current,
          settings: { ...current.settings, ...p.settings },
        };
      },
    },
  ),
);
