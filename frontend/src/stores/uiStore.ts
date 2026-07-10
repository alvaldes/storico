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
  sidebarOpen: boolean;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
}

export const useUIStore = create<UIState>((set) => {
  const initialTheme = getStoredTheme();
  // Apply on init — runs once in browser
  if (typeof window !== 'undefined') {
    applyTheme(
      initialTheme === 'system' ? getSystemPreference() : initialTheme,
    );
  }

  return {
    theme: initialTheme,
    sidebarOpen: true,
    setTheme: (theme) => {
      localStorage.setItem('theme', theme);
      applyTheme(theme === 'system' ? getSystemPreference() : theme);
      set({ theme });
    },
    toggleTheme: () => {
      // Resolve current (ignoring 'system'), toggle to opposite
      const resolved = resolveTheme();
      const next: 'light' | 'dark' =
        resolved === 'light' ? 'dark' : 'light';
      localStorage.setItem('theme', next);
      applyTheme(next);
      set({ theme: next });
    },
    setSidebarOpen: (open) => set({ sidebarOpen: open }),
    toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  };
});
