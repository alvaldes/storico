import { useEffect, useState } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import {
  CircleCheckIcon,
  InfoIcon,
  TriangleAlertIcon,
  OctagonXIcon,
  Loader2Icon,
} from "lucide-react";

/**
 * Toaster component — follows the shadcn/ui pattern (see shadcn/ui docs,
 * registry `@shadcn/sonner`).
 *
 * The base CSS (position:fixed, offsets, theme colors, icons, animations) is
 * NOT provided inline here. It is loaded via a `<link data-astro-transition-persist>`
 * in the layout (MainLayout.astro), which points to the sonner CSS copied by
 * Vite's `?url` import.
 *
 * Why: Astro View Transitions' `swapHeadElements()` strips every `<head>`
 * element that isn't `link[rel=stylesheet]` or marked
 * `data-astro-transition-persist`. Sonner v2 injects its CSS at runtime via
 * `__insertCSS()` into a `<style>` tag — that tag is removed on the first
 * navigation, and since the module is cached `__insertCSS` never re-runs, so
 * the toaster loses position:fixed, offsets, theme colors, icons, and
 * animations. Pinning the CSS through a persisted `<link>` is the
 * shadcn-friendly fix and removes the need for any inline patches.
 *
 * Theming: this project does not use next-themes; we read the theme from the
 * <html> class (set by ThemeScript + ThemeToggle), matching the existing dark
 * mode implementation. shadcn's own next-themes hook is replaced with a
 * MutationObserver here.
 *
 * Tokens: shadcn's sonner template references `--popover`, `--popover-fg`,
 * `--border` and `--radius`. We map them to this project's design tokens
 * (see globals.css): --popover -> --color-surface, --popover-foreground ->
 * --color-text, --border -> --color-border, --radius -> --radius-md.
 *
 * @see https://ui.shadcn.com/docs/components/base/sonner
 * @see https://sonner.emilkowal.ski
 */
const Toaster = ({ ...props }: ToasterProps) => {
  const [theme, setTheme] = useState<"light" | "dark" | "system">("system");

  // Detect theme from <html> class since we don't use next-themes ThemeProvider.
  useEffect(() => {
    const html = document.documentElement;
    const update = () => {
      setTheme(html.classList.contains("dark") ? "dark" : "light");
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(html, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);

  return (
    <Sonner
      theme={theme as ToasterProps["theme"]}
      className="toaster group"
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      position="top-right"
      offset="80px"
      style={
        {
          "--normal-bg": "var(--popover)",
          "--normal-text": "var(--popover-foreground)",
          "--normal-border": "var(--border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
