import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { toast } from 'sonner';
import { type AppSettings, type ExportFormat, DEFAULT_SETTINGS } from '@/types/settings';
import { fetchSettings, saveSettings } from '@/lib/settings-api';

type SaveResult = 'idle' | 'success' | 'error';

/**
 * The copy a save reports with, supplied by the caller.
 *
 * The store owns no user-facing text. Its defaults used to be hardcoded English strings
 * ("Saving LLM configuration…"), which had two problems: they would have surfaced untranslated
 * in a Spanish UI, and they described an LLM configuration this store no longer carries.
 */
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
  syncToApi: (toastLabels: ToastLabels) => Promise<void>;
  setExportFormat: (format: ExportFormat) => void;
  resetSettings: () => void;
}

export const useSettingsStore = create<SettingsState>()(
  persist(
    (set, get) => ({
      settings: DEFAULT_SETTINGS,
      apiLoaded: false,
      apiSaving: false,
      lastSaveResult: 'idle',

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
        set({ apiSaving: true, lastSaveResult: 'idle' });
        const toastId = toast.loading(toastLabels.loading);
        try {
          await saveSettings(settings);
          set({ apiSaving: false, lastSaveResult: 'success' });
          toast.success(toastLabels.success, {
            id: toastId,
            description: toastLabels.successDesc,
          });
          // Reset button state after 3s
          setTimeout(() => {
            const { lastSaveResult } = get();
            if (lastSaveResult === 'success') set({ lastSaveResult: 'idle' });
          }, 3000);
        } catch (e) {
          const message = e instanceof Error ? e.message : toastLabels.error;
          set({ apiSaving: false, lastSaveResult: 'error' });
          toast.error(toastLabels.error, {
            id: toastId,
            description: message,
          });
          // Reset button state after 4s
          setTimeout(() => {
            const { lastSaveResult } = get();
            if (lastSaveResult === 'error') set({ lastSaveResult: 'idle' });
          }, 4000);
        }
      },

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
      // New key — old 'storico-settings' still has per-user LLM API keys persisted, clean slate
      name: 'storico-settings-v2',
      // Persist only export config: the API keys that used to live here do not belong in
      // localStorage, and the server no longer carries a per-user copy of them either.
      partialize: (state) => ({
        settings: { export: state.settings.export },
      }),
      // Default merge is shallow — deep-merge settings so the shape comes from current state
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
