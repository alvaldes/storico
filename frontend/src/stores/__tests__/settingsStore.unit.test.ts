import { beforeEach, describe, expect, it, vi } from 'vitest';

import { useSettingsStore } from '@/stores/settingsStore';
import { DEFAULT_SETTINGS } from '@/types/settings';
import { fetchSettings, saveSettings } from '@/lib/settings-api';
import { toast } from 'sonner';

vi.mock('@/lib/settings-api', () => ({
  fetchSettings: vi.fn(),
  saveSettings: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { loading: vi.fn(() => 'toast-id'), success: vi.fn(), error: vi.fn() },
}));

/** The copy a caller supplies; the store owns none of its own. */
const LABELS = {
  loading: 'Saving preferences…',
  success: 'Preferences saved',
  successDesc: 'Saved to your account.',
  error: 'Could not save preferences',
};

describe('useSettingsStore — the shape it carries', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useSettingsStore.setState({ settings: DEFAULT_SETTINGS, apiLoaded: false });
  });

  it('carries no per-user LLM configuration', () => {
    // The property, not just the absence of a hardcoded value: this store used to hold a
    // provider selection plus a model/api_key/base_url per provider, and nothing read it.
    expect(Object.keys(useSettingsStore.getState().settings)).toEqual(['export']);
  });

  it('hides the API key from every setter it exposes', () => {
    // The four llm setters are gone; a rename that re-adds one would fail here. Filtered by
    // type as well as prefix, because the state object itself is named `settings`.
    const setters = Object.entries(useSettingsStore.getState())
      .filter(([key, value]) => key.startsWith('set') && typeof value === 'function')
      .map(([key]) => key);
    expect(setters).toEqual(['setExportFormat']);
  });
});

describe('useSettingsStore — saving preferences', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(saveSettings).mockResolvedValue({
      preferences: { export: { defaultFormat: 'markdown' } },
      updated_at: '2026-01-01T00:00:00Z',
    });
    useSettingsStore.setState({ settings: DEFAULT_SETTINGS, apiSaving: false, lastSaveResult: 'idle' });
  });

  it('sends the current settings and reports with the caller’s copy', async () => {
    useSettingsStore.getState().setExportFormat('markdown');

    await useSettingsStore.getState().syncToApi(LABELS);

    expect(saveSettings).toHaveBeenCalledWith({ export: { defaultFormat: 'markdown' } });
    expect(toast.success).toHaveBeenCalledWith(
      'Preferences saved',
      expect.objectContaining({ description: 'Saved to your account.' }),
    );
    expect(useSettingsStore.getState().lastSaveResult).toBe('success');
  });

  it('reports a failure with the caller’s copy and keeps the state unsaved', async () => {
    vi.mocked(saveSettings).mockRejectedValue(new Error('the API is down'));

    await useSettingsStore.getState().syncToApi(LABELS);

    expect(toast.error).toHaveBeenCalledWith(
      'Could not save preferences',
      // The backend's own words stay the description, so a real cause is not hidden.
      expect.objectContaining({ description: 'the API is down' }),
    );
    expect(useSettingsStore.getState().lastSaveResult).toBe('error');
    expect(useSettingsStore.getState().apiSaving).toBe(false);
  });

  it('loads what the API returns', async () => {
    vi.mocked(fetchSettings).mockResolvedValue({
      preferences: { export: { defaultFormat: 'trello' } },
      updated_at: '2026-01-01T00:00:00Z',
    });

    await useSettingsStore.getState().loadFromApi();

    expect(useSettingsStore.getState().settings.export.defaultFormat).toBe('trello');
    expect(useSettingsStore.getState().apiLoaded).toBe(true);
  });

  it('stays usable when the API cannot be read', async () => {
    // The page still renders from defaults rather than failing to load.
    vi.mocked(fetchSettings).mockRejectedValue(new Error('offline'));

    await useSettingsStore.getState().loadFromApi();

    expect(useSettingsStore.getState().apiLoaded).toBe(true);
    expect(useSettingsStore.getState().settings).toEqual(DEFAULT_SETTINGS);
  });
});

describe('useSettingsStore — the legacy persisted key', () => {
  // The key an older build wrote. `partialize` then was `{ settings: state.settings }`, and
  // `settings.llm` held a plaintext `apiKey` per cloud provider, so this is a credential
  // sitting in browser storage with no reader and no expiry.
  const LEGACY_KEY = 'storico-settings';

  beforeEach(() => {
    localStorage.clear();
  });

  it('removes the legacy key, which may still hold plaintext API keys', async () => {
    localStorage.setItem(
      LEGACY_KEY,
      JSON.stringify({
        state: {
          settings: {
            llm: {
              provider: 'openai',
              openai: { apiKey: 'sk-legacy-secret', model: 'gpt-4o-mini' },
              anthropic: { apiKey: 'sk-ant-legacy-secret' },
            },
          },
        },
        version: 0,
      }),
    );

    vi.resetModules();
    await import('@/stores/settingsStore');

    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it('leaves the live keys alone', async () => {
    // A test that only asserted the removal would pass even if the cleanup wiped every key.
    localStorage.setItem(LEGACY_KEY, '{"state":{}}');
    localStorage.setItem('storico-settings-v2', '{"state":{"settings":{}}}');
    localStorage.setItem('theme', 'dark');

    vi.resetModules();
    await import('@/stores/settingsStore');

    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
    expect(localStorage.getItem('storico-settings-v2')).not.toBeNull();
    expect(localStorage.getItem('theme')).toBe('dark');
  });

  it('does not stop the module loading when storage refuses the removal', async () => {
    // Safari private mode and storage-disabled policies throw instead of returning.
    const spy = vi
      .spyOn(Storage.prototype, 'removeItem')
      .mockImplementation(() => {
        throw new DOMException('the operation is insecure', 'SecurityError');
      });

    vi.resetModules();
    await expect(import('@/stores/settingsStore')).resolves.toBeDefined();

    spy.mockRestore();
  });

  it('does not stop the module loading on the server, where storage does not exist', async () => {
    // Astro renders these pages server-side, so the module is evaluated without a `localStorage`.
    vi.stubGlobal('localStorage', undefined);

    vi.resetModules();
    await expect(import('@/stores/settingsStore')).resolves.toBeDefined();

    vi.unstubAllGlobals();
  });
});
