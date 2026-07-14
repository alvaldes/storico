"use client";

import * as React from "react";
import { SidebarTrigger } from "@/components/ui/sidebar";
import { Separator } from "@/components/ui/separator";
import { AutoBreadcrumb } from "@/components/react/AutoBreadcrumb";
import type { Locale } from "@/i18n/utils";

interface DashboardHeaderProps {
  locale: Locale;
  currentPath: string;
}

export function DashboardHeader({
  locale,
  currentPath,
}: DashboardHeaderProps) {
  const cleanPath = currentPath.replace(/^\/(en|es)/, "") || "/";
  const segments = cleanPath.split("/").filter(Boolean);

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
    </header>
  );
}
