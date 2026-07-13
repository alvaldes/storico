"use client";

import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import { Button } from "@/components/ui/button";
import { Menu, LayoutDashboard, FileText, KanbanSquare, Upload, Settings } from "lucide-react";
import { useTranslations, localizedPath, type Locale } from "@/i18n/utils";

interface MobileNavDropdownProps {
  locale: Locale;
  currentPath: string;
}

const navItems = [
  { href: (l: Locale) => localizedPath("/dashboard", l), icon: LayoutDashboard, key: "dashboard" as const },
  { href: (l: Locale) => localizedPath("/stories", l), icon: FileText, key: "stories" as const },
  { href: (l: Locale) => localizedPath("/kanban", l), icon: KanbanSquare, key: "kanban" as const },
  { href: (l: Locale) => localizedPath("/export", l), icon: Upload, key: "export" as const },
  { href: (l: Locale) => localizedPath("/settings", l), icon: Settings, key: "settings" as const },
];

export function MobileNavDropdown({ locale, currentPath }: MobileNavDropdownProps) {
  const t = useTranslations(locale);
  const nav = t.nav;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger
        render={
          <Button
            variant="ghost"
            size="icon"
            className="lg:hidden"
            aria-label={nav.dashboard}
          >
            <Menu className="h-5 w-5" />
          </Button>
        }
      />
      <DropdownMenuContent align="end" sideOffset={8}>
        {navItems.map(({ href, icon: Icon, key }) => {
          const linkHref = href(locale);
          const isActive = currentPath === linkHref;
          return (
            <DropdownMenuItem
              key={key}
              onClick={() => {
                const w = window as { navigate?: (href: string) => void };
                if (w.navigate) {
                  w.navigate(linkHref);
                } else {
                  window.location.href = linkHref;
                }
              }}
            >
              <div
                className={`flex items-center gap-2 text-sm ${
                  isActive ? "font-semibold text-foreground" : "text-muted-foreground"
                }`}
              >
                <Icon className="h-4 w-4 shrink-0" />
                <span>{nav[key]}</span>
              </div>
            </DropdownMenuItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
