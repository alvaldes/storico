import { useEffect } from 'react';
import { create } from 'zustand';
import {
  type Theme,
  getStoredTheme,
  getSystemPreference,
  resolveTheme,
  applyTheme,
} from '@/lib/theme';

interface UIState {
  theme: Theme;
  hydrated: boolean;
  sidebarOpen: boolean;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
}

/**
 * Theme is initialized to the deterministic value 'system' on BOTH the
 * server and the client so hydration renders match. The persisted
 * preference is read after mount (useThemeHydration) — reading it during
 * store creation was the hydration mismatch that forced every island to
 * client:only.
 */
export const useUIStore = create<UIState>((set) => ({
  theme: 'system',
  hydrated: false,
  sidebarOpen: true,
  setTheme: (theme) => {
    if (typeof window !== 'undefined') {
      localStorage.setItem('theme', theme);
      applyTheme(theme === 'system' ? getSystemPreference() : theme);
    }
    set({ theme });
  },
  toggleTheme: () => {
    // Resolve the current theme (ignoring 'system'), toggle to the opposite
    const resolved = resolveTheme();
    const next: 'light' | 'dark' = resolved === 'light' ? 'dark' : 'light';
    if (typeof window !== 'undefined') {
      localStorage.setItem('theme', next);
      applyTheme(next);
    }
    set({ theme: next });
  },
  setSidebarOpen: (open) => set({ sidebarOpen: open }),
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
}));

/**
 * Runs once per page load, after hydration. Reads the persisted theme and
 * syncs the store with it — pre-hydration the store says 'system' on both
 * sides, so no component can mismatch.
 *
 * ThemeScript already applied the resolved theme to <html> before first
 * paint; this keeps the store (and anything rendering it) in sync.
 */
export function useThemeHydration(): boolean {
  const hydrated = useUIStore((s) => s.hydrated);
  useEffect(() => {
    if (hydrated) return;
    const stored = getStoredTheme();
    applyTheme(stored === 'system' ? getSystemPreference() : stored);
    useUIStore.setState({ theme: stored, hydrated: true });
  }, [hydrated]);
  return hydrated;
}

/**
 * Resolved ('light' | 'dark') theme that is hydration-safe: it returns
 * 'light' until the store has hydrated, on both the server and the
 * client's first render.
 */
export function useResolvedTheme(): 'light' | 'dark' {
  const theme = useUIStore((s) => s.theme);
  const hydrated = useThemeHydration();
  if (!hydrated) return 'light';
  return theme === 'system' ? getSystemPreference() : theme;
}
