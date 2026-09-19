/**
 * Removal of localStorage keys that older builds of Storico wrote and nothing reads.
 *
 * The one that matters is `storico-settings`, the settings key from before
 * `storico-settings-v2` replaced it. Its `partialize` then was `{ settings }` in full, and
 * `settings.llm` held a plaintext `apiKey` per cloud provider — so an upgraded browser still
 * holds a credential with no owner, no reader and no expiry. The values must not be carried
 * forward; dropping the key is the whole fix.
 *
 * Called from two places on purpose, and both are idempotent:
 *
 *  - `stores/settingsStore.ts`, at module evaluation, for anything that imports the store; and
 *  - the bundled script in `components/astro/ThemeScript.astro`, which every layout includes,
 *    so a browser is cleaned on its first full page load **whichever** page that is. Without
 *    that second call the cleanup only ran for the subset of pages whose module graph reaches
 *    the store — today just `/account` — leaving the key in place for everyone else.
 */

/** The settings key written before `storico-settings-v2`. See the module note above. */
const LEGACY_SETTINGS_KEY = 'storico-settings';

/**
 * Drop the pre-`v2` settings payload.
 *
 * Best-effort by design. This runs during module evaluation and in a page script, and it also
 * runs on the server, where Astro renders these pages without a `localStorage` at all. A
 * `localStorage` that exists but refuses the call — Safari private mode, storage disabled by
 * policy — must not break store creation or a page render either. Both cases leave the key in
 * place, which is no worse than not having tried, and neither is worth failing over.
 */
export function dropLegacySettingsKey(): void {
  try {
    if (typeof localStorage === 'undefined') return;
    localStorage.removeItem(LEGACY_SETTINGS_KEY);
  } catch {
    // Storage unavailable or refusing. The stale key survives; the app is unaffected.
  }
}
