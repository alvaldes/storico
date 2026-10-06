/**
 * Theme bridge — Starlight pages honour the app's theme storage.
 *
 * The app keeps its theme under `theme` (`'light' | 'dark' | 'system'`, see
 * `src/lib/theme.ts` — the single source of truth, unchanged by this module).
 * Starlight keeps its own under `starlight-theme` (`'light' | 'dark' | ''`, where
 * `''` means "follow the system") and BOTH write `data-theme` on the same
 * `<html>`. Without this bridge the two switches disagree in both directions.
 *
 * The bridge is strictly one-way: the app's key wins. It is consumed by:
 *  - `src/components/starlight/Head.astro` — injects `THEME_BRIDGE_SCRIPT` inline
 *    in the head of every docs page, before Starlight's own ThemeProvider script.
 *  - `src/components/starlight/ThemeSelect.astro` — writes the app's key on change.
 */

import type { Theme } from './theme';

/** Starlight's own preference values: `''` means "follow the system". */
export type StarlightThemePreference = 'light' | 'dark' | '';

export interface ThemeBridgeMapping {
  /** What to write to `data-theme` on `<html>` — always concrete. */
  dataTheme: 'light' | 'dark';
  /**
   * What to mirror into `starlight-theme`. `''` is deliberate: Starlight's
   * ThemeProvider treats an absent/empty value as "resolve from the same system
   * preference", so a system preference is never recorded as an explicit choice.
   */
  starlightTheme: StarlightThemePreference;
}

/**
 * Pure mapping from the app's `Theme` to both storage surfaces.
 * `systemPreference` must be provided by the caller (`matchMedia` is a browser
 * concern; this function stays pure and testable).
 */
export function mapTheme(
  theme: Theme,
  systemPreference: 'light' | 'dark',
): ThemeBridgeMapping {
  if (theme === 'system') {
    return { dataTheme: systemPreference, starlightTheme: '' };
  }
  return { dataTheme: theme, starlightTheme: theme };
}

/**
 * Anti-flash inline bridge script for Starlight pages (self-contained, no imports).
 *
 * Starlight's layout hardcodes `data-theme="dark"` on the server-rendered `<html>`
 * and its ThemeProvider inline script (which also lives in the head, after ours)
 * re-derives `data-theme` from `starlight-theme`. This script therefore does two
 * things before first paint: applies the app's resolved theme, and mirrors the
 * app's preference into `starlight-theme` so the later ThemeProvider run agrees.
 *
 * This exact code is injected via `src/components/starlight/Head.astro` as an
 * `is:inline` script. Keep in sync if changed.
 */
export const THEME_BRIDGE_SCRIPT = `(function(){var s=null;try{s=localStorage.getItem('theme')}catch(e){}var t=s==='light'||s==='dark'?s:'system';if(t==='system'){t=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}document.documentElement.setAttribute('data-theme',t);try{localStorage.setItem('starlight-theme',s==='light'||s==='dark'?s:'')}catch(e){}})()`;
