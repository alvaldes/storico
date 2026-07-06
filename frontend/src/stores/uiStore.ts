import { create } from 'zustand';

type Theme = 'light' | 'dark' | 'system';

interface UIState {
  theme: Theme;
  sidebarOpen: boolean;
  setTheme: (theme: Theme) => void;
  toggleTheme: () => void;
  setSidebarOpen: (open: boolean) => void;
  toggleSidebar: () => void;
}

function getSystemPreference(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches
    ? 'dark'
    : 'light';
}

function getStoredTheme(): Theme {
  if (typeof window === 'undefined') return 'system';
  const stored = localStorage.getItem('theme');
  if (stored === 'light' || stored === 'dark' || stored === 'system') {
    return stored;
  }
  return 'system';
}

function applyTheme(theme: Theme) {
  if (typeof document === 'undefined') return;
  const resolved = theme === 'system' ? getSystemPreference() : theme;
  document.documentElement.setAttribute('data-theme', resolved);
}

export const useUIStore = create<UIState>((set) => {
  const initialTheme = getStoredTheme();
  // Apply on init — runs once in browser
  if (typeof window !== 'undefined') {
    applyTheme(initialTheme);
  }

  return {
    theme: initialTheme,
    sidebarOpen: true,
    setTheme: (theme) => {
      localStorage.setItem('theme', theme);
      applyTheme(theme);
      set({ theme });
    },
    toggleTheme: () => {
      set((state) => {
        const next: Theme =
          state.theme === 'light'
            ? 'dark'
            : state.theme === 'dark'
              ? 'system'
              : 'light';
        localStorage.setItem('theme', next);
        applyTheme(next);
        return { theme: next };
      });
    },
    setSidebarOpen: (open) => set({ sidebarOpen: open }),
    toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  };
});
