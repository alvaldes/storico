import { beforeEach, describe, expect, it, vi } from 'vitest';

import { dropLegacySettingsKey } from '@/lib/legacy-storage-cleanup';

/**
 * The key an older build persisted under. `partialize` then was `{ settings }` in full, and
 * `settings.llm` held a plaintext `apiKey` per cloud provider — so this is a credential sitting
 * in browser storage with no reader and no expiry.
 */
const LEGACY_KEY = 'storico-settings';

describe('dropLegacySettingsKey', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('removes the legacy key that may hold plaintext API keys', () => {
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

    dropLegacySettingsKey();

    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it('leaves every live key alone', () => {
    // A test that only asserted the removal would pass even if the cleanup wiped all of storage.
    localStorage.setItem(LEGACY_KEY, '{"state":{}}');
    localStorage.setItem('storico-settings-v2', '{"state":{"settings":{}}}');
    localStorage.setItem('workspace-storage', '{"state":{"currentWorkspace":"ws-1"}}');
    localStorage.setItem('theme', 'dark');

    dropLegacySettingsKey();

    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
    expect(localStorage.getItem('storico-settings-v2')).not.toBeNull();
    expect(localStorage.getItem('workspace-storage')).not.toBeNull();
    expect(localStorage.getItem('theme')).toBe('dark');
  });

  it('is safe to call twice, which two call sites rely on', () => {
    localStorage.setItem(LEGACY_KEY, '{"state":{}}');

    dropLegacySettingsKey();
    expect(() => dropLegacySettingsKey()).not.toThrow();
    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it('does something when the key is absent, which is the normal case', () => {
    expect(() => dropLegacySettingsKey()).not.toThrow();
    expect(localStorage.getItem(LEGACY_KEY)).toBeNull();
  });

  it('does not throw on the server, where storage does not exist', () => {
    // Astro renders these pages server-side, so both call sites run without a `localStorage`.
    vi.stubGlobal('localStorage', undefined);

    expect(() => dropLegacySettingsKey()).not.toThrow();

    vi.unstubAllGlobals();
  });

  it('does not throw when storage exists but refuses the call', () => {
    // Safari private mode and storage-disabled policies throw instead of returning.
    localStorage.setItem(LEGACY_KEY, '{"state":{}}');
    const spy = vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('the operation is insecure', 'SecurityError');
    });

    expect(() => dropLegacySettingsKey()).not.toThrow();
    // The call was really attempted and really swallowed — not skipped by an early return.
    expect(spy).toHaveBeenCalledWith(LEGACY_KEY);

    spy.mockRestore();
    // The key survives, which is the honest outcome: nothing was removed.
    expect(localStorage.getItem(LEGACY_KEY)).not.toBeNull();
  });
});
