/**
 * Shared theme utility for Storico.
 *
 * SINGLE SOURCE OF TRUTH for all theme operations.
 * Used by:
 *  - PublicLayout / index.astro (vanilla JS via bundled <script>)
 *  - MainLayout / Zustand uiStore (imported directly)
 *
 * All systems MUST read/write localStorage('theme') with the same format.
 */

export type Theme = 'light' | 'dark' | 'system';

// ── Storage ─────────────────────────────────────────────────────

export function getStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'system';
  const stored = localStorage.getItem('theme');
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored;
  }
  return 'system';
}

export function getSystemPreference(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

export function resolveTheme(): 'light' | 'dark' {
  const stored = getStoredTheme();
  return stored === 'system' ? getSystemPreference() : stored;
}

// ── DOM ─────────────────────────────────────────────────────────

export function applyTheme(theme: 'light' | 'dark') {
  if (typeof document === 'undefined') return;
  document.documentElement.setAttribute('data-theme', theme);
}

export function applyStoredTheme() {
  applyTheme(resolveTheme());
}

/**
 * Toggle between 'light' and 'dark' only.
 * 'system' resolves to the actual preference, THEN toggles to the opposite.
 * This keeps the toggle predictable (1 click = 1 visible change).
 * The 'system' mode is set from settings/preferences, not from the toggle.
 */
export function toggleTheme(): 'light' | 'dark' {
  const resolved = resolveTheme();
  const next: 'light' | 'dark' = resolved === 'light' ? 'dark' : 'light';
  localStorage.setItem('theme', next);
  applyTheme(next);
  return next;
}

// ── View Transition helpers ─────────────────────────────────────

export function onBeforeSwap(e: Event) {
  const evt = e as CustomEvent<{ newDocument: Document }>;
  evt.detail.newDocument.documentElement.dataset.theme = resolveTheme();
}

export function onAfterSwap() {
  applyTheme(resolveTheme());
}

/**
 * Respond to OS-level preference changes (only when in 'system' mode).
 */
export function onSystemPreferenceChange() {
  const stored = localStorage.getItem('theme');
  if (!stored || stored === 'system') {
    applyTheme(resolveTheme());
  }
}

// ── Anti-flash inline (self-contained, no imports) ──────────────
// This exact code is used in ThemeAntiFlash.astro as an is:inline script.
// Keep in sync if changed.
export const ANTI_FLASH_SCRIPT = `(function(){var s=localStorage.getItem('theme');var t=s||'system';if(t==='system'){t=window.matchMedia('(prefers-color-scheme:dark)').matches?'dark':'light'}document.documentElement.setAttribute('data-theme',t)})()`;
