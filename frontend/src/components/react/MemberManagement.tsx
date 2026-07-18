import { useState, useEffect, useCallback } from "react";
import { UserAvatar } from "@/components/react/UserAvatar";
import {
  LoaderCircle,
  UserPlus,
  ShieldCheck,
  Shield,
  Trash2,
  Crown,
  Send,
  TriangleAlert,
  Check,
  X,
  MoreHorizontal,
} from "lucide-react";
import { toast } from "sonner";
import {
  listMembers,
  addMember,
  updateMemberRole,
  removeMember,
  transferOwnership,
} from "@/lib/workspace-api";
import { useWorkspaceStore } from "@/stores/workspaceStore";
import { useAuthStore } from "@/stores/authStore";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Field,
  FieldLabel,
  FieldDescription,
  FieldError,
} from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import type { WorkspaceMember } from "@/types/workspace";
import en from "@/i18n/en.json";
import es from "@/i18n/es.json";

/* ── Props ─────────────────────────────────────────────────── */

interface MemberManagementProps {
  locale: string;
  workspaceId: string;
}

/* ── Helpers ────────────────────────────────────────────────── */

function formatDate(dateStr: string, locale: string): string {
  const date = new Date(dateStr);
  return date.toLocaleDateString(locale === "es" ? "es-MX" : "en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

/* ── MemberManagement Component ────────────────────────────── */

export function MemberManagement({
  locale,
  workspaceId,
}: MemberManagementProps) {
  const t = locale === "es" ? es : en;

  /* ── Stores ── */
  const currentWorkspace = useWorkspaceStore((s) => s.currentWorkspace);
  const currentUser = useAuthStore((s) => s.user);

  /* ── State ── */
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /* Add member dialog */
  const [addOpen, setAddOpen] = useState(false);
  const [newUserId, setNewUserId] = useState("");
  const [addSaving, setAddSaving] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  /* Remove member confirmation */
  const [removeTarget, setRemoveTarget] = useState<WorkspaceMember | null>(
    null,
  );
  const [removeSaving, setRemoveSaving] = useState(false);

  /* Transfer ownership */
  const [transferOpen, setTransferOpen] = useState(false);
  const [transferTargetId, setTransferTargetId] = useState("");
  const [transferSaving, setTransferSaving] = useState(false);
  const [transferError, setTransferError] = useState<string | null>(null);

  /* Role change saving tracking */
  const [changingRole, setChangingRole] = useState<string | null>(null);

  /* ── Derived ── */
  const ownerId = currentWorkspace?.ownerId ?? "";
  const isAdmin = currentWorkspace?.role === "admin";
  const isOwner = currentUser?.id === ownerId;

  const adminMembers = members.filter((m) => m.role === "admin");
  const nonOwnerAdmins = adminMembers.filter((m) => m.userId !== ownerId);

  /* ── Fetch Members ── */
  const loadMembers = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listMembers(workspaceId);
      setMembers(data.members);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : (t.members?.failedToLoad ?? "Failed to load members");
      setError(message);
    } finally {
      setLoading(false);
    }
  }, [workspaceId]);

  useEffect(() => {
    loadMembers();
  }, [loadMembers]);

  /* ── Add Member ── */
  const handleAddMember = async () => {
    if (!newUserId.trim()) {
      setAddError(t.members?.userIdRequired ?? "User ID is required");
      return;
    }
    setAddSaving(true);
    setAddError(null);
    try {
      await addMember(workspaceId, newUserId.trim());
      toast.success(t.members?.addedToast ?? "Member added");
      setAddOpen(false);
      setNewUserId("");
      loadMembers();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : (t.members?.failedToAdd ?? "Failed to add member");
      setAddError(message);
    } finally {
      setAddSaving(false);
    }
  };

  /* ── Change Role ── */
  const handleRoleChange = async (userId: string, newRole: string) => {
    setChangingRole(userId);
    try {
      await updateMemberRole(workspaceId, userId, newRole);
      toast.success(
        newRole === "admin"
          ? (t.members?.promotedToast ?? "Member promoted to admin")
          : (t.members?.demotedToast ?? "Admin demoted to member"),
      );
      loadMembers();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : (t.members?.failedRoleChange ?? "Failed to change role");
      toast.error(message);
    } finally {
      setChangingRole(null);
    }
  };

  /* ── Remove Member ── */
  const handleRemoveMember = async () => {
    if (!removeTarget) return;
    setRemoveSaving(true);
    try {
      await removeMember(workspaceId, removeTarget.userId);
      toast.success(t.members?.removedToast ?? "Member removed");
      setRemoveTarget(null);
      loadMembers();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : (t.members?.failedToRemove ?? "Failed to remove member");
      toast.error(message);
    } finally {
      setRemoveSaving(false);
    }
  };

  /* ── Transfer Ownership ── */
  const handleTransferOwnership = async () => {
    if (!transferTargetId) {
      setTransferError(t.members?.selectOwnerError ?? "Select a new owner");
      return;
    }
    setTransferSaving(true);
    setTransferError(null);
    try {
      await transferOwnership(workspaceId, transferTargetId);
      toast.success(t.members?.transferredToast ?? "Ownership transferred");
      setTransferOpen(false);
      setTransferTargetId("");
      loadMembers();
    } catch (err) {
      const message =
        err instanceof Error ? err.message : (t.members?.failedToTransfer ?? "Failed to transfer ownership");
      setTransferError(message);
    } finally {
      setTransferSaving(false);
    }
  };

  /* ── Owner Info ── */
  const ownerMember = members.find((m) => m.userId === ownerId);

  /* ── Loading State ── */
  if (loading) {
    return (
      <div className="flex items-center gap-2 py-4 text-sm text-(--color-text-secondary)">
        <LoaderCircle className="h-4 w-4 animate-spin" />
        {t.members?.loading ?? "Loading members..."}
      </div>
    );
  }

  /* ── Error State ── */
  if (error) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/30">
        <TriangleAlert className="h-5 w-5 shrink-0 text-red-500" />
        <div>
          <p className="text-sm font-medium text-red-800 dark:text-red-200">
            {error}
          </p>
          <button
            type="button"
            onClick={loadMembers}
            className="mt-1 text-sm text-red-600 underline hover:text-red-800 dark:text-red-400 dark:hover:text-red-200"
          >
            {t.members?.tryAgain ?? "Try again"}
          </button>
        </div>
      </div>
    );
  }

  /* ── Render ── */
  return (
    <div className="space-y-6">
      {/* ── Member List ── */}
      <div className="space-y-3">
        {/* Header row */}
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-(--color-text)">
            {members.length === 1
              ? (t.members?.count ?? "{count} member").replace("{count}", String(members.length))
              : (t.members?.countPlural ?? "{count} members").replace("{count}", String(members.length))}
          </p>
          {isAdmin && (
            <Dialog open={addOpen} onOpenChange={setAddOpen}>
              <DialogTrigger render={<Button variant="outline" size="sm" />}>
                <UserPlus className="h-4 w-4" />
                {t.members?.addTitle ?? "Add Member"}
              </DialogTrigger>
              <DialogContent>
                <DialogHeader>
                  <DialogTitle>{t.members?.addTitle ?? "Add Member"}</DialogTitle>
                  <DialogDescription>
                    {t.members?.addDescription ?? "Enter the user ID (UUID) of the person you want to add"}
                  </DialogDescription>
                </DialogHeader>
                <div className="space-y-4 py-2">
                  <Field>
                    <FieldLabel htmlFor="new-user-id">{t.members?.userIdLabel ?? "User ID"}</FieldLabel>
                    <Input
                      id="new-user-id"
                      type="text"
                      value={newUserId}
                      onChange={(e) => {
                        setNewUserId(e.target.value);
                        setAddError(null);
                      }}
                      placeholder={t.members?.userIdPlaceholder ?? "00000000-0000-0000-0000-000000000000"}
                    />
                    <FieldDescription>
                      {t.members?.userIdDescription ?? "Enter the UUID of the user you want to add to this workspace."}
                    </FieldDescription>
                    <FieldError>{addError}</FieldError>
                  </Field>
                </div>
                <DialogFooter>
                  <DialogClose render={<Button variant="outline" />}>
                    {t.common?.cancel ?? "Cancel"}
                  </DialogClose>
                  <Button onClick={handleAddMember} disabled={addSaving}>
                    {addSaving ? (
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                    ) : (
                      <UserPlus className="h-4 w-4" />
                    )}
                    {t.members?.addButton ?? "Add"}
                  </Button>
                </DialogFooter>
              </DialogContent>
            </Dialog>
          )}
        </div>

        {/* Member rows */}
        <div className="divide-y divide-(--color-border) rounded-lg border border-(--color-border)">
          {members.map((member) => {
            const isOwner = member.userId === ownerId;
            const isSelf = member.userId === currentUser?.id;
            const canManage = isAdmin && !isOwner;
            const isLastAdmin =
              isSelf &&
              member.role === "admin" &&
              adminMembers.length <= 1;

            return (
              <div
                key={member.userId}
                className="flex flex-wrap items-center gap-3 px-4 py-3 sm:flex-nowrap"
              >
                {/* Avatar */}
                <UserAvatar src={member.avatarUrl} name={member.name} size="sm" />

                {/* Name + Email */}
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5">
                    <span className="truncate text-sm font-medium text-(--color-text)">
                      {member.name}
                    </span>
                    {isOwner && (
                      <Crown className="h-3.5 w-3.5 shrink-0 text-amber-500" />
                    )}
                    {isSelf && (
                      <span className="text-xs text-(--color-text-tertiary)">
                        {t.members?.you ?? "(you)"}
                      </span>
                    )}
                  </div>
                  <p className="truncate text-xs text-(--color-text-secondary)">
                    {member.email}
                  </p>
                </div>

                {/* Role badge */}
                {isOwner ? (
                  <Badge variant="default">{t.members?.owner ?? "Owner"}</Badge>
                ) : (
                  <Badge
                    variant={member.role === "admin" ? "default" : "secondary"}
                  >
                    {member.role === "admin" ? (
                      <ShieldCheck className="mr-1 h-3 w-3" />
                    ) : (
                      <Shield className="mr-1 h-3 w-3" />
                    )}
                    {member.role === "admin" ? (t.members?.admin ?? "Admin") : (t.members?.memberRole ?? "Member")}
                  </Badge>
                )}

                {/* Joined date (hide on small screens) */}
                <span className="hidden text-xs text-(--color-text-tertiary) sm:block">
                  {formatDate(member.createdAt, locale)}
                </span>

                {/* Actions (admin only, not for owner) */}
                {canManage && (
                  <div className="flex items-center gap-1">
                    {/* Role change */}
                    <Select
                      value={member.role}
                      onValueChange={(val) => {
                        if (val === null) return;
                        handleRoleChange(member.userId, val);
                      }}
                      disabled={changingRole === member.userId}
                    >
                      <SelectTrigger size="sm" className="h-7 min-w-[7rem]">
                        {changingRole === member.userId && (
                          <LoaderCircle className="h-3.5 w-3.5 animate-spin shrink-0" />
                        )}
                        <span className={changingRole === member.userId ? "opacity-50" : ""}>
                          {member.role === "admin"
                            ? (t.members?.admin ?? "Admin")
                            : (t.members?.memberRole ?? "Member")}
                        </span>
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="admin">{t.members?.admin ?? "Admin"}</SelectItem>
                        <SelectItem value="member">{t.members?.memberRole ?? "Member"}</SelectItem>
                      </SelectContent>
                    </Select>

                    {/* Remove button */}
                    <AlertDialog
                      open={removeTarget?.userId === member.userId}
                      onOpenChange={(open) => {
                        if (!open) setRemoveTarget(null);
                      }}
                    >
                      <AlertDialogTrigger
                        render={
                          <Button
                            variant="ghost"
                            size="icon-sm"
                            className="text-(--color-text-tertiary) hover:text-red-500"
                            onClick={() => setRemoveTarget(member)}
                          />
                        }
                      >
                        <Trash2 className="h-4 w-4" />
                      </AlertDialogTrigger>
                      <AlertDialogContent size="sm">
                        <AlertDialogHeader>
                          <AlertDialogTitle>{t.members?.removeTitle ?? "Remove member?"}</AlertDialogTitle>
                          <AlertDialogDescription>
                            {isLastAdmin
                              ? (t.members?.removeLastAdminWarning ?? "You are the last admin. Removing yourself will leave this workspace without administrators.")
                              : (t.members?.removeDescription ?? "Are you sure you want to remove {name} from this workspace?").replace("{name}", member.name)}
                          </AlertDialogDescription>
                        </AlertDialogHeader>
                        <AlertDialogFooter>
                          <AlertDialogCancel>{t.common?.cancel ?? "Cancel"}</AlertDialogCancel>
                          <AlertDialogAction
                            variant="destructive"
                            onClick={handleRemoveMember}
                            disabled={removeSaving}
                          >
                            {removeSaving ? (
                              <LoaderCircle className="h-4 w-4 animate-spin" />
                            ) : (
                              <Trash2 className="h-4 w-4" />
                            )}
                            {t.members?.removeButton ?? "Remove"}
                          </AlertDialogAction>
                        </AlertDialogFooter>
                      </AlertDialogContent>
                    </AlertDialog>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* ── Ownership Section ── */}
      <Separator />

      <div className="space-y-4">
        <div>
          <h3 className="text-sm font-medium text-(--color-text)">
            {t.members?.ownershipTitle ?? "Workspace Ownership"}
          </h3>
          <p className="text-xs text-(--color-text-secondary)">
            {t.members?.ownershipDescription ?? "The workspace owner has full control over the workspace and cannot be removed. Ownership can be transferred to another admin."}
          </p>
        </div>

        {/* Current owner */}
        {ownerMember && (
          <div className="flex items-center gap-3 rounded-lg border border-(--color-border) bg-(--color-surface-secondary)/30 px-4 py-3">
            <UserAvatar
              src={ownerMember.avatarUrl}
              name={ownerMember.name}
              size="md"
              className="ring-amber-300"
              fallbackClass="bg-amber-500/10 text-amber-600"
            />
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-1.5">
                <span className="text-sm font-medium text-(--color-text)">
                  {ownerMember.name}
                </span>
                  <Badge variant="default" className="bg-amber-500/15 text-amber-600">
                    <Crown className="mr-1 h-3 w-3" />
                    {t.members?.owner ?? "Owner"}
                  </Badge>
              </div>
              <p className="text-xs text-(--color-text-secondary)">
                {ownerMember.email}
              </p>
            </div>

            {/* Transfer button (only owner can transfer) */}
            {isOwner && (
              <Dialog open={transferOpen} onOpenChange={setTransferOpen}>
              <DialogTrigger render={<Button variant="outline" size="sm" />}>
                  <Send className="h-4 w-4" />
                  {t.members?.transferButton ?? "Transfer"}
                </DialogTrigger>
                <DialogContent>
                  <DialogHeader>
                    <DialogTitle>{t.members?.transferTitle ?? "Transfer Ownership"}</DialogTitle>
                    <DialogDescription>
                      {t.members?.transferDescription ?? "Select an admin to become the new workspace owner. You will become a regular admin."}
                    </DialogDescription>
                  </DialogHeader>
                  <div className="space-y-4 py-2">
                    <Field>
                      <FieldLabel htmlFor="new-owner">{t.members?.newOwnerLabel ?? "New Owner"}</FieldLabel>
                      <Select
                        value={transferTargetId}
                        onValueChange={(val) => {
                          if (val === null) return;
                          setTransferTargetId(val);
                          setTransferError(null);
                        }}
                      >
                        <SelectTrigger
                          id="new-owner"
                          className="w-full"
                        >
                          <span className={transferTargetId ? "" : "text-muted-foreground"}>
                            {transferTargetId
                              ? nonOwnerAdmins.find((a) => a.userId === transferTargetId)
                                ?.name ?? transferTargetId
                              : (t.members?.selectAdminPlaceholder ?? "Select an admin...")}
                          </span>
                        </SelectTrigger>
                        <SelectContent>
                          {nonOwnerAdmins.map((admin) => (
                            <SelectItem
                              key={admin.userId}
                              value={admin.userId}
                            >
                              {admin.name} ({admin.email})
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FieldError>{transferError}</FieldError>
                    </Field>
                    {transferTargetId && (
                      <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950/30">
                        <p className="text-xs font-medium text-amber-800 dark:text-amber-200">
                          ⚠️ {t.members?.transferWarning ?? "This action cannot be undone"}
                        </p>
                        <p className="mt-1 text-xs text-amber-700 dark:text-amber-300">
                          {t.members?.transferWarningDesc ?? "The new owner will have full control over this workspace, including the ability to remove you."}
                        </p>
                      </div>
                    )}
                  </div>
                  <DialogFooter>
                    <DialogClose render={<Button variant="outline" />}>
                      {t.common?.cancel ?? "Cancel"}
                    </DialogClose>
                    <Button
                      onClick={handleTransferOwnership}
                      disabled={!transferTargetId || transferSaving}
                    >
                      {transferSaving ? (
                        <LoaderCircle className="h-4 w-4 animate-spin" />
                      ) : (
                        <Send className="h-4 w-4" />
                      )}
                      {t.members?.transferTitle ?? "Transfer Ownership"}
                    </Button>
                  </DialogFooter>
                </DialogContent>
              </Dialog>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
