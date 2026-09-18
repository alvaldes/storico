import { useEffect, useState } from 'react';
import { LoaderCircle } from 'lucide-react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Field, FieldDescription, FieldError, FieldLabel } from '@/components/ui/field';
import { Input } from '@/components/ui/input';
import { ApiRequestError } from '@/lib/api';
import { createCustomProvider, renameCustomProvider } from '@/lib/custom-providers-api';
import {
  PROVIDER_NAME_MAX_LENGTH,
  isKnownProvider,
  isReservedProviderName,
  isValidProviderName,
  normalizeProviderName,
} from '@/lib/llm-providers';
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
 * survives: a 409 from the server does not say whether it was the reserved-name
 * guard or a duplicate in this workspace.
 *
 * The name is free-form text, stored as typed: the field caps it at
 * ``PROVIDER_NAME_MAX_LENGTH`` and shows the count, so the limit is visible instead
 * of arriving as a rejection.
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

  const trimmed = normalizeProviderName(name);
  const unchanged = isRename && trimmed === provider.name;
  const canSubmit = !saving && trimmed.length > 0 && !unchanged;

  /**
   * Which rule a refused name broke, in the user's language.
   *
   * Ordered so the message names the rule that was actually broken: a built-in name
   * is not "already registered", and a name that is only too long is not "reserved".
   * The built-in comparison is case-insensitive, matching the backend, because the
   * name keeps its casing now.
   */
  const nameError = (value: string): string => {
    if (isKnownProvider(value.toLowerCase())) return t.workspace.llmCustomProviderNameKnown;
    if (isReservedProviderName(value)) return t.workspace.llmCustomProviderNameReserved;
    return t.workspace.llmCustomProviderNameInvalid;
  };

  const handleOpenChange = (next: boolean) => {
    if (saving) return;
    onOpenChange(next);
  };

  const handleSubmit = async () => {
    if (!canSubmit) return;

    // Checked before the request so the user is told which rule they hit rather
    // than a generic conflict.
    if (!isValidProviderName(trimmed)) {
      setError(nameError(trimmed));
      return;
    }

    setSaving(true);
    setError(null);
    try {
      const saved = provider
        ? await renameCustomProvider(workspaceId, provider.id, { name: trimmed })
        : await createCustomProvider(workspaceId, { name: trimmed });
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
            maxLength={PROVIDER_NAME_MAX_LENGTH}
            autoComplete="off"
            spellCheck={false}
            disabled={saving}
            aria-invalid={error ? true : undefined}
          />
          <div className="flex items-center text-xs">
            <div className="flex-1">
              <FieldError>{error}</FieldError>
            </div>
            <span className="text-muted-foreground">
              {name.length}/{PROVIDER_NAME_MAX_LENGTH}
            </span>
          </div>
          <FieldDescription>{t.workspace.llmCustomProviderNameHint}</FieldDescription>
        </Field>

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
