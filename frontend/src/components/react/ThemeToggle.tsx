import { useEffect, useState } from "react";
import { Sun, Moon, Monitor } from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";

export function ThemeToggle() {
  const { theme, toggleTheme } = useUIStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const Icon = mounted
    ? theme === "light"
      ? Moon
      : theme === "dark"
        ? Sun
        : Monitor
    : Sun;

  return (
    <button
      onClick={mounted ? toggleTheme : undefined}
      className={cn(
        "rounded-md p-2 transition-colors",
        "text-(--color-text-secondary) hover:bg-(--color-surface-secondary)",
        mounted &&
          "focus:outline-none focus-visible:ring-2 focus-visible:ring-(--color-primary-500)",
      )}
      aria-label={mounted ? "Toggle theme" : "Loading theme toggle"}
      {...(mounted ? { title: `Current: ${theme}. Click to switch.` } : {})}
    >
      <Icon className="h-5 w-5" />
    </button>
  );
}
