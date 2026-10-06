import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import { THEME_BRIDGE_SCRIPT, mapTheme } from '@/lib/theme-bridge';

/**
 * The two storage keys the bridge touches. `theme` is the app's key — the single
 * source of truth, owned by `src/lib/theme.ts`. `starlight-theme` is Starlight's
 * own key, mirrored so Starlight's ThemeProvider (which re-runs in the head after
 * the bridge and rewrites `data-theme` from it) always agrees with the app.
 */
const APP_KEY = 'theme';
const STARLIGHT_KEY = 'starlight-theme';

describe('mapTheme', () => {
  it('keeps an explicit light preference as itself in both directions', () => {
    // An explicit app value must survive verbatim: Starlight's ThemeProvider reads
    // `starlight-theme` as a truthy literal and applies exactly that theme.
    expect(mapTheme('light', 'dark')).toEqual({ dataTheme: 'light', starlightTheme: 'light' });
    expect(mapTheme('light', 'light')).toEqual({ dataTheme: 'light', starlightTheme: 'light' });
  });

  it('keeps an explicit dark preference as itself in both directions', () => {
    expect(mapTheme('dark', 'light')).toEqual({ dataTheme: 'dark', starlightTheme: 'dark' });
    expect(mapTheme('dark', 'dark')).toEqual({ dataTheme: 'dark', starlightTheme: 'dark' });
  });

  it("resolves 'system' through the system preference and mirrors starlight-theme to ''", () => {
    // '' is the exact value whose *absence* makes Starlight's own ThemeProvider
    // fall through to the same system preference, so both surfaces resolve
    // identically without the bridge ever lying about an explicit choice.
    expect(mapTheme('system', 'dark')).toEqual({ dataTheme: 'dark', starlightTheme: '' });
    expect(mapTheme('system', 'light')).toEqual({ dataTheme: 'light', starlightTheme: '' });
  });
});

describe('THEME_BRIDGE_SCRIPT', () => {
  beforeEach(() => {
    localStorage.clear();
    // The setup.ts mock always reports "not dark"; tests that need the dark
    // preference stub it explicitly.
    stubSystemPreference('light');
  });

  afterEach(() => {
    // Restore the setup.ts matchMedia mock for the tests that follow.
    window.matchMedia = originalMatchMedia;
  });

  const originalMatchMedia = window.matchMedia;

  function stubSystemPreference(preference: 'light' | 'dark') {
    // setup.ts defines `window.matchMedia` writable, so a direct assignment is the
    // reliable way to reach the property the bridge script actually reads.
    window.matchMedia = ((query: string) => ({
      matches:
        query.replace(/\s+/g, '') === '(prefers-color-scheme:dark)' && preference === 'dark',
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }

  function runBridge() {
    // The script is shipped as an inline `<script>` body; running it through
    // `new Function` against jsdom's window/document is the closest a unit test
    // gets to what the browser does with it.
    // eslint-disable-next-line @typescript-eslint/no-implied-eval, no-new-func
    new Function(THEME_BRIDGE_SCRIPT)();
  }

  it('is a self-contained IIFE with no imports or awaits', () => {
    expect(THEME_BRIDGE_SCRIPT.startsWith('(function')).toBe(true);
    expect(THEME_BRIDGE_SCRIPT.endsWith(')()')).toBe(true);
    expect(THEME_BRIDGE_SCRIPT).not.toMatch(/\bimport\b|\bawait\b|\brequire\b/);
  });

  it("references the app's storage key, the data-theme attribute, and the mirrored starlight-theme key", () => {
    // A rename of any of these three strings must break this test: each one is a
    // contract point with either src/lib/theme.ts or Starlight's ThemeProvider.
    expect(THEME_BRIDGE_SCRIPT).toContain(`localStorage.getItem('${APP_KEY}')`);
    expect(THEME_BRIDGE_SCRIPT).toContain('data-theme');
    expect(THEME_BRIDGE_SCRIPT).toContain(STARLIGHT_KEY);
    expect(THEME_BRIDGE_SCRIPT).toContain('prefers-color-scheme');
  });

  it('applies an explicit dark preference to both surfaces', () => {
    localStorage.setItem(APP_KEY, 'dark');
    runBridge();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem(STARLIGHT_KEY)).toBe('dark');
  });

  it('applies an explicit light preference to both surfaces', () => {
    localStorage.setItem(APP_KEY, 'light');
    runBridge();
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem(STARLIGHT_KEY)).toBe('light');
  });

  it("resolves a stored 'system' value through the system preference and mirrors ''", () => {
    localStorage.setItem(APP_KEY, 'system');
    stubSystemPreference('dark');
    runBridge();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem(STARLIGHT_KEY)).toBe('');
  });

  it('treats an absent key as system', () => {
    stubSystemPreference('light');
    runBridge();
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem(STARLIGHT_KEY)).toBe('');
  });

  it('treats an unknown stored value as system, never as a theme', () => {
    localStorage.setItem(APP_KEY, 'purple');
    stubSystemPreference('dark');
    runBridge();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
    expect(localStorage.getItem(STARLIGHT_KEY)).toBe('');
  });
});
