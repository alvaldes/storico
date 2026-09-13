import { useState, useEffect, useCallback } from "react";
import {
  Settings,
  Users,
  Check,
  TriangleAlert,
  Trash2,
  RotateCw,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
  CardFooter,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  AlertDialog,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogAction,
  AlertDialogCancel,
} from "@/components/ui/alert-dialog";
import { MemberManagement } from "@/components/react/MemberManagement";
import { LLMConfigEditor } from "@/components/react/LLMConfigEditor";
import { IconPicker, IconTrigger } from "@/components/ui/icon-picker";
import * as workspaceApi from "@/lib/workspace-api";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { useAuthStore } from "@/stores/authStore";
import en from "@/i18n/en.json";
import es from "@/i18n/es.json";
import { localizedPath, type Locale } from "@/i18n/utils";

/* ── Props ─────────────────────────────────────────────────── */

interface WorkspaceSettingsProps {
  locale: Locale;
  workspaceId: string;
}

/* ── WorkspaceSettings Component ────────────────────────────── */

export function WorkspaceSettings({
  locale,
  workspaceId,
}: WorkspaceSettingsProps) {
  const t = locale === "es" ? es : en;

  /* ── Workspace Info State ── */
  const [wsName, setWsName] = useState("");
  const [wsIcon, setWsIcon] = useState("building-2");
  const [wsRole, setWsRole] = useState<"admin" | "member">("member");
  const [wsOwnerId, setWsOwnerId] = useState("");
  const [pickerOpen, setPickerOpen] = useState(false);
  const [infoSaving, setInfoSaving] = useState(false);

  /* ── Delete Workspace State ── */
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [deleteName, setDeleteName] = useState("");
  const [deleteVerify, setDeleteVerify] = useState("");
  const [deleteSaving, setDeleteSaving] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const verifyPhrase =
    t.workspace?.deleteConfirmPhrase ?? "delete my workspace";

  /* ── Current User ── */
  const currentUser = useAuthStore((s) => s.user);

  /* ── Resolve workspaceId from URL (survives View Transitions) ── */
  const [resolvedWsId, setResolvedWsId] = useState(workspaceId);
  // Use resolved URL ID (survives View Transitions) instead of initial prop
  const wsId = resolvedWsId;

  useEffect(() => {
    function onSwap() {
      const match = window.location.pathname.match(
        /\/workspaces\/([^/]+)\/settings/,
      );
      if (match && match[1]) {
        setResolvedWsId(match[1]);
        setDeleteName("");
        setDeleteVerify("");
        setDeleteError(null);
        setDeleteOpen(false);
      }
    }
    document.addEventListener("astro:after-swap", onSwap);
    return () => document.removeEventListener("astro:after-swap", onSwap);
  }, []);

  /* ── Shared State ── */
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);

  /* ── Fetch Workspace Info ── */
  const loadWorkspaceInfo = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const ws = await workspaceApi.getWorkspace(wsId).catch((err) => {
        if (
          err instanceof Error &&
          (err.message.includes("403") || err.message.includes("admin"))
        ) {
          return null;
        }
        throw err;
      });

      if (ws) {
        setWsName(ws.name ?? "");
        setWsIcon(ws.icon ?? "building-2");
        setWsRole(ws.role ?? "member");
        setWsOwnerId(ws.ownerId ?? "");
      }
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : (t.workspace?.loadError ?? "Failed to load settings");
      setError(message);
      toast.error(message);
    } finally {
      setLoading(false);
    }
  }, [wsId]);

  useEffect(() => {
    setMounted(true);
    loadWorkspaceInfo();
  }, [loadWorkspaceInfo]);

  /* ── Workspace Info Save Handler ── */
  const handleInfoSave = async () => {
    setInfoSaving(true);
    try {
      await useWorkspaceStore.getState().updateWorkspace(wsId, {
        name: wsName || undefined,
        icon: wsIcon !== "building-2" ? wsIcon : undefined,
      });
      toast.success(t.workspace?.savedInfo ?? "Workspace updated");
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : (t.workspace?.saveInfoError ?? "Failed to update workspace");
      toast.error(message);
    } finally {
      setInfoSaving(false);
    }
  };

  /* ── Delete Workspace Handler ── */
  const handleDeleteWorkspace = async () => {
    const nameMismatch = deleteName !== wsName;
    const phraseMismatch = deleteVerify !== verifyPhrase;
    if (nameMismatch || phraseMismatch) {
      setDeleteError(
        t.workspace?.deleteConfirmError ?? "Failed to delete workspace",
      );
      return;
    }
    setDeleteSaving(true);
    setDeleteError(null);
    try {
      await useWorkspaceStore.getState().deleteWorkspace(wsId);
      toast.success(t.workspace?.deleteConfirmSuccess ?? "Workspace deleted");
      // Redirect to dashboard — internal path only (never absolute/protocol-relative)
      const redirectTarget = localizedPath("/dashboard", locale);
      if (redirectTarget.startsWith("/") && !redirectTarget.startsWith("//")) {
        window.location.href = redirectTarget;
      }
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : (t.workspace?.deleteConfirmError ?? "Failed to delete workspace");
      setDeleteError(message);
      setDeleteSaving(false);
    }
  };

  const canDelete = deleteName === wsName && deleteVerify === verifyPhrase;

  /* ── Derived ── */
  const isOwner = currentUser?.id === wsOwnerId;

  /* ── Loading State ── */
  if (!mounted) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-(--color-border) border-t-(--color-primary-500)" />
      </div>
    );
  }

  /* ── Render ── */
  return (
    <div className="mx-auto max-w-4xl space-y-6 pb-12">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-semibold text-(--color-text)">
          {t.workspace?.settingsTitle ?? "Workspace Settings"}
        </h1>
        <p className="mt-1 text-sm text-(--color-text-secondary)">
          {t.workspace?.settingsDescription ??
            "Configure LLM, prompts, and manage team members for this workspace."}
        </p>
      </div>

      {/* ── Section 1: General (Workspace Info) ── */}
      {!loading && (
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Settings className="h-4 w-4 text-(--color-text-secondary)" />
              <CardTitle className="text-base">
                {t.workspace?.infoTitle ?? "General"}
              </CardTitle>
            </div>
          </CardHeader>
          <CardContent>
            <div className="flex items-center gap-3">
              <IconTrigger
                value={wsIcon}
                onClick={() => setPickerOpen(true)}
                locale={locale}
              />
              <Input
                id="ws-name"
                value={wsName}
                onChange={(e) => setWsName(e.target.value)}
                placeholder={t.workspace?.namePlaceholder ?? "e.g. My Team"}
                disabled={wsRole !== "admin"}
                className="flex-1"
              />
              <Button
                onClick={handleInfoSave}
                disabled={infoSaving || wsRole !== "admin"}
                size="sm"
              >
                {infoSaving ? (
                  <RotateCw className="h-4 w-4 animate-spin" />
                ) : (
                  <Check className="h-4 w-4" />
                )}
                {t.common?.save ?? "Save"}
              </Button>
            </div>

            {wsRole !== "admin" && (
              <p className="mt-2 text-xs text-(--color-text-tertiary)">
                {t.workspace?.infoNonAdminHint ??
                  "Only admins can edit workspace settings."}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Icon Picker dialog */}
      <IconPicker
        value={wsIcon}
        onChange={setWsIcon}
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        locale={locale}
      />

      {loading ? (
        <div className="flex items-center gap-2 py-12 text-sm text-(--color-text-secondary)">
          <RotateCw className="h-4 w-4 animate-spin" />
          {t.workspace?.loading ?? "Loading settings..."}
        </div>
      ) : error ? (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/30">
          <TriangleAlert className="h-5 w-5 shrink-0 text-red-500" />
          <div>
            <p className="text-sm font-medium text-red-800 dark:text-red-200">
              {error}
            </p>
            <button
              type="button"
              onClick={loadWorkspaceInfo}
              className="mt-1 text-sm text-red-600 underline hover:text-red-800 dark:text-red-400 dark:hover:text-red-200"
            >
              {t.workspace?.tryAgain ?? "Try again"}
            </button>
          </div>
        </div>
      ) : (
        <>
          {/* LLM Config + Prompt Config Editor */}
          <LLMConfigEditor locale={locale} workspaceId={wsId} />

          {/* ── Section 3: Member Management ── */}
          <Card>
            <CardHeader>
              <div className="flex items-center gap-2">
                <Users className="h-4 w-4 text-(--color-text-secondary)" />
                <CardTitle>
                  {t.workspace?.teamMembersTitle ?? "Team Members"}
                </CardTitle>
              </div>
              <CardDescription>
                {t.workspace?.teamMembersDesc ??
                  "Manage members, roles, and ownership for this workspace"}
              </CardDescription>
            </CardHeader>
            <CardContent>
              <MemberManagement locale={locale} workspaceId={wsId} />
            </CardContent>
          </Card>

          {/* ── Section 4: Danger Zone (owner only) ── */}
          {isOwner && (
            <Card className="border-red-300 dark:border-red-700">
              <CardHeader>
                <div className="flex items-center gap-2">
                  <TriangleAlert className="h-4 w-4 text-red-500" />
                  <CardTitle className="text-red-600 dark:text-red-400">
                    {t.workspace?.deleteTitle ?? "Delete workspace"}
                  </CardTitle>
                </div>
                <CardDescription>
                  {t.workspace?.deleteDescription ??
                    "Permanently delete this workspace and all its data. This action cannot be undone."}
                </CardDescription>
              </CardHeader>
              <CardFooter className="bg-red-50/80 dark:bg-red-950/20 border-t-red-200 dark:border-t-red-800 justify-end">
                <AlertDialog
                  open={deleteOpen}
                  onOpenChange={(open) => {
                    setDeleteOpen(open);
                    if (open) {
                      setDeleteName("");
                      setDeleteVerify("");
                      setDeleteError(null);
                    }
                  }}
                >
                  <AlertDialogTrigger render={<Button variant="destructive" />}>
                    <Trash2 className="h-4 w-4" />
                    {t.workspace?.deleteButton ?? "Delete workspace"}
                  </AlertDialogTrigger>
                  <AlertDialogContent size="default" className="min-w-[500px]">
                    <AlertDialogHeader>
                      <AlertDialogTitle>
                        {t.workspace?.deleteConfirmTitle ?? "Delete Workspace"}
                      </AlertDialogTitle>
                      <AlertDialogDescription>
                        {t.workspace?.deleteConfirmDescription ??
                          "This will permanently delete the workspace and related resources like Projects, User Stories and Tasks."}
                      </AlertDialogDescription>
                    </AlertDialogHeader>

                    <div className="-mx-4 border-y border-(--color-border) bg-(--color-surface-secondary)/30 px-4 py-4 space-y-5">
                      {/* Step 1: type workspace name */}
                      <label className="flex flex-col gap-2">
                        <p className="text-sm text-(--color-text)">
                          {t.workspace?.deleteConfirmNameLabel ??
                            "To confirm, type"}{" "}
                          <b className="font-semibold break-all">{wsName}</b>
                        </p>
                        <Input
                          value={deleteName}
                          onChange={(e) => {
                            setDeleteName(e.target.value);
                            setDeleteError(null);
                          }}
                          disabled={deleteSaving}
                        />
                      </label>

                      {/* Step 2: type verification phrase */}
                      <label className="flex flex-col gap-2">
                        <p className="text-sm text-(--color-text)">
                          {t.workspace?.deleteConfirmPhraseLabel ??
                            "To confirm, type"}{" "}
                          <b className="font-semibold" translate="no">
                            {verifyPhrase}
                          </b>
                        </p>
                        <Input
                          value={deleteVerify}
                          onChange={(e) => {
                            setDeleteVerify(e.target.value);
                            setDeleteError(null);
                          }}
                          disabled={deleteSaving}
                        />
                      </label>
                    </div>

                    {/* Warning note */}
                    <div className="flex items-start gap-3 rounded-md border border-red-200 bg-red-50 p-3 dark:border-red-900 dark:bg-red-950/30">
                      <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-red-500" />
                      <p className="text-sm text-red-800 dark:text-red-200">
                        {(
                          t.workspace?.deleteConfirmNote ??
                          "Deleting {name} cannot be undone."
                        ).replace("{name}", wsName)}
                      </p>
                    </div>

                    {deleteError && (
                      <p className="text-xs text-red-500">{deleteError}</p>
                    )}

                    <AlertDialogFooter>
                      <AlertDialogCancel disabled={deleteSaving}>
                        {t.common?.cancel ?? "Cancel"}
                      </AlertDialogCancel>
                      <AlertDialogAction
                        variant="destructive"
                        onClick={handleDeleteWorkspace}
                        disabled={!canDelete || deleteSaving}
                      >
                        {deleteSaving ? (
                          <RotateCw className="h-4 w-4 animate-spin" />
                        ) : (
                          <Trash2 className="h-4 w-4" />
                        )}
                        {t.workspace?.deleteButton ?? "Delete workspace"}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </CardFooter>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
