"use client";

import { useEffect, useState, useCallback } from "react";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import {
  LayoutDashboard,
  FolderKanban,
  FileText,
  KanbanSquare,
  Upload,
  Settings,
  PanelLeftClose,
  PanelLeftOpen,
  ChevronsUpDown,
  Plus,
  Check,
  Building2,
} from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useTranslations, type Locale } from "@/i18n/utils";
import pkg from "../../../package.json";

export interface SidebarProps {
  locale: string;
  currentPath: string;
  userJson: string;
}

export function Sidebar({ locale = "en", currentPath = "" }: SidebarProps) {
  const t = useTranslations(locale as Locale);
  const L = (path: string) => `/${locale}${path}`;

  // ── Workspace store ──
  const {
    workspaces,
    currentWorkspace,
    fetchWorkspaces,
    setCurrentWorkspace,
    createWorkspace,
    loading,
  } = useWorkspaceStore();

  // ── Collapse state ──
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    const saved = localStorage.getItem("sidebar-collapsed") === "true";
    setCollapsed(saved);
    document.documentElement.classList.toggle("sidebar-collapsed", saved);
  }, []);
  const toggleCollapse = useCallback(() => {
    setCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem("sidebar-collapsed", String(next));
      document.documentElement.classList.toggle("sidebar-collapsed", next);
      return next;
    });
  }, []);

  // ── Fetch workspaces on mount ──
  useEffect(() => {
    if (workspaces.length === 0) {
      fetchWorkspaces();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Workspace creation dialog ──
  const [createOpen, setCreateOpen] = useState(false);
  const [workspaceName, setWorkspaceName] = useState("");
  const [creating, setCreating] = useState(false);

  const handleCreateWorkspace = useCallback(async () => {
    if (!workspaceName.trim()) return;
    setCreating(true);
    try {
      await createWorkspace({ name: workspaceName.trim() });
      setCreateOpen(false);
      setWorkspaceName("");
    } catch {
      // error handled by store
    } finally {
      setCreating(false);
    }
  }, [workspaceName, createWorkspace]);

  // ── Active nav link (client-side) ──
  // currentPath prop is the SSR initial value; after View Transitions
  // the layout persists so props don't update — we track it on the client.
  const [clientPath, setClientPath] = useState(() =>
    typeof window !== "undefined" ? window.location.pathname : currentPath,
  );
  useEffect(() => {
    const onSwap = () => setClientPath(window.location.pathname);
    document.addEventListener("astro:after-swap", onSwap);
    return () => document.removeEventListener("astro:after-swap", onSwap);
  }, []);

  const isActive = (href: string) => {
    const clean = (s: string) => s.replace(/\/$/, "");
    return clean(clientPath) === clean(href);
  };

  // ── Nav links ──
  const navLinks = [
    { href: L("/dashboard"), icon: LayoutDashboard, label: t.nav.dashboard },
    { href: L("/projects"), icon: FolderKanban, label: t.nav.projects },
    { href: L("/stories"), icon: FileText, label: t.nav.stories },
    { href: L("/kanban"), icon: KanbanSquare, label: t.nav.kanban },
    { href: L("/export"), icon: Upload, label: t.nav.export },
    { href: L("/settings"), icon: Settings, label: t.nav.settings },
  ];

  // Filter out Settings for non-admin members
  const visibleLinks =
    currentWorkspace?.role === "member"
      ? navLinks.filter((l) => l.href !== L("/settings"))
      : navLinks;

  // ── Current workspace display name ──
  const wsName = currentWorkspace?.name || "Select workspace";

  return (
    <aside
      data-nav="sidebar"
      className={cn(
        "fixed left-0 z-40 flex w-60 flex-col",
        "bg-(--color-surface)",
        "transition-[width,transform] duration-200",
        "-translate-x-full top-14 rounded-b-xl shadow-lg",
        "lg:inset-y-0 lg:top-0 lg:shadow-none lg:rounded-none lg:border-r lg:border-(--color-border) lg:translate-x-0",
        collapsed && "sidebar-collapsed:w-16",
      )}
    >
      {/* ── Header: Logo + Collapse toggle (desktop) ── */}
      <div
        className={cn(
          "hidden lg:flex h-14 items-center justify-between",
          "border-b border-(--color-border) px-4",
          collapsed
            ? "sidebar-collapsed:justify-center sidebar-collapsed:px-0"
            : "",
        )}
      >
        <a
          href={L("/")}
          className={cn(
            "inline-flex items-center gap-2.5 no-underline",
            collapsed && "sidebar-collapsed:hidden",
          )}
        >
          <img src="/favicon.svg" alt="" className="h-6 w-auto shrink-0" />
          <span className="text-lg font-bold text-(--color-text)">
            {t.app.name}
          </span>
        </a>
        <button
          onClick={toggleCollapse}
          className={cn(
            "rounded-md p-1.5",
            "text-(--color-text-secondary) hover:bg-(--color-surface-secondary)",
            "transition-colors",
          )}
          title={collapsed ? t.sidebar.expand : t.sidebar.collapse}
          aria-label={collapsed ? t.sidebar.expand : t.sidebar.collapse}
        >
          <PanelLeftClose
            className={cn("h-5 w-5", collapsed && "sidebar-collapsed:hidden")}
          />
          <PanelLeftOpen
            className={cn(
              "h-5 w-5 hidden",
              collapsed && "sidebar-collapsed:block",
            )}
          />
        </button>
      </div>

      {/* ── Workspace Switcher ── */}
      <div className="px-3 pt-3 pb-1">
        <DropdownMenu>
          <DropdownMenuTrigger
            render={
              <button
                className={cn(
                  "flex w-full items-center gap-2 rounded-lg px-3 py-2 text-sm",
                  "text-(--color-text) hover:bg-(--color-surface-secondary)",
                  "transition-colors",
                  collapsed && "sidebar-collapsed:justify-center sidebar-collapsed:px-0",
                )}
              >
                <Building2 className="h-4 w-4 shrink-0" />
                <span
                  className={cn(
                    "flex-1 text-left truncate",
                    collapsed && "sidebar-collapsed:hidden",
                  )}
                >
                  {wsName}
                </span>
                <ChevronsUpDown
                  className={cn(
                    "h-3 w-3 shrink-0 text-(--color-text-secondary)",
                    collapsed && "sidebar-collapsed:hidden",
                  )}
                />
              </button>
            }
          />
          <DropdownMenuContent align="start" side="right" sideOffset={8}>
            {loading ? (
              <DropdownMenuItem disabled>
                <span className="text-(--color-text-secondary)">
                  {t.common.loading}
                </span>
              </DropdownMenuItem>
            ) : workspaces.length === 0 ? (
              <DropdownMenuItem disabled>
                <span className="text-(--color-text-secondary)">
                  No workspaces yet
                </span>
              </DropdownMenuItem>
            ) : (
              workspaces.map((w) => (
                <DropdownMenuItem
                  key={w.id}
                  onClick={() => setCurrentWorkspace(w)}
                >
                  <Building2 className="h-4 w-4" />
                  <span className="flex-1">{w.name}</span>
                  {w.id === currentWorkspace?.id && (
                    <Check className="h-4 w-4 text-(--color-primary-500)" />
                  )}
                </DropdownMenuItem>
              ))
            )}
            <DropdownMenuSeparator />
            <DropdownMenuItem onClick={() => setCreateOpen(true)}>
              <Plus className="h-4 w-4" />
              <span>New Workspace</span>
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* ── Navigation ── */}
      <nav className="flex-1 overflow-y-auto p-3 space-y-1">
        {visibleLinks.map(({ href, icon: Icon, label }) => (
          <a
            key={href}
            href={href}
            data-nav-link
            title={label}
            className={cn(
              "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
              isActive(href)
                ? "bg-(--color-surface-secondary) text-(--color-text) font-semibold"
                : "text-(--color-text-secondary) hover:bg-(--color-surface-secondary) hover:text-(--color-text)",
              collapsed && "sidebar-collapsed:justify-center sidebar-collapsed:px-0",
            )}
          >
            <Icon className="h-4 w-4 shrink-0" />
            <span
              className={cn(
                collapsed && "sidebar-collapsed:hidden",
              )}
            >
              {label}
            </span>
          </a>
        ))}
      </nav>

      {/* ── Footer ── */}
      <div
        className={cn(
          "border-t border-(--color-border) p-3",
        )}
      >
        {/* Collapse toggle — visible on mobile */}
        <button
          onClick={toggleCollapse}
          className={cn(
            "flex w-full items-center justify-center rounded-md p-1.5 mb-2",
            "text-(--color-text-secondary) hover:bg-(--color-surface-secondary)",
            "transition-colors lg:hidden",
          )}
          title={collapsed ? t.sidebar.expand : t.sidebar.collapse}
          aria-label={collapsed ? t.sidebar.expand : t.sidebar.collapse}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4 w-4" />
          ) : (
            <PanelLeftClose className="h-4 w-4" />
          )}
        </button>

        <p
          className={cn(
            "text-xs text-(--color-text-secondary) text-center truncate",
          )}
        >
          <span className={cn(collapsed && "sidebar-collapsed:hidden")}>
            {t.app.name}{" "}
          </span>
          v{pkg.version}
        </p>
      </div>

      {/* ── Create Workspace Dialog ── */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>New Workspace</DialogTitle>
            <DialogDescription>
              Create a new workspace to organize your projects and stories.
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <label
                htmlFor="workspace-name"
                className="text-sm font-medium text-(--color-text)"
              >
                Workspace name
              </label>
              <Input
                id="workspace-name"
                placeholder="e.g. My Team Workspace"
                value={workspaceName}
                onChange={(e) => setWorkspaceName(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !creating && workspaceName.trim()) {
                    handleCreateWorkspace();
                  }
                }}
                autoFocus
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setCreateOpen(false);
                setWorkspaceName("");
              }}
            >
              {t.common.cancel}
            </Button>
            <Button
              onClick={handleCreateWorkspace}
              disabled={!workspaceName.trim() || creating}
            >
              {creating ? t.common.loading : t.common.create}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </aside>
  );
}
