"use client"

import { useCallback } from "react"
import {
  LogOut,
  User as UserIcon,
  Sun,
  Moon,
  Languages,
  ChevronsUpDown,
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
import { useAuthStore } from "@/stores/authStore"

export function NavUser({
  locale,
  currentPath,
}: {
  locale: Locale
  currentPath: string
}) {
  const { isMobile } = useSidebar()
  const t = useTranslations(locale)
  const { theme, toggleTheme } = useUIStore()
  const L = (path: string) => `/${locale}${path}`
  const user = useAuthStore((s) => s.user)

  const displayName = user?.name ?? ""
  const displayEmail = user?.email ?? ""
  const displayImage = user?.avatar_url

  const otherLocale = locale === "en" ? "es" : "en"
  const otherPath =
    currentPath === "/"
      ? `/${otherLocale}`
      : currentPath.replace(/^\/(en|es)/, `/${otherLocale}`) ||
        `/${otherLocale}`

  const initials = displayName
    ? displayName
        .split(" ")
        .map((n) => n[0])
        .join("")
        .toUpperCase()
        .slice(0, 2)
    : "??"

  const handleLogout = useCallback(() => {
    signOut({ callbackUrl: `/${locale}/login` })
  }, [locale])

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
              <AvatarImage src={displayImage ?? ""} alt={displayName} />
              <AvatarFallback className="rounded-lg">
                {initials}
              </AvatarFallback>
            </Avatar>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">{displayName}</span>
              <span className="truncate text-xs text-sidebar-foreground/60">
                {displayEmail}
              </span>
            </div>
            <ChevronsUpDown className="ml-auto size-4" />
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
                    <AvatarImage src={displayImage ?? ""} alt={displayName} />
                    <AvatarFallback className="rounded-lg">
                      {initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="grid flex-1 text-left text-sm leading-tight">
                    <span className="truncate font-medium">{displayName}</span>
                    <span className="truncate text-xs text-muted-foreground">
                      {displayEmail}
                    </span>
                  </div>
                </div>
              </DropdownMenuLabel>
            </DropdownMenuGroup>
            <DropdownMenuSeparator />
            <DropdownMenuGroup>
              <DropdownMenuItem render={<a href={L("/account")} />}>
                <UserIcon className="size-4" />
                {t.nav?.account ?? "Account"}
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
                {theme === "dark" ? t.theme?.mode_light : t.theme?.mode_dark}
              </DropdownMenuItem>
              <DropdownMenuItem
                aria-label="Switch language"
                onClick={async () => {
                  const { navigate } = await import("astro:transitions/client");
                  navigate(otherPath, { history: "replace" });
                }}
              >
                <Languages className="size-4" />
                {locale === "en"
                  ? t.settings?.appearance_language_es
                  : t.settings?.appearance_language_en}
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
