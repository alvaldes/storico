import { useEffect, useState } from "react";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import {
  CircleCheckIcon,
  InfoIcon,
  TriangleAlertIcon,
  OctagonXIcon,
  Loader2Icon,
} from "lucide-react";

const Toaster = ({ ...props }: ToasterProps) => {
  const [theme, setTheme] = useState<"light" | "dark" | "system">("system");

  // Detect theme from <html> class since we don't use next-themes ThemeProvider
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
          "--normal-bg": "var(--color-surface-secondary)",
          "--normal-text": "var(--color-text)",
          "--normal-border": "var(--color-border)",
          "--border-radius": "var(--radius-md)",
          zIndex: 9999,
          right: "16px",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast:
            "cn-toast bg-(--color-surface) backdrop-blur-md text-(--color-text) border border-(--color-border) shadow-xl",
        },
      }}
      {...props}
    />
  );
};

export { Toaster };
