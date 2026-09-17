import { useEffect, useState } from 'react';
import { LoaderCircle, TriangleAlert } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field, FieldDescription, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { ApiRequestError } from '@/lib/api';
import { createCustomProvider, renameCustomProvider } from '@/lib/custom-providers-api';
import { isKnownProvider, isValidProviderName, normalizeProviderName } from '@/lib/llm-providers';
import type { CustomProvider } from '@/types/workspace';
import en from '@/i18n/en.json';
import es from '@/i18n/es.json';

interface CustomProviderDialogProps {
  locale: 'en' | 'es';
  workspaceId: string;
  /**
   * The provider being renamed, or `null` to register a new one.
   *
   * The same dialog serves both because the only difference is which request is
   * sent and which words are shown; a second component would duplicate the name
   * rule and the error handling.
   */
  provider: CustomProvider | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Called with the saved row so the caller can select it and refresh its list. */
  onSaved: (provider: CustomProvider) => void;
}

/**
 * Modal for registering or renaming a workspace custom provider.
 *
 * The name is validated here as well as by the backend so the specific reason
 * survives: a 409 from the server does not say whether it was the built-in guard or
 * a duplicate in this workspace.
 */
export function CustomProviderDialog({
  locale,
  workspaceId,
  provider,
  open,
  onOpenChange,
  onSaved,
}: CustomProviderDialogProps) {
  const t = locale === 'es' ? es : en;
  const isRename = provider !== null;

  const [name, setName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Reset on open so a previous attempt's text and error never leak into the next
  // one: the dialog is reused for every provider in the workspace.
  useEffect(() => {
    if (!open) return;
    setName(provider?.name ?? '');
    setError(null);
    setSaving(false);
  }, [open, provider]);

  const normalized = normalizeProviderName(name);
  const unchanged = isRename && normalized === provider.name;
  const canSubmit = !saving && normalized.length > 0 && !unchanged;

  const handleOpenChange = (next: boolean) => {
    if (saving) return;
    onOpenChange(next);
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;

    // Checked before the request so the user is told which rule they hit rather
    // than a generic conflict.
    if (!isValidProviderName(normalized)) {
      setError(t.workspace.llmCustomProviderNameInvalid);
      return;
    }
    if (isKnownProvider(normalized)) {
      setError(t.workspace.llmCustomProviderNameKnown);
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const saved = provider
        ? await renameCustomProvider(workspaceId, provider.id, { name: normalized })
        : await createCustomProvider(workspaceId, { name: normalized });
      onSaved(saved);
      onOpenChange(false);
    } catch (err) {
      // Locally-valid names can still collide, and that is what a 409 means here: the
      // built-in and malformed cases were already answered above.
      setError(
        err instanceof ApiRequestError && err.status === 409
          ? t.workspace.llmCustomProviderDuplicate
          : t.workspace.llmCustomProviderSaveError,
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>
            {isRename
              ? t.workspace.llmCustomProviderRenameTitle
              : t.workspace.llmCustomProviderAddTitle}
          </DialogTitle>
          <DialogDescription>
            {isRename
              ? t.workspace.llmCustomProviderRenameDescription
              : t.workspace.llmCustomProviderAddDescription}
          </DialogDescription>
        </DialogHeader>

        <Field>
          <FieldLabel htmlFor="custom-provider-name">
            {t.workspace.llmCustomProviderNameLabel}
          </FieldLabel>
          <Input
            id="custom-provider-name"
            type="text"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              // A message about the previous value would be about a name the user
              // has already moved on from.
              setError(null);
            }}
            placeholder={t.workspace.llmCustomProviderPlaceholder}
            autoComplete="off"
            spellCheck={false}
            disabled={saving}
            aria-invalid={error ? true : undefined}
          />
          <FieldDescription>{t.workspace.llmCustomProviderNameHint}</FieldDescription>
        </Field>

        {error && (
          <p
            role="alert"
            className="flex items-start gap-1.5 text-sm text-red-600 dark:text-red-400"
          >
            <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            {error}
          </p>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => handleOpenChange(false)}
            disabled={saving}
          >
            {t.common.cancel}
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={!canSubmit}>
            {saving && <LoaderCircle className="h-4 w-4 animate-spin" />}
            {isRename
              ? t.workspace.llmCustomProviderConfirmRename
              : t.workspace.llmCustomProviderConfirmAdd}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
