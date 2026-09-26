import { useEffect, useRef, useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Field, FieldLabel, FieldDescription } from '@/components/ui/field';
import { FileUp, Loader2, X } from 'lucide-react';
import { useTranslations, type Locale } from '@/i18n/utils';
import { ErrorDisplay } from '@/components/react/ErrorDisplay';
import { ApiRequestError } from '@/lib/api';
import { readImportFailure } from '@/lib/stories-api';
import { useStoryStore } from '@/stores/storyStore';
import type {
  StoryImportDuplicate,
  StoryImportFailure,
  StoryImportReport,
} from '@/types/story';

/** Anything a row-level error or a skipped duplicate carries to explain itself. */
export interface ImportReasonItem {
  reason: string;
  field?: string;
  length?: number;
  max?: number;
  observed?: number;
  expected?: number;
  firstLine?: number;
}

/**
 * Map a backend reason code to its localized sentence, replacing the
 * `{...}` placeholders from the item. Unknown codes fall back to
 * `stories.import_reason_unknown` instead of leaking raw backend text.
 */
export function describeImportReason(
  t: ReturnType<typeof useTranslations>,
  item: ImportReasonItem,
): string {
  const s = t.stories;
  switch (item.reason) {
    case 'missing_field':
      return s.import_reason_missing_field.replace('{field}', item.field ?? '');
    case 'empty_field':
      return s.import_reason_empty_field.replace('{field}', item.field ?? '');
    case 'too_long':
      return s.import_reason_too_long
        .replace('{field}', item.field ?? '')
        .replace('{length}', String(item.length ?? 0))
        .replace('{max}', String(item.max ?? 0));
    case 'unparsable_story':
      return s.import_reason_unparsable_story;
    case 'field_count_mismatch':
      return s.import_reason_field_count_mismatch
        .replace('{observed}', String(item.observed ?? 0))
        .replace('{expected}', String(item.expected ?? 0));
    case 'parts_look_like_a_full_story':
      return s.import_reason_parts_look_like_a_full_story;
    case 'duplicate':
      return s.import_reason_duplicate;
    case 'duplicate_in_file':
      return s.import_reason_duplicate_in_file.replace('{firstLine}', String(item.firstLine ?? 0));
    case 'invalid_encoding':
      return s.import_reason_invalid_encoding;
    case 'header_unrecognized':
      return s.import_reason_header_unrecognized;
    case 'too_many_rows':
      return s.import_reason_too_many_rows.replace('{max}', String(item.max ?? 0));
    case 'malformed_csv':
      return s.import_reason_malformed_csv;
    case 'empty_file':
      return s.import_reason_empty_file;
    default:
      return s.import_reason_unknown;
  }
}

/**
 * Format a byte count as a human-readable size (binary units, matching what
 * the backend limit counts). `2097152` must read as "2 MB", not as a raw
 * number a person has to divide by hand.
 */
export function formatFileSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB'] as const;
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit++;
  }
  const rounded = unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  return `${rounded} ${units[unit]}`;
}

interface ImportStoriesDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  locale?: Locale;
  projectId: string;
  workspaceId: string;
}

/**
 * CSV import dialog for the stories list. Holds its own run state; the store's
 * `importStories` refreshes the list itself when something was created, so this
 * dialog only renders the report it gets back.
 */
export function ImportStoriesDialog({
  open,
  onOpenChange,
  locale = 'en',
  projectId,
  workspaceId,
}: ImportStoriesDialogProps) {
  const t = useTranslations(locale);
  const importStories = useStoryStore((s) => s.importStories);

  const [file, setFile] = useState<File | null>(null);
  const [running, setRunning] = useState(false);
  const [report, setReport] = useState<StoryImportReport | null>(null);
  const [failure, setFailure] = useState<StoryImportFailure | null>(null);
  const [submitError, setSubmitError] = useState<ApiRequestError | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  /* ── a fresh open must never show a previous run's report ── */
  useEffect(() => {
    if (open) {
      setFile(null);
      setRunning(false);
      setReport(null);
      setFailure(null);
      setSubmitError(null);
      if (inputRef.current) inputRef.current.value = '';
    }
  }, [open]);

  const handleSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    if (!file || running || !projectId || !workspaceId) return;
    setRunning(true);
    setReport(null);
    setFailure(null);
    setSubmitError(null);
    try {
      const result = await importStories({ workspaceId, projectId, file });
      setReport(result);
    } catch (err) {
      const typed = readImportFailure(err);
      if (typed) {
        setFailure(typed);
      } else if (err instanceof ApiRequestError) {
        setSubmitError(err);
      } else {
        // Same wrap StoryForm does: a plain network/proxy error still gets an
        // honest card instead of an unhandled rejection.
        setSubmitError(
          new ApiRequestError(
            0,
            'Unknown Error',
            err instanceof Error ? err.message : 'Unknown error',
            err,
          ),
        );
      }
    } finally {
      setRunning(false);
    }
  };

  const lineLabel = (line: number) =>
    t.stories.import_error_line.replace('{line}', String(line));

  const renderDuplicate = (item: StoryImportDuplicate, index: number) => (
    <li key={`${item.line}-${item.reason}-${index}`} className="text-sm">
      <span className="font-medium">{lineLabel(item.line)}</span>
      {' — '}
      <span className="text-muted-foreground">{describeImportReason(t, item)}</span>
    </li>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{t.stories.import_title}</DialogTitle>
          <DialogDescription>{t.stories.import_description}</DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-5">
          <Field>
            <FieldLabel htmlFor="import-csv-file">{t.stories.import_file_label}</FieldLabel>
            {/* Visually hidden but focusable: keyboard users reach the input
                directly, and the label above is associated with it. */}
            <input
              ref={inputRef}
              id="import-csv-file"
              type="file"
              accept=".csv,text/csv"
              className="sr-only"
              disabled={running}
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setReport(null);
                setFailure(null);
                setSubmitError(null);
              }}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => inputRef.current?.click()}
                disabled={running}
              >
                <FileUp className="h-4 w-4" />
                {t.stories.import_file_label}
              </Button>
              {file && (
                <>
                  <span className="max-w-48 truncate text-sm text-foreground" title={file.name}>
                    {file.name}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={t.common.clear}
                    onClick={() => {
                      setFile(null);
                      if (inputRef.current) inputRef.current.value = '';
                    }}
                    disabled={running}
                  >
                    <X className="h-4 w-4" />
                  </Button>
                </>
              )}
            </div>
            <FieldDescription>{t.stories.import_file_hint}</FieldDescription>
          </Field>

          {/* ── SUCCESS ── */}
          {report && (
            <div className="space-y-3">
              <p className="text-sm font-medium text-foreground">{t.stories.import_result_title}</p>
              {report.created === 0 ? (
                // Nothing was created: say so plainly instead of a proud "0 created".
                <p className="text-sm text-muted-foreground">{t.stories.import_result_none}</p>
              ) : (
                <p className="text-sm text-foreground">
                  {t.stories.import_result_summary
                    .replace('{created}', String(report.created))
                    .replace('{skipped}', String(report.skipped))}
                </p>
              )}
              {report.duplicates.length > 0 && (
                <div className="space-y-1">
                  <p className="text-sm font-medium text-foreground">
                    {t.stories.import_duplicates_title}
                  </p>
                  <ul className="space-y-1">{report.duplicates.map(renderDuplicate)}</ul>
                </div>
              )}
            </div>
          )}

          {/* ── ROW-LEVEL FAILURE: nothing was saved ── */}
          {failure && failure.kind === 'rows' && (
            <div className="space-y-2" role="alert">
              <p className="text-sm font-medium text-destructive">{t.stories.import_errors_title}</p>
              <p className="text-sm text-muted-foreground">{t.stories.import_errors_hint}</p>
              {/* The backend allows 1000 rows and can report on many of them:
                  scroll the report, never push the footer off screen. */}
              <div className="max-h-64 space-y-3 overflow-y-auto rounded-lg border border-border bg-muted/30 p-3">
                <ul className="space-y-1">
                  {failure.errors.map((item, index) => (
                    <li key={`${item.line}-${item.reason}-${index}`} className="text-sm">
                      <span className="font-medium">{lineLabel(item.line)}</span>
                      {' — '}
                      <span className="text-muted-foreground">{describeImportReason(t, item)}</span>
                    </li>
                  ))}
                </ul>
                {failure.duplicates.length > 0 && (
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-foreground">
                      {t.stories.import_duplicates_title}
                    </p>
                    <ul className="space-y-1">{failure.duplicates.map(renderDuplicate)}</ul>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* ── FILE-LEVEL FAILURE ── */}
          {failure && failure.kind === 'file' && (
            <p role="alert" className="text-sm text-destructive">
              {failure.errorCode === 'IMPORT_FILE_TOO_LARGE'
                ? t.stories.import_file_too_large.replace(
                    '{max}',
                    formatFileSize(failure.max ?? 0),
                  )
                : t.stories.import_file_rejected.replace(
                    '{reason}',
                    describeImportReason(t, { reason: failure.reason ?? '' }),
                  )}
            </p>
          )}

          {submitError && (
            <ErrorDisplay
              friendlyMessage={submitError.message}
              rawDetail={submitError.rawError.rawBody}
              status={submitError.status}
              errorCode={submitError.errorCode}
              retryLabel={t.stories.import_submit}
              onRetry={handleSubmit}
              onDismiss={() => setSubmitError(null)}
              locale={locale}
            />
          )}

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={running}
            >
              {t.common.cancel}
            </Button>
            <Button type="submit" disabled={!file || running}>
              {running ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  {t.stories.import_running}
                </>
              ) : (
                t.stories.import_submit
              )}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
