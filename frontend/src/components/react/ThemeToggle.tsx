import { useEffect, useState } from "react";
import { Sun, Moon, Monitor } from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";
import { useTranslations, type Locale } from "@/i18n/utils";

export function ThemeToggle({ locale = 'en' }: { locale?: Locale }) {
  const t = useTranslations(locale);
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
      aria-label={mounted ? (t.theme?.toggle ?? "Toggle theme") : (t.theme?.loadingToggle ?? "Loading theme toggle")}
      {...(mounted ? { title: (t.theme?.currentTheme ?? "Current: {theme}. Click to switch.").replace("{theme}", theme) } : {})}
    >
      <Icon className="h-5 w-5" />
    </button>
  );
}
