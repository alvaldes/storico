"use client"

import * as React from "react"
import {
  Building2,
  Plus,
  Check,
  ChevronsUpDown,
  SearchIcon,
} from "lucide-react"
import { IconDisplay } from "@/components/ui/icon-display"

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
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Field,
  FieldLabel,
} from "@/components/ui/field"
import { useWorkspaceStore } from "@/stores/workspaceStore"
import { useTranslations, type Locale } from "@/i18n/utils"
import { IconPicker, IconTrigger } from "@/components/ui/icon-picker"

interface Team {
  name: string
  id: string
  role: string
  icon?: string
}

export function TeamSwitcher({
  teams,
  locale,
}: {
  teams: Team[]
  locale: Locale
}) {
  const { isMobile } = useSidebar()
  const { currentWorkspace, setCurrentWorkspace, createWorkspace } =
    useWorkspaceStore()
  const t = useTranslations(locale)

  const [createOpen, setCreateOpen] = React.useState(false)
  const [workspaceName, setWorkspaceName] = React.useState("")
  const [workspaceIcon, setWorkspaceIcon] = React.useState("building-2")
  const [creating, setCreating] = React.useState(false)
  const [pickerOpen, setPickerOpen] = React.useState(false)

  const activeTeam = currentWorkspace ?? teams[0]

  const handleCreate = async () => {
    if (!workspaceName.trim()) return
    setCreating(true)
    try {
      await createWorkspace({
        name: workspaceName.trim(),
        icon: workspaceIcon,
      })
      setCreateOpen(false)
      setWorkspaceName("")
      setWorkspaceIcon("building-2")
    } catch {
      // error handled by store
    } finally {
      setCreating(false)
    }
  }

  if (!teams.length) {
    return (
      <SidebarMenu>
        <SidebarMenuItem>
          <SidebarMenuButton size="lg" onClick={() => setCreateOpen(true)}>
            <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
              <Plus className="size-4" />
            </div>
            <div className="grid flex-1 text-left text-sm leading-tight">
              <span className="truncate font-medium">
                {t.sidebar?.createWorkspace ?? "New Workspace"}
              </span>
            </div>
          </SidebarMenuButton>
        </SidebarMenuItem>
      </SidebarMenu>
    )
  }

  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger
              render={
                <SidebarMenuButton
                  size="lg"
                  className="data-open:bg-sidebar-accent data-open:text-sidebar-accent-foreground"
                />
              }
            >
              <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground">
                <IconDisplay name={activeTeam.icon} className="size-4" fallback={Building2} />
              </div>
              <div className="grid flex-1 text-left text-sm leading-tight">
                <span className="truncate font-medium">{activeTeam.name}</span>
                <span className="truncate text-xs text-sidebar-foreground/60">
                  {activeTeam.role}
                </span>
              </div>
              <ChevronsUpDown className="ml-auto size-4" />
            </DropdownMenuTrigger>
            <DropdownMenuContent
              className="w-(--radix-dropdown-menu-trigger-width) min-w-56 rounded-lg"
              align="start"
              side={isMobile ? "bottom" : "right"}
              sideOffset={4}
            >
              <DropdownMenuGroup>
                <DropdownMenuLabel className="text-xs text-muted-foreground">
                  {t.sidebar?.workspaces ?? "Workspaces"}
                </DropdownMenuLabel>
                {teams.map((team) => (
                  <DropdownMenuItem
                    key={team.id}
                    onClick={() => {
                      const ws = useWorkspaceStore
                        .getState()
                        .workspaces.find((w) => w.id === team.id)
                      if (ws) setCurrentWorkspace(ws)
                    }}
                    className="gap-2 p-2"
                  >
                    <div className="flex size-6 items-center justify-center rounded-md border">
                      <IconDisplay name={team.icon} className="size-3.5 shrink-0" fallback={Building2} />
                    </div>
                    <span className="flex-1">{team.name}</span>
                    {team.id === activeTeam.id && (
                      <Check className="size-4 text-primary" />
                    )}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuGroup>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                className="gap-2 p-2"
                onClick={() => setCreateOpen(true)}
              >
                <div className="flex size-6 items-center justify-center rounded-md border bg-transparent">
                  <Plus className="size-4" />
                </div>
                <span className="font-medium text-muted-foreground">
                  {t.sidebar?.newWorkspace ?? "New Workspace"}
                </span>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>

      {/* Create Workspace Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {t.sidebar?.newWorkspace ?? "New Workspace"}
            </DialogTitle>
            <DialogDescription>
              {t.sidebar?.createWorkspaceDescription ?? "Create a new workspace to organize your projects and stories."}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <Field>
              <FieldLabel htmlFor="team-name">
                {t.sidebar?.workspaceNameLabel ?? "Workspace name"}
              </FieldLabel>
              <div className="flex items-center gap-2">
                <IconTrigger
                  value={workspaceIcon}
                  onClick={() => setPickerOpen(true)}
                  locale={locale}
                />
                <Input
                  id="team-name"
                  placeholder={t.sidebar?.workspaceNamePlaceholder ?? "e.g. My Team"}
                  value={workspaceName}
                  onChange={(e) => setWorkspaceName(e.target.value)}
                  onKeyDown={(e) => {
                    if (
                      e.key === "Enter" &&
                      !creating &&
                      workspaceName.trim()
                    ) {
                      handleCreate()
                    }
                  }}
                  autoFocus
                  className="flex-1"
                />
              </div>
            </Field>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setCreateOpen(false)
                setWorkspaceName("")
                setWorkspaceIcon("building-2")
              }}
            >
              {t.common?.cancel ?? "Cancel"}
            </Button>
            <Button
              onClick={handleCreate}
              disabled={!workspaceName.trim() || creating}
            >
              {creating ? t.common?.loading ?? "Creating..." : t.common?.create ?? "Create"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Icon Picker */}
      <IconPicker
        value={workspaceIcon}
        onChange={setWorkspaceIcon}
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        locale={locale}
      />
    </>
  )
}
