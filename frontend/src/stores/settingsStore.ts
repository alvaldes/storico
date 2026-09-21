import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { toast } from 'sonner';
import { type AppSettings, type ExportFormat, DEFAULT_SETTINGS, normalizeExportFormat } from '@/types/settings';
import { fetchSettings, saveSettings } from '@/lib/settings-api';
import { dropLegacySettingsKey } from '@/lib/legacy-storage-cleanup';

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

/**
 * Run the legacy-key cleanup at module evaluation, so importing this store is enough.
 *
 * The cleanup itself lives in `@/lib/legacy-storage-cleanup` because the page script in
 * `ThemeScript.astro` calls it as well: this store is only imported by `/account`, so on its
 * own it would leave the pre-`v2` key — which held a plaintext API key per cloud provider — in
 * every browser that never visits that page. Idempotent, so both call sites are safe.
 */
dropLegacySettingsKey();

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
            // The response is untrusted runtime data: a build before this one could have
            // served a format this build no longer offers, and the Select would render blank.
            settings: {
              ...response.preferences,
              export: {
                ...response.preferences?.export,
                defaultFormat: normalizeExportFormat(
                  response.preferences?.export?.defaultFormat,
                ),
              },
            },
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
        const persistedExport = p.settings.export;
        return {
          ...current,
          settings: {
            ...current.settings,
            ...p.settings,
            // The persisted blob is untrusted too: `trello` is exactly what a browser that
            // visited the old /account page holds under `storico-settings-v2`.
            export: persistedExport
              ? {
                  ...current.settings.export,
                  ...persistedExport,
                  defaultFormat: normalizeExportFormat(persistedExport.defaultFormat),
                }
              : current.settings.export,
          },
        };
      },
    },
  ),
);
