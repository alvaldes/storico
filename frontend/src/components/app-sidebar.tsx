"use client"

import * as React from "react"
import { useSidebar } from "@/components/ui/sidebar"
import { useTranslations, type Locale } from "@/i18n/utils"
import { useWorkspaceStore } from "@/stores/workspaceStore"

import { NavMain } from "@/components/nav-main"
import { NavUser } from "@/components/nav-user"
import { TeamSwitcher } from "@/components/team-switcher"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarRail,
} from "@/components/ui/sidebar"
import {
  LayoutDashboard,
  FolderKanban,
  FileText,
  KanbanSquare,
  Upload,
  Settings,
} from "lucide-react"

export interface AppSidebarProps extends React.ComponentProps<typeof Sidebar> {
  locale: Locale
  currentPath: string
  user: { name: string; email: string; image?: string } | null
}

export function AppSidebar({
  locale,
  currentPath,
  user,
  ...props
}: AppSidebarProps) {
  const t = useTranslations(locale)
  const L = (path: string) => `/${locale}${path}`
  const { workspaces, currentWorkspace, fetchWorkspaces } = useWorkspaceStore()
  const { state } = useSidebar()

  // Fetch workspaces once
  React.useEffect(() => {
    if (workspaces.length === 0) {
      fetchWorkspaces()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Detect active link from currentPath
  const cleanPath = currentPath.replace(/^\/(en|es)/, "") || "/"
  const isActive = (href: string) => {
    const clean = (s: string) => s.replace(/\/$/, "")
    return clean(cleanPath) === clean(href)
  }

  const navMain = [
    {
      title: t.nav.dashboard,
      url: L("/dashboard"),
      icon: <LayoutDashboard />,
      isActive: isActive(L("/dashboard")),
    },
    {
      title: t.nav.projects,
      url: L("/projects"),
      icon: <FolderKanban />,
      isActive: isActive(L("/projects")),
    },
    {
      title: t.nav.stories,
      url: L("/stories"),
      icon: <FileText />,
      isActive: isActive(L("/stories")),
    },
    {
      title: t.nav.kanban,
      url: L("/kanban"),
      icon: <KanbanSquare />,
      isActive: isActive(L("/kanban")),
    },
    {
      title: t.nav.export,
      url: L("/export"),
      icon: <Upload />,
      isActive: isActive(L("/export")),
    },
    {
      title: t.nav.settings,
      url: L("/settings"),
      icon: <Settings />,
      isActive: isActive(L("/settings")),
    },
  ]

  const teams = workspaces.map((ws) => ({
    name: ws.name,
    id: ws.id,
    role: ws.role ?? "member",
  }))

  return (
    <Sidebar collapsible="icon" {...props}>
      <SidebarHeader>
        <TeamSwitcher
          teams={teams}
          locale={locale}
        />
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={navMain} locale={locale} />
      </SidebarContent>
      <SidebarFooter>
        <NavUser
          user={user}
          locale={locale}
        />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
