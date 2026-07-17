import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Field,
  FieldGroup,
  FieldLabel,
} from "@/components/ui/field";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/authStore";
import { useTranslations, type Locale } from "@/i18n/utils";
import { TriangleAlert, LoaderCircle } from "lucide-react";

interface DeleteAccountDialogProps {
  locale: Locale;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DeleteAccountDialog({
  locale,
  open,
  onOpenChange,
}: DeleteAccountDialogProps) {
  const t = useTranslations(locale);
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clear);
  const [emailInput, setEmailInput] = useState("");
  const [verifyInput, setVerifyInput] = useState("");
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Expected verification phrase from translations
  const expectedPhrase = t.settings.danger_delete_dialog_verify_phrase;

  // Normalize for comparison
  const normalizedEmail = user?.email?.toLowerCase().trim() ?? "";
  const normalizedEmailInput = emailInput.toLowerCase().trim();
  const normalizedVerifyInput = verifyInput.toLowerCase().trim();
  const normalizedExpectedPhrase = expectedPhrase.toLowerCase().trim();

  const canDelete =
    !deleting &&
    normalizedEmailInput.length > 0 &&
    normalizedEmailInput === normalizedEmail &&
    normalizedVerifyInput === normalizedExpectedPhrase;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canDelete) return;

    setDeleting(true);
    setError(null);

    try {
      await api.delete("/api/v1/users/me");
      clearAuth();
      onOpenChange(false);
      // Redirect to home after successful deletion
      window.location.href = "/";
    } catch (err) {
      const message =
        err instanceof Error
          ? err.message
          : t.settings.danger_delete_dialog_error;
      setError(message);
    } finally {
      setDeleting(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!deleting) {
      // Reset state when closing
      setEmailInput("");
      setVerifyInput("");
      setError(null);
      onOpenChange(open);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[480px]" showCloseButton={false}>
        <form onSubmit={handleSubmit}>
          <DialogHeader>
            <DialogTitle>{t.settings.danger_delete_dialog_title}</DialogTitle>
          </DialogHeader>

          <div className="space-y-5 py-2">
            {/* Description */}
            <DialogDescription
              dangerouslySetInnerHTML={{
                __html: t.settings.danger_delete_dialog_description_1,
              }}
            />

            {/* Warning note */}
            <div
              role="note"
              className="flex items-start gap-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/30 dark:text-red-200"
            >
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{t.settings.danger_delete_dialog_description_2}</span>
            </div>

            {/* Confirmation fields */}
            <FieldGroup>
              <Field>
                <FieldLabel
                  dangerouslySetInnerHTML={{
                    __html: t.settings.danger_delete_dialog_email_label.replace(
                      "{email}",
                      user?.email ?? "",
                    ),
                  }}
                />
                <Input
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={deleting}
                />
              </Field>
              <Field>
                <FieldLabel
                  dangerouslySetInnerHTML={{
                    __html: t.settings.danger_delete_dialog_verify_label,
                  }}
                />
                <Input
                  value={verifyInput}
                  onChange={(e) => setVerifyInput(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={deleting}
                />
              </Field>
            </FieldGroup>

            {/* Error message */}
            {error && (
              <p className="text-sm text-red-600 dark:text-red-400">{error}</p>
            )}
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleOpenChange(false)}
              disabled={deleting}
            >
              {t.settings.danger_delete_dialog_cancel}
            </Button>
            <Button
              type="submit"
              variant="outline"
              disabled={!canDelete}
              className="border-red-300 text-red-600 hover:bg-red-100 hover:text-red-700 disabled:border-input disabled:text-muted-foreground disabled:hover:bg-transparent dark:border-red-800 dark:text-red-400 dark:hover:bg-red-900/50 dark:hover:text-red-300"
            >
              {deleting ? (
                <span className="inline-flex items-center gap-2">
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                  {t.settings.danger_delete_dialog_deleting}
                </span>
              ) : (
                t.settings.danger_delete_dialog_confirm
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
