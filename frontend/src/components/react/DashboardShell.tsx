"use client"

import * as React from "react"
import type { ReactNode } from "react"
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar"
import { AppSidebar } from "@/components/app-sidebar"
import { DashboardHeader } from "@/components/react/DashboardHeader"
import { AutoBreadcrumb } from "@/components/react/AutoBreadcrumb"
import { Toaster } from "@/components/ui/sonner"
import { type Locale } from "@/i18n/utils"
import { useAuthStore, type AuthUser } from "@/stores/authStore"
import { fetchCurrentUser } from "@/lib/user-api"

interface DashboardShellProps {
  locale: Locale
  currentPath: string
  userJson: string
  sidebarDefaultOpen?: boolean
  children: ReactNode
}

/**
 * Full dashboard layout with shadcn SidebarProvider.
 *
 * Provides the sidebar context for SidebarTrigger, responsive
 * collapse behavior, and mobile sheet navigation.
 */
export function DashboardShell({
  locale,
  currentPath,
  userJson,
  sidebarDefaultOpen = true,
  children,
}: DashboardShellProps) {
  const user = userJson ? (JSON.parse(userJson) as Record<string, unknown>) : null
  const parsedUser = user
    ? {
        name: (user.name as string) ?? "",
        email: (user.email as string) ?? "",
        image: (user.image as string) ?? undefined,
      }
    : null

  const cleanPath = currentPath.replace(/^\/(en|es)/, "") || "/"
  const segments = cleanPath.split("/").filter(Boolean)

  // Populate auth store from serialised session (used by SettingsPage, etc.)
  const setUser = useAuthStore((s) => s.setUser)
  React.useEffect(() => {
    if (userJson) {
      try {
        const parsed: Record<string, unknown> = JSON.parse(userJson)
        const baseUser: AuthUser = {
          id: (parsed.id as string) || "",
          email: (parsed.email as string) || "",
          name: (parsed.name as string) || "",
          avatar_url:
            (parsed.avatar_url as string) || (parsed.image as string) || undefined,
        }
        setUser(baseUser)
        fetchCurrentUser()
          .then((profile) => {
            setUser({ ...baseUser, authProvider: profile.authProvider })
          })
          .catch(() => {})
      } catch {
        setUser(null)
      }
    } else {
      setUser(null)
    }
  }, [userJson, setUser])

  return (
    <SidebarProvider defaultOpen={sidebarDefaultOpen}>
      <AppSidebar
        locale={locale}
        currentPath={currentPath}
        user={parsedUser}
      />
      <SidebarInset>
        <DashboardHeader
          locale={locale}
          currentPath={currentPath}
        />

        {/* Breadcrumb on mobile — shown below the header */}
        <div className="sm:hidden px-4 pt-3">
          <AutoBreadcrumb locale={locale} segments={segments} />
        </div>

        <main className="flex-1 p-4 lg:p-6">{children}</main>
      </SidebarInset>
      <Toaster />
    </SidebarProvider>
  )
}