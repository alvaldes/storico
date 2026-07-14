"use client";

import * as React from "react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { AutoBreadcrumb } from "@/components/react/AutoBreadcrumb";
import { UserMenu } from "@/components/react/UserMenu";
import { ThemeToggle } from "@/components/react/ThemeToggle";
import { Button } from "@/components/ui/button";
import { Github } from "lucide-react";
import { useTranslations, type Locale } from "@/i18n/utils";

interface DashboardHeaderProps {
  locale: Locale;
  currentPath: string;
  userJson: string;
}

export function DashboardHeader({
  locale,
  currentPath,
  userJson,
}: DashboardHeaderProps) {
  const t = useTranslations(locale);
  const cleanPath = currentPath.replace(/^\/(en|es)/, "") || "/";
  const segments = cleanPath.split("/").filter(Boolean);

  // Language toggle path
  const otherLocale = locale === "en" ? "es" : "en";
  const otherPath =
    currentPath === "/"
      ? `/${otherLocale}`
      : currentPath.replace(/^\/(en|es)/, `/${otherLocale}`) ||
        `/${otherLocale}`;

  return (
    <header className="flex h-16 shrink-0 items-center justify-between border-b border-(--color-border) bg-(--color-surface) px-3 transition-[width,height] ease-linear group-has-data-[collapsible=icon]/sidebar-wrapper:h-12">
      <div className="flex items-center gap-2">
        {/* Sidebar collapse/expand — desktop (sidebar-07 pattern) */}
        <SidebarTrigger className="inline-flex" />

        {/* Vertical separator — desktop */}
        <Separator
          orientation="vertical"
          className="hidden sm:block mx-0 my-auto h-4"
        />

        {/* Breadcrumb */}
        <div className="hidden sm:flex ml-1">
          <AutoBreadcrumb locale={locale} segments={segments} />
        </div>
      </div>

      <div className="flex items-center gap-2">
        <UserMenu userJson={userJson} locale={locale} />
        <a
          href={otherPath}
          className="rounded-md px-2 py-1 text-xs font-medium text-(--color-text-secondary) hover:text-(--color-text) hover:bg-(--color-surface-secondary) transition-colors no-underline"
          aria-label="Switch language"
        >
          {locale === "en" ? "ES" : "EN"}
        </a>
        <ThemeToggle />
        <a
          href="https://github.com/alvaldes/storico"
          target="_blank"
          rel="noopener noreferrer"
          className="rounded-md p-1.5 text-(--color-text-secondary) hover:text-(--color-text) hover:bg-(--color-surface-secondary) transition-colors"
          aria-label="GitHub repository"
          title="GitHub repository"
        >
          <Github className="h-5 w-5" />
        </a>
      </div>
    </header>
  );
}
