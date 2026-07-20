"use client"

import * as React from "react"
import { useSidebar } from "@/components/ui/sidebar"
import { useTranslations, type Locale } from "@/i18n/utils"
import { useWorkspaceStore } from "@/stores/workspaceStore"
import { useProjectStore } from "@/stores/projectStore"

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

function stripLocale(path: string): string {
  return path.replace(/^\/(en|es)/, "") || "/"
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
  const { projects, fetchProjects } = useProjectStore()
  const { state } = useSidebar()

  // ── Bootstrap data ──
  React.useEffect(() => {
    if (workspaces.length === 0) {
      fetchWorkspaces()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  React.useEffect(() => {
    if (currentWorkspace) {
      fetchProjects()
    }
  }, [currentWorkspace?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Track path on the client so active state works with View Transitions ──
  const [livePath, setLivePath] = React.useState(currentPath)
  React.useEffect(() => {
    const updatePath = () => setLivePath(window.location.pathname)
    updatePath()
    document.addEventListener("astro:page-load", updatePath)
    return () => document.removeEventListener("astro:page-load", updatePath)
  }, [])

  // ── Active-link detection ──
  const cleanPath = stripLocale(livePath)
  const isActive = (href: string) => {
    const a = cleanPath.replace(/\/$/, "")
    const b = stripLocale(href).replace(/\/$/, "")
    return a === b
  }
  const isProjectsActive = /^\/projects(\/|$)/.test(cleanPath)

  // ── Navigation items ──
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
      isActive: isProjectsActive,
      items: [
        {
          title: t.nav.allProjects,
          url: L("/projects"),
          isActive: isActive(L("/projects")),
        },
        ...projects.map((p) => ({
          title: p.name,
          url: L(`/projects/${p.id}`),
          isActive: cleanPath === `/projects/${p.id}`,
        })),
      ],
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
      url: currentWorkspace ? L(`/workspaces/${currentWorkspace.id}/settings`) : "#",
      icon: <Settings />,
      isActive: currentWorkspace
        ? isActive(L(`/workspaces/${currentWorkspace.id}/settings`))
        : false,
    },
  ]

  const teams = workspaces.map((ws) => ({
    name: ws.name,
    id: ws.id,
    role: ws.role ?? "member",
    icon: ws.icon ?? undefined,
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
          currentPath={currentPath}
        />
      </SidebarFooter>
      <SidebarRail />
    </Sidebar>
  )
}
