import { useEffect, useState } from 'react';
import { Sun, Moon, Monitor } from 'lucide-react';
import { useUIStore } from '@/stores/uiStore';
import { cn } from '@/lib/utils';

export function ThemeToggle() {
  const { theme, toggleTheme } = useUIStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    // Prevent hydration mismatch: render a placeholder with the same size
    return (
      <button
        className="rounded-md p-2 text-(--color-text-secondary) hover:bg-(--color-surface-secondary) transition-colors"
        aria-label="Loading theme toggle"
        disabled
      >
        <Sun className="h-5 w-5" />
      </button>
    );
  }

  const Icon = theme === 'light' ? Sun : theme === 'dark' ? Moon : Monitor;

  return (
    <button
      onClick={toggleTheme}
      className={cn(
        'rounded-md p-2 transition-colors',
        'text-(--color-text-secondary) hover:bg-(--color-surface-secondary)',
        'focus:outline-none focus-visible:ring-2 focus-visible:ring-(--color-primary-500)',
      )}
      aria-label="Toggle theme"
      title={`Current: ${theme}. Click to switch.`}
    >
      <Icon className="h-5 w-5" />
    </button>
  );
}
