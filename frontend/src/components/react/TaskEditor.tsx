import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Field, FieldLabel, FieldError } from '@/components/ui/field';
import { Loader2, X } from 'lucide-react';
import { useTranslations, type Locale } from '@/i18n/utils';
import { useTaskStore } from '@/stores/taskStore';
import { createInvalidation, revokeInvalidation, fetchRepetition } from '@/lib/versioning-api';
import { toast } from 'sonner';
import type { Task, TaskStatus, TaskInvalidation } from '@/types/task';
import { isValidTaskTransition, TASK_STATUSES } from '@/types/task';
import { ErrorDisplay } from '@/components/react/ErrorDisplay';
import { ApiRequestError } from '@/lib/api';

interface TaskEditorProps {
  task: Task;
  open: boolean;
  /**
   * True when `task` belongs to a non-current extraction version. While frozen,
   * the dependencies control is disabled and the key is omitted from the save
   * payload (its presence is the write), so the editor can never trigger
   * `TASK_VERSION_FROZEN`; `status` and `labels` stay live in every state and
   * the "Inválida" checkbox is disabled (the server refuses marks on frozen
   * versions with 409 `TASK_VERSION_FROZEN`).
   * Required — WU3 computes it at the call site from the version selector's
   * `is_current`.
   */
  frozen: boolean;
  /**
   * The task's current active mark, as the page read it. When present, the
   * editor opens with the checkbox checked and the reason populated; saving
   * with the checkbox then unchecked asks for confirmation and revokes the
   * mark. `null`/`undefined` means the task is unmarked (or unknown — the
   * server's 409 `TASK_ALREADY_MARKED` stays the backstop).
   */
  activeMark?: TaskInvalidation | null;
  /**
   * Open the editor with the "Inválida" checkbox already checked — the
   * "Marcar como inválida" button's entry point. Nothing is applied until the
   * user saves; cancelling leaves no mark.
   */
  markDefaultChecked?: boolean;
  /**
   * Focus the reason field when the editor opens — the mark button's entry
   * point is "ready to type".
   */
  reasonAutofocus?: boolean;
  /**
   * Called after a confirmed mark write (mark or revoke), with the task's new
   * state, so a parent that renders the card flag can flip it without a
   * re-read. Fires once per confirmed write, before the PUT: the mark exists
   * server-side regardless of whether the PUT succeeds, and a PUT failure must
   * not hide a real mark.
   */
  onInvalidationChange?: (taskId: string, hasActiveInvalidation: boolean) => void;
  onOpenChange: (open: boolean) => void;
  locale?: Locale;
}

function normalizeTag(tag: string): string {
  return tag.trim().toLowerCase();
}

/**
 * Shared fallback for a story whose tasks have not been loaded yet.
 *
 * It has to be ONE stable reference. The siblings selector below used to end with
 * `?? []`, which builds a new array on every call, and zustand v5 subscribes through
 * `useSyncExternalStore`, which compares snapshots with `Object.is`. An unstable snapshot
 * makes React re-render forever: mounting this editor for a story id that was absent from
 * `state.tasks` threw "Maximum update depth exceeded" and the dialog never rendered.
 * Frozen so nothing can mutate the value every mounted editor shares.
 */
const NO_TASKS: readonly Task[] = Object.freeze([]);

export function TaskEditor({
  task,
  open,
  frozen,
  activeMark = null,
  markDefaultChecked = false,
  reasonAutofocus = false,
  onInvalidationChange,
  onOpenChange,
  locale = 'en',
}: TaskEditorProps) {
  const t = useTranslations(locale);
  const updateTask = useTaskStore((s) => s.updateTask);

  const [labels, setLabels] = useState<string[]>(task.labels);
  const [dependencies, setDependencies] = useState<string[]>(task.dependencies);
  const [status, setStatus] = useState<TaskStatus>(task.status);
  const [saving, setSaving] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [saveError, setSaveError] = useState<ApiRequestError | null>(null);

  // ── Mark state (W6-B1) ──
  // `markChecked`/`markReason` are what the user is about to save; `wasMarked`
  // is what the server currently holds, so the save knows whether checking the
  // box means "create" and unchecking it means "revoke". Initializers read the
  // props so the very first render (the one the focus effect runs after) is
  // already correct for the mark button's entry point.
  const [markChecked, setMarkChecked] = useState<boolean>(() => !!activeMark || markDefaultChecked);
  const [markReason, setMarkReason] = useState<string>(() => activeMark?.reason ?? '');
  const [wasMarked, setWasMarked] = useState<boolean>(() => !!activeMark);
  // The confirmation is a property of the SAVE, not of a button: `handleSave`
  // opens it and only its accept path performs the writes. `null` = no
  // confirmation pending.
  const [confirmAction, setConfirmAction] = useState<'mark' | 'unmark' | null>(null);
  // The D16 repetition read: fetched when the mark controls render, shown with
  // the earlier version and reason, and its one action copies that reason into
  // the textarea — a client-side fill that persists nothing.
  const [repetition, setRepetition] = useState<{ versionNumber: number; reason: string } | null>(
    null,
  );
  const reasonRef = useRef<HTMLTextAreaElement>(null);

  // Sibling tasks in the same story are the only valid dependency targets.
  const siblings = useTaskStore((s) => s.tasks[task.storyId] ?? NO_TASKS);
  const siblingOptions = siblings.filter((s) => s.id !== task.id);
  const availableSiblings = siblingOptions.filter(
    (s) => !dependencies.some((d) => normalizeTag(d) === normalizeTag(s.id)),
  );
  const siblingLabel = (dep: string) => siblings.find((s) => s.id === dep)?.title ?? dep;

  // Tag input refs
  const labelInputRef = useRef<HTMLInputElement>(null);
  const [labelInput, setLabelInput] = useState('');

  // Reset form when task or dialog changes. `title`/`description` are not
  // state — they render read-only straight from `task` under the D5/D21 matrix.
  useEffect(() => {
    if (open) {
      setLabels(task.labels);
      setDependencies(task.dependencies);
      setStatus(task.status);
      setSaving(false);
      setErrors({});
      setSaveError(null);
      setLabelInput('');
      setMarkChecked(!!activeMark || markDefaultChecked);
      setMarkReason(activeMark?.reason ?? '');
      setWasMarked(!!activeMark);
      setConfirmAction(null);
      setRepetition(null);
      // The mark button's entry point: focus lands in the reason field, ready
      // to type. The textarea only exists when the checkbox starts checked.
      // Deferred by one tick because the dialog's own focus handling puts the
      // focus on the popup's first tabbable control after mount — the reason
      // field has to win that race.
      if (reasonAutofocus && (!!activeMark || markDefaultChecked)) {
        window.setTimeout(() => reasonRef.current?.focus(), 0);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reset only when the dialog opens or the task changes
  }, [open, task]);

  // The D16 read runs when the mark controls render. It is a read-only
  // warning: it creates, updates and revokes nothing.
  useEffect(() => {
    if (!open) return;
    let active = true;
    fetchRepetition(task.id)
      .then((res) => {
        if (active) setRepetition(res.matches[0] ?? null);
      })
      .catch(() => {
        // A hiccup in the warning read must not block the save: no match shown.
        if (active) setRepetition(null);
      });
    return () => {
      active = false;
    };
  }, [open, task.id]);

  /* ── Label helpers ── */

  const addLabel = useCallback(
    (raw: string) => {
      const tag = raw.trim();
      if (!tag) {
        setErrors((prev) => ({ ...prev, labels: t.taskEditor.labels_empty }));
        return;
      }
      if (labels.some((l) => normalizeTag(l) === normalizeTag(tag))) {
        setErrors((prev) => ({ ...prev, labels: t.taskEditor.labels_duplicate }));
        return;
      }
      setLabels((prev) => [...prev, tag]);
      setLabelInput('');
      setErrors((prev) => ({ ...prev, labels: '' }));
    },
    [labels, t.taskEditor],
  );

  const removeLabel = useCallback((index: number) => {
    setLabels((prev) => prev.filter((_, i) => i !== index));
  }, []);

  /* ── Dependency helpers ── */

  const addDependency = useCallback(
    (raw: string) => {
      const dep = raw.trim();
      if (!dep) {
        setErrors((prev) => ({ ...prev, dependencies: t.taskEditor.dependency_empty }));
        return;
      }
      if (normalizeTag(dep) === normalizeTag(task.id)) {
        setErrors((prev) => ({ ...prev, dependencies: t.taskEditor.dependency_self }));
        return;
      }
      // Only sibling tasks from the same story are valid dependencies.
      if (!siblingOptions.some((s) => s.id === dep)) {
        setErrors((prev) => ({ ...prev, dependencies: t.taskEditor.dependency_same_story }));
        return;
      }
      if (dependencies.some((d) => normalizeTag(d) === normalizeTag(dep))) {
        return; // silent dedup
      }
      setDependencies((prev) => [...prev, dep]);
      setErrors((prev) => ({ ...prev, dependencies: '' }));
    },
    [dependencies, task.id, siblingOptions, t.taskEditor],
  );

  const removeDependency = useCallback((index: number) => {
    setDependencies((prev) => prev.filter((_, i) => i !== index));
  }, []);

  /* ── Key handlers ── */

  const handleLabelKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addLabel(labelInput);
    }
  };

  /* ── Status validation ── */

  // Same rule as the backend: a no-op is always valid, real transitions
  // follow the Kanban flow table.
  const isValidStatus = useCallback(
    (newStatus: TaskStatus) => isValidTaskTransition(task.status, newStatus),
    [task.status],
  );

  /* ── Save ── */

  const handleSave = async () => {
    const localErrors: Record<string, string> = {};
    if (!isValidStatus(status)) {
      // Composed from translated pieces with language-neutral separators, so no
      // English word order is baked in and no raw enum slug reaches the user.
      localErrors.status = `${t.taskEditor.invalid_transition}: ${t.kanban.columns[task.status]} → ${t.kanban.columns[status]}`;
    }
    // The reason is mandatory when marking: blocking here issues no request at
    // all, and the server's 422 stays the backstop.
    if (markChecked && markReason.trim() === '') {
      localErrors.markReason = t.taskEditor.mark_reason_missing;
    }
    if (Object.keys(localErrors).length > 0) {
      setErrors(localErrors);
      return;
    }

    // The confirmation is a property of the save: a save that would create or
    // revoke a mark first asks, and cancelling it issues no request. A save
    // whose mark state does not change goes straight to the writes.
    const pendingMark: 'mark' | 'unmark' | null =
      markChecked && !wasMarked ? 'mark' : !markChecked && wasMarked ? 'unmark' : null;
    if (pendingMark) {
      setConfirmAction(pendingMark);
      return;
    }

    await performSave(null);
  };

  /**
   * The write sequence: the mark write first (POST create / DELETE revoke),
   * then the PUT with the contract fields. Any failure stops the sequence,
   * shows the error and keeps the dialog open with the edits intact — the
   * store rolls its optimistic update back internally.
   */
  const performSave = async (pendingMark: 'mark' | 'unmark' | null) => {
    setConfirmAction(null);
    setSaving(true);
    setSaveError(null);

    try {
      if (pendingMark === 'mark') {
        await createInvalidation(task.id, markReason.trim());
        setWasMarked(true);
        onInvalidationChange?.(task.id, true);
      } else if (pendingMark === 'unmark') {
        await revokeInvalidation(task.id);
        setWasMarked(false);
        onInvalidationChange?.(task.id, false);
      }

      // Store handles optimistic update + server response + rollback internally.
      // On failure it re-throws so we can show the error and keep the dialog open.
      // D5/D21 field matrix: the write contract is status/labels/dependencies
      // only — `title` and `description` render read-only because the backend
      // refuses them. `status` and `labels` stay live in every state, including
      // frozen; the `dependencies` key is omitted while frozen so its presence
      // can never trigger `TASK_VERSION_FROZEN` on a frozen version.
      const payload: { status: TaskStatus; labels: string[]; dependencies?: string[] } = {
        status,
        labels,
      };
      if (!frozen) payload.dependencies = dependencies;
      await updateTask(task.id, payload);
      setSaving(false);
      toast.success(t.taskEditor.saved);
      onOpenChange(false);
    } catch (err) {
      // Store already rolled back the optimistic update.
      setSaving(false);
      if (err instanceof ApiRequestError) {
        setSaveError(err);
      } else {
        // Wrap unknown errors
        setSaveError(
          new ApiRequestError(
            0,
            'Unknown Error',
            err instanceof Error ? err.message : 'Unknown error',
            err,
          ),
        );
      }
      // Keep dialog open so the user can retry.
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t.taskEditor.title}</DialogTitle>
          <DialogDescription>{t.taskEditor.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-5">
          {/* Title — read-only text under the D5/D21 field matrix: the write
              contract no longer accepts it, so an editable control that cannot
              save would be a lie. */}
          <Field>
            <FieldLabel>{t.taskEditor.title_label}</FieldLabel>
            <p id="te-title" className="text-sm text-foreground">
              {task.title}
            </p>
          </Field>

          {/* Description — read-only text, same matrix rule as the title. */}
          <Field>
            <FieldLabel>{t.taskEditor.description_label}</FieldLabel>
            <p id="te-description" className="text-sm whitespace-pre-wrap text-muted-foreground">
              {task.description}
            </p>
          </Field>

          {/* Status */}
          <Field>
            <FieldLabel htmlFor="te-status">{t.taskEditor.status_label}</FieldLabel>
            <select
              id="te-status"
              value={status}
              onChange={(e) => setStatus(e.target.value as TaskStatus)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              aria-invalid={!!errors.status}
            >
              {TASK_STATUSES.map((s) => (
                <option
                  key={s}
                  value={s}
                  disabled={!isValidStatus(s)}
                  className={isValidStatus(s) ? '' : 'text-muted-foreground/50'}
                >
                  {isValidStatus(s) ? '✓ ' : '✗ '} {t.kanban.columns[s]}{' '}
                  {isValidStatus(s) ? '' : ` (${t.taskEditor.invalid_transition})`}
                </option>
              ))}
            </select>
            <FieldError>{errors.status}</FieldError>
          </Field>

          {/* Labels */}
          <Field>
            <FieldLabel htmlFor="te-labels">{t.taskEditor.labels_label}</FieldLabel>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {labels.map((label, i) => (
                <Badge key={`${label}-${i}`} variant="secondary" className="gap-1 pr-1">
                  {label}
                  <button
                    type="button"
                    onClick={() => removeLabel(i)}
                    className="ml-0.5 rounded-full p-0.5 hover:bg-muted-foreground/20 transition-colors"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
            <Input
              id="te-labels"
              ref={labelInputRef}
              value={labelInput}
              onChange={(e) => {
                setLabelInput(e.target.value);
                setErrors((prev) => ({ ...prev, labels: '' }));
              }}
              onKeyDown={handleLabelKeyDown}
              placeholder={t.taskEditor.labels_placeholder}
              aria-invalid={!!errors.labels}
            />
            <FieldError>{errors.labels}</FieldError>
          </Field>

          {/* Dependencies — multi-select of sibling tasks in the same story (by task.id) */}
          <Field>
            <FieldLabel htmlFor="te-deps">{t.taskEditor.dependencies_label}</FieldLabel>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {dependencies.map((dep, i) => (
                <Badge key={`${dep}-${i}`} variant="outline" className="gap-1 pr-1">
                  {siblingLabel(dep)}
                  <button
                    type="button"
                    onClick={() => removeDependency(i)}
                    disabled={frozen}
                    className="ml-0.5 rounded-full p-0.5 hover:bg-muted-foreground/20 transition-colors disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <X className="h-3 w-3" />
                  </button>
                </Badge>
              ))}
            </div>
            <select
              id="te-deps"
              value=""
              onChange={(e) => {
                if (e.target.value) addDependency(e.target.value);
              }}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
              aria-invalid={!!errors.dependencies}
              disabled={frozen || availableSiblings.length === 0}
            >
              <option value="">{t.taskEditor.dependencies_placeholder}</option>
              {availableSiblings.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.title}
                </option>
              ))}
            </select>
            <FieldError>{errors.dependencies}</FieldError>
          </Field>

          {/* Mark controls: one checkbox, a mandatory reason when it is checked,
              the D16 repetition notice, and the two confirmations as properties
              of the save. Disabled while frozen — the server refuses marks and
              revokes on a frozen version with 409 TASK_VERSION_FROZEN. */}
          <Field>
            <label
              htmlFor="te-mark"
              className="flex w-fit items-center gap-2 text-sm font-medium text-foreground"
            >
              <input
                type="checkbox"
                id="te-mark"
                checked={markChecked}
                disabled={frozen}
                onChange={(e) => setMarkChecked(e.target.checked)}
                className="h-4 w-4 accent-primary disabled:cursor-not-allowed disabled:opacity-50"
              />
              {t.taskEditor.mark_label}
            </label>
          </Field>

          {repetition && (
            <div
              role="status"
              className="flex items-start justify-between gap-3 rounded-lg border border-amber-200 bg-amber-50 p-3 dark:border-amber-900 dark:bg-amber-950/30"
            >
              <p className="text-sm text-amber-800 dark:text-amber-200">
                {t.taskEditor.repetition_notice
                  .replace('{version}', String(repetition.versionNumber))
                  .replace('{reason}', repetition.reason)}
              </p>
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => setMarkReason(repetition.reason)}
              >
                {t.taskEditor.repetition_copy}
              </Button>
            </div>
          )}

          {markChecked && (
            <Field>
              <FieldLabel htmlFor="te-mark-reason">{t.taskEditor.mark_reason_label}</FieldLabel>
              <textarea
                id="te-mark-reason"
                ref={reasonRef}
                value={markReason}
                onChange={(e) => {
                  setMarkReason(e.target.value);
                  setErrors((prev) => ({ ...prev, markReason: '' }));
                }}
                placeholder={t.taskEditor.mark_reason_placeholder}
                rows={3}
                aria-invalid={!!errors.markReason}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
              />
              <FieldError>{errors.markReason}</FieldError>
            </Field>
          )}
        </div>

        {saveError && (
          <ErrorDisplay
            friendlyMessage={t.taskEditor.error_save}
            rawDetail={saveError.rawError.rawBody}
            status={saveError.status}
            errorCode={saveError.errorCode}
            retryLabel={t.taskEditor.save}
            onRetry={handleSave}
            onDismiss={() => setSaveError(null)}
            locale={locale}
          />
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={saving}
          >
            {t.taskEditor.cancel}
          </Button>
          <Button type="button" onClick={handleSave} disabled={saving}>
            {saving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            {saving ? t.taskEditor.saving : t.taskEditor.save}
          </Button>
        </DialogFooter>

        {/* The mark/unmark confirmation: opened by the save itself, and only
            its accept path performs the writes — cancelling issues no request
            and leaves the editor open with the user's edits. */}
        <AlertDialog
          open={confirmAction !== null}
          onOpenChange={(o) => {
            if (!o) setConfirmAction(null);
          }}
        >
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>
                {confirmAction === 'unmark'
                  ? t.taskEditor.unmark_confirm_title
                  : t.taskEditor.mark_confirm_title}
              </AlertDialogTitle>
              <AlertDialogDescription>
                {confirmAction === 'unmark'
                  ? t.taskEditor.unmark_confirm_body
                  : t.taskEditor.mark_confirm_body}
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>{t.taskEditor.cancel}</AlertDialogCancel>
              <AlertDialogAction
                onClick={() => {
                  if (confirmAction) void performSave(confirmAction);
                }}
              >
                {confirmAction === 'unmark'
                  ? t.taskEditor.unmark_confirm_accept
                  : t.taskEditor.mark_confirm_accept}
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </DialogContent>
    </Dialog>
  );
}
