"use client"

import { useCallback } from "react"
import {
  LogOut,
  User as UserIcon,
  Settings,
  Sun,
  Moon,
  Languages,
  Github,
} from "lucide-react"
import { signOut } from "auth-astro/client"

import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from "@/components/ui/sidebar"
import { useTranslations, type Locale } from "@/i18n/utils"
import { useUIStore } from "@/stores/uiStore"

export function NavUser({
  user,
  locale,
  currentPath,
}: {
  user: { name: string; email: string; image?: string } | null
  locale: Locale
  currentPath: string
}) {
  const { isMobile } = useSidebar()
  const t = useTranslations(locale)
  const { theme, toggleTheme } = useUIStore()
  const L = (path: string) => `/${locale}${path}`

  const otherLocale = locale === "en" ? "es" : "en"
  const otherPath =
    currentPath === "/"
      ? `/${otherLocale}`
      : currentPath.replace(/^\/(en|es)/, `/${otherLocale}`) ||
        `/${otherLocale}`

  const initials = user?.name
    ? user.name
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : "??"

  const handleLogout = useCallback(() => {
    signOut()
  }, [])

  if (!user) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" render={<a href={L("/login")} />}>
            <UserIcon className="size-4" />
            <span>{t.nav?.login ?? "Sign in"}</span>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    )
  }

  return (
    <SidebarMenu>
      <SidebarMenuItem>
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <SidebarMenuButton
                size="lg"
                className="aria-expanded:bg-sidebar-accent aria-expanded:text-sidebar-accent-foreground"
              />
            }
          >
            <Avatar className="h-8 w-8 rounded-lg">
              <AvatarImage src={user.image ?? ""} alt={user.name} />
              <AvatarFallback className="rounded-lg">
                {initials}
              </AvatarFallback>
            </Avatar>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">{user.name}</span>
              <span className="truncate text-xs text-sidebar-foreground/60">
                {user.email}
              </span>
            </div>
          </DropdownMenuTrigger>
          <DropdownMenuContent
            className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
            side={isMobile ? "bottom" : "right"}
            align="end"
            sideOffset={4}
          >
            <DropdownMenuGroup>
              <DropdownMenuLabel className="p-0 font-normal">
                <div className="flex items-center gap-2 px-1 py-1.5 text-left text-sm">
                  <Avatar className="h-8 w-8 rounded-lg">
                    <AvatarImage src={user.image ?? ""} alt={user.name} />
                    <AvatarFallback className="rounded-lg">
                      {initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">{user.name}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {user.email}
                    </span>
                  </div>
                </div>
              </DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem render={<a href={L("/settings")} />}>
                <Settings className="size-4" />
                {t.nav?.settings ?? "Settings"}
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem onClick={toggleTheme}>
                {theme === "dark" ? (
                  <Sun className="size-4" />
                ) : (
                  <Moon className="size-4" />
                )}
                {theme === "dark" ? "Light Mode" : "Dark Mode"}
              </DropdownMenuItem>
              <DropdownMenuItem
                render={<a href={otherPath} />}
                aria-label="Switch language"
              >
                <Languages className="size-4" />
                {locale === "en" ? "ES" : "EN"}
              </DropdownMenuItem>
              <DropdownMenuItem
                render={
                  <a
                    href="https://github.com/alvaldes/storico"
                    target="_blank"
                    rel="noopener noreferrer"
                  />
                }
                aria-label="GitHub repository"
              >
                <Github className="size-4" />
                GitHub
              </DropdownMenuItem>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={handleLogout}>
              <LogOut className="size-4" />
              {t.nav?.logout ?? "Log out"}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </SidebarMenuItem>
    </SidebarMenu>
  )
}
