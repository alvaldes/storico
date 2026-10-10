import React, { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Field, FieldGroup, FieldLabel } from '@/components/ui/field';
import { api, ApiRequestError } from '@/lib/api';
import { errorCodeHeadline } from '@/lib/error-codes';
import { renderBoldMarkup } from '@/lib/render-bold-markup';
import { useAuthStore } from '@/stores/authStore';
import { getTranslations, type Locale } from '@/i18n/utils';
import { TriangleAlert, LoaderCircle } from 'lucide-react';

interface DeleteAccountDialogProps {
  locale: Locale;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DeleteAccountDialog({ locale, open, onOpenChange }: DeleteAccountDialogProps) {
  const t = getTranslations(locale);
  const user = useAuthStore((s) => s.user);
  const clearAuth = useAuthStore((s) => s.clear);
  const [emailInput, setEmailInput] = useState('');
  const [verifyInput, setVerifyInput] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Expected verification phrase from translations
  const expectedPhrase = t.settings.danger_delete_dialog_verify_phrase;

  // Normalize for comparison
  const normalizedEmail = user?.email?.toLowerCase().trim() ?? '';
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
      await api.delete('/api/v1/users/me');
      clearAuth();
      onOpenChange(false);
      // Redirect to home after successful deletion
      window.location.assign('/');
    } catch (err) {
      // A designed refusal carries a stable `error_code` (e.g. the account-delete 409,
      // `ACCOUNT_DELETE_BLOCKED`); the user gets that code's localized sentence through
      // the error-code map, never the raw status text the HTTP layer builds from an
      // object `detail`. Codes the frontend has not learned fall through to the raw
      // message, and non-API errors keep the generic fallback.
      const headline =
        err instanceof ApiRequestError ? errorCodeHeadline(err.errorCode, locale) : undefined;
      setError(headline ?? (err instanceof Error ? err.message : t.settings.danger_delete_dialog_error));
    } finally {
      setDeleting(false);
    }
  };

  const handleOpenChange = (open: boolean) => {
    if (!deleting) {
      // Reset state when closing
      setEmailInput('');
      setVerifyInput('');
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
            <DialogDescription>
              {renderBoldMarkup(t.settings.danger_delete_dialog_description_1, 'b')}
            </DialogDescription>

            {/* Warning note */}
            <div
              role="note"
              className="flex items-start gap-3 rounded-md border border-(--color-destructive-border) bg-(--color-destructive-bg) px-3 py-2 text-sm text-(--color-destructive-text)"
            >
              <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" />
              <span>{t.settings.danger_delete_dialog_description_2}</span>
            </div>

            {/* Confirmation fields */}
            <FieldGroup>
              <Field>
                <FieldLabel>
                  {/* The {email} placeholder is substituted before the split, in the same order
                      the inlined helper used, so the value can never become an authored tag. */}
                  {renderBoldMarkup(
                    t.settings.danger_delete_dialog_email_label.replace('{email}', user?.email ?? ''),
                    'b',
                  )}
                </FieldLabel>
                <Input
                  value={emailInput}
                  onChange={(e) => setEmailInput(e.target.value)}
                  autoComplete="off"
                  spellCheck={false}
                  disabled={deleting}
                />
              </Field>
              <Field>
                <FieldLabel>
                  {renderBoldMarkup(t.settings.danger_delete_dialog_verify_label, 'b')}
                </FieldLabel>
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
            {error && <p className="text-sm text-destructive">{error}</p>}
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
              className="border-(--color-destructive-border) text-destructive hover:bg-(--color-destructive-bg) hover:text-(--color-destructive-text) disabled:border-input disabled:text-muted-foreground disabled:hover:bg-transparent"
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
