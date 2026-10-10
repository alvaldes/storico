'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useProjectStore } from '@/stores/projectStore';
import { useTranslations, type Locale } from '@/i18n/utils';
import { Button } from '@/components/ui/button';
import { CopyButton } from '@/components/ui/copy-button';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, Download, ExternalLink } from 'lucide-react';
import { toast } from 'sonner';
import { ErrorDisplay } from '@/components/react/ErrorDisplay';
import { ApiRequestError } from '@/lib/api';
import { listStories } from '@/lib/stories-api';
import { listVersions } from '@/lib/versioning-api';
import {
  EXPORT_FORMATS,
  fetchTaskExportBlob,
  getTaskExportPreview,
  isFileExportFormat,
  resolveExportTarget,
  type ExportFormat,
} from '@/lib/task-export-api';
import {
  getTrelloExport,
  isTerminalTrelloExportStatus,
  previewTrelloExport,
  triggerTrelloExport,
  type TrelloExportJob,
} from '@/lib/trello-api';
import type { UserStory, StoryVersion } from '@/types/story';

/** The extraction poll's cadence (2 s); D5 makes the export ride the same shape. */
const TRELLO_POLL_INTERVAL_MS = 2000;

/**
 * One failure this page renders: a refused trigger, an unanswered poll, a
 * refused download or a failed preview. All of them travel the same card, and
 * the canonical envelope's `error_code` is translated when the backend named
 * one.
 */
interface ExportFailure {
  message: string;
  errorCode?: string;
  status?: number;
  rawDetail?: unknown;
}

function toFailure(err: unknown, fallback: string): ExportFailure {
  if (err instanceof ApiRequestError) {
    return {
      message: err.message || fallback,
      errorCode: err.errorCode,
      status: err.status,
      rawDetail: err.rawError.rawBody,
    };
  }
  return { message: err instanceof Error ? err.message : fallback };
}

interface ExportPanelProps {
  locale?: Locale;
}

/**
 * The export page, as one section.
 *
 * One toolbar states what will be exported — project → story → version, where
 * the project selector carries *all projects* (the whole workspace) and the
 * version selector is disabled until a story is chosen, because a version
 * belongs to a story and the API answers `422` otherwise. The four formats are
 * what you do with the selection: CSV, JSON and MD are the file download
 * served by `GET …/export/tasks`; Trello keeps its trigger, its poll and its
 * board link. The preview fetches what would be exported — the file body via
 * `preview=true`, the board plan via the Trello preview — and shows it
 * read-only with a copy button (E2): nothing typed there could change what is
 * exported, so nothing there can be typed.
 *
 * Every path builds its request from `resolveExportTarget` (`lib/task-export-api.ts`),
 * the one resolver all four formats share, so no two paths can disagree about
 * what is selected.
 */
export function ExportPanel({ locale = 'en' }: ExportPanelProps) {
  const t = useTranslations(locale);
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspace?.id);
  const { projects, fetchProjects } = useProjectStore();

  const [format, setFormat] = useState<ExportFormat>('json');

  /* ── The toolbar's cascade: project → story → version ── */

  // Moving up the cascade clears everything below it, so the resolved target
  // can never name a story orphaned from its project or a version orphaned
  // from its story. `null` at a level means "not narrowed here".
  const [projectFilter, setProjectFilter] = useState<string | null>(null);
  const [storyFilter, setStoryFilter] = useState<string | null>(null);
  const [versionFilter, setVersionFilter] = useState<string | null>(null);
  const [storyOptions, setStoryOptions] = useState<UserStory[]>([]);
  const [versions, setVersions] = useState<StoryVersion[]>([]);

  /* ── The preview ── */

  const [previewText, setPreviewText] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<ExportFailure | null>(null);
  const [previewNonce, setPreviewNonce] = useState(0);

  /* ── The file download ── */

  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<ExportFailure | null>(null);

  /* ── The Trello export ── */

  const [trelloStarting, setTrelloStarting] = useState(false);
  const [trelloJob, setTrelloJob] = useState<TrelloExportJob | null>(null);
  const [trelloFailure, setTrelloFailure] = useState<ExportFailure | null>(null);

  /**
   * The one resolved target behind every request this page makes — the file
   * export's query, the Trello body and both previews read this same value.
   *
   * The cascade already makes the levels coherent, and `resolveExportTarget`
   * closes the construction: even a state holding every id yields one target,
   * so the backend's `422` refusals are unreachable from here rather than
   * merely unlikely.
   */
  const target = useMemo(
    () => resolveExportTarget(projectFilter, storyFilter, versionFilter),
    [projectFilter, storyFilter, versionFilter],
  );

  // Fetch projects if they haven't been loaded yet (the toolbar's first level),
  // exactly as the Kanban board feeds its filter select.
  useEffect(() => {
    if (workspaceId && projects.length === 0) {
      void fetchProjects();
    }
  }, [workspaceId, projects.length, fetchProjects]);

  // Stories of the selected project, capped at 100 like every story list read.
  // A failed read leaves the story select empty and so unusable — narrowing to
  // a story then becomes impossible, which fails safe: the export falls back
  // to the project, never to a scope the user did not pick.
  useEffect(() => {
    if (!workspaceId || !projectFilter) {
      setStoryOptions([]);
      return;
    }
    let active = true;
    listStories(projectFilter, 1, 100, workspaceId)
      .then((page) => {
        if (active) setStoryOptions(page.items);
      })
      .catch(() => {
        if (active) setStoryOptions([]);
      });
    return () => {
      active = false;
    };
  }, [workspaceId, projectFilter]);

  // The chosen story's versions, the same read the story page's selector uses.
  // A failed read leaves only the current-version row — the export falls back
  // to the current versions, never to a version the user did not pick.
  useEffect(() => {
    if (!storyFilter) {
      setVersions([]);
      return;
    }
    let active = true;
    listVersions(storyFilter)
      .then((history) => {
        if (active) setVersions(history);
      })
      .catch(() => {
        if (active) setVersions([]);
      });
    return () => {
      active = false;
    };
  }, [storyFilter]);

  const handleProjectChange = useCallback((value: string | null) => {
    setProjectFilter(value ?? null);
    setStoryFilter(null);
    setVersionFilter(null);
  }, []);

  const handleStoryChange = useCallback((value: string | null) => {
    setStoryFilter(value ?? null);
    // The version choice belonged to the previous story; a version that
    // survived the switch would be an extraction of a story this export no
    // longer names.
    setVersionFilter(null);
  }, []);

  const handleVersionChange = useCallback((value: string | null) => {
    setVersionFilter(value ?? null);
  }, []);

  // The preview: what would be exported, read from the same endpoints the
  // actions use — the file body via `preview=true` (the exact bytes the
  // download saves, minus the attachment header) and the Trello board plan via
  // the preview endpoint, which creates no job. One selection, one read.
  useEffect(() => {
    if (!workspaceId) return;
    let active = true;
    setPreviewLoading(true);
    setPreviewError(null);
    const read = isFileExportFormat(format)
      ? getTaskExportPreview(workspaceId, format, target)
      : previewTrelloExport(workspaceId, target).then((plan) => JSON.stringify(plan, null, 2));
    read
      .then((text) => {
        if (active) setPreviewText(text);
      })
      .catch((err: unknown) => {
        if (!active) return;
        setPreviewText(null);
        setPreviewError(toFailure(err, t.exportPage.preview_error));
      })
      .finally(() => {
        if (active) setPreviewLoading(false);
      });
    return () => {
      active = false;
    };
  }, [workspaceId, format, target, previewNonce, t]);

  const handleDownload = async () => {
    if (!workspaceId || !isFileExportFormat(format)) return;
    setDownloading(true);
    setDownloadError(null);
    try {
      const { blob, filename } = await fetchTaskExportBlob(workspaceId, format, target);
      // Trigger download
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename ?? `tasks-export.${format === 'markdown' ? 'md' : format}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);
      toast.success(`Tasks exported as ${format.toUpperCase()}`);
    } catch (err) {
      setDownloadError(toFailure(err, t.exportPage.error_download));
      toast.error(t.exportPage.error_download);
    } finally {
      setDownloading(false);
    }
  };

  const handleTrelloExport = async () => {
    if (!workspaceId) return;
    setTrelloStarting(true);
    setTrelloFailure(null);
    try {
      const job = await triggerTrelloExport(workspaceId, target);
      setTrelloJob(job);
    } catch (err) {
      setTrelloFailure(toFailure(err, t.exportPage.trello_error_start));
    } finally {
      setTrelloStarting(false);
    }
  };

  // The poll (D5): while the job is pending or running, one GET every interval,
  // scheduled only by the previous answer — a terminal state removes the timer's
  // reason to exist, so polling stops instead of being capped.
  useEffect(() => {
    if (!trelloJob || !workspaceId) return;
    if (isTerminalTrelloExportStatus(trelloJob.status)) return;
    const timer = setTimeout(() => {
      getTrelloExport(workspaceId, trelloJob.id)
        .then((next) => setTrelloJob(next))
        .catch((err: unknown) => {
          // A poll that cannot be answered must not hammer the endpoint either:
          // stop here and show what the failure carried. The job row keeps the
          // board reachable if it existed.
          setTrelloFailure(toFailure(err, t.exportPage.trello_error_generic));
        });
    }, TRELLO_POLL_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [trelloJob, workspaceId, t]);

  if (!workspaceId) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
        <Download className="mb-3 h-10 w-10 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">{t.exportPage.no_workspace}</p>
      </div>
    );
  }

  const trelloJobTerminal = trelloJob ? isTerminalTrelloExportStatus(trelloJob.status) : false;

  // Select options, the board's convention: the top-level "not narrowed" row
  // (value `null`), and rows that read as the human sentence — a project by
  // its name, a story as `${actor}: ${feature}`, a version as `v{n}`.
  const projectItems = useMemo<{ label: string; value: string | null }[]>(
    () => [
      { label: t.exportPage.scope_workspace, value: null },
      ...projects.map((p) => ({ label: p.name, value: p.id })),
    ],
    [projects, t],
  );
  const storyItems = useMemo<{ label: string; value: string | null }[]>(
    () => [
      { label: t.exportPage.scope_all_stories, value: null },
      ...storyOptions.map((s) => ({ label: `${s.actor}: ${s.feature}`, value: s.id })),
    ],
    [storyOptions, t],
  );
  const versionItems = useMemo<{ label: string; value: string | null }[]>(
    () => [
      { label: t.exportPage.scope_version_current, value: null },
      ...versions.map((v) => ({ label: `v${v.versionNumber ?? '?'}`, value: v.id })),
    ],
    [versions, t],
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{t.exportPage.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t.exportPage.description}</p>
      </div>

      {/* The one section: the toolbar states what will be exported, the format
          selector states what will be done with it, the preview shows it, and
          the action — download or Trello trigger — does it. */}
      <section className="rounded-xl border border-border bg-(--color-surface) p-6 space-y-5">
        {/* Scope cascade: all projects (the whole workspace) by default,
            narrowed by project, then story, then version. The story select
            stays disabled until a project is chosen, and the version select
            until a story is — a version belongs to a story, and the API
            answers `422` for one asked at project or workspace level, so the
            controls make that impossible instead of letting the user find
            out. The resolved target carries exactly one target — never two. */}
        <div className="flex flex-wrap items-center gap-2">
          <Select value={projectFilter} onValueChange={handleProjectChange} items={projectItems}>
            <SelectTrigger className="w-56" aria-label={t.exportPage.scope_project_label}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {projectItems.map((item) => (
                  <SelectItem key={item.value ?? '_all_projects'} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          <Select
            value={storyFilter}
            onValueChange={handleStoryChange}
            disabled={!projectFilter}
            items={storyItems}
          >
            <SelectTrigger className="w-56" aria-label={t.exportPage.scope_story_label}>
              <SelectValue>
                {projectFilter ? undefined : t.exportPage.scope_select_project}
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {storyItems.map((item) => (
                  <SelectItem key={item.value ?? '_all_stories'} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          <Select
            value={versionFilter}
            onValueChange={handleVersionChange}
            disabled={!storyFilter}
            items={versionItems}
          >
            <SelectTrigger className="w-56" aria-label={t.exportPage.scope_version_label}>
              <SelectValue>{storyFilter ? undefined : t.exportPage.scope_select_story}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {versionItems.map((item) => (
                  <SelectItem key={item.value ?? '_current_version'} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        {/* Format selector — the four formats, in the order the product serves
            them. CSV, JSON and MD are the file download against the same
            selection; Trello is the fourth disposition. */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t.exportPage.format_label}</label>
          <div className="flex gap-2">
            {EXPORT_FORMATS.map((f) => (
              <button
                key={f}
                type="button"
                onClick={() => setFormat(f)}
                className={`flex-1 rounded-lg border px-4 py-3 text-sm font-medium text-left transition-all ${
                  format === f
                    ? 'border-primary bg-primary/5 text-primary shadow-xs'
                    : 'border-border bg-(--color-surface) text-muted-foreground hover:text-foreground hover:bg-muted/30'
                }`}
              >
                {t.exportPage[`format_${f}`]}
              </button>
            ))}
          </div>
        </div>

        {/* The preview: exactly what the action would export, read from the
            same endpoints — read-only by decision (E2): the text is shown and
            copied, never submitted back. */}
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-foreground">{t.exportPage.preview_label}</p>
            <CopyButton
              text={previewText ?? ''}
              label={t.exportPage.copy}
              copiedLabel={t.exportPage.copied}
              disabled={!previewText}
              className="text-muted-foreground hover:text-foreground"
            />
          </div>
          {previewLoading && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              {t.exportPage.preview_loading}
            </div>
          )}
          {!previewLoading && previewText !== null && (
            <pre
              data-testid="export-preview"
              className="max-h-80 overflow-auto rounded-lg border border-border bg-background/50 p-3 font-mono text-xs break-all whitespace-pre-wrap text-foreground/90"
            >
              {previewText}
            </pre>
          )}
          {previewError && (
            <ErrorDisplay
              friendlyMessage={previewError.message}
              rawDetail={previewError.rawDetail}
              status={previewError.status}
              errorCode={previewError.errorCode}
              retryLabel={t.common.retry}
              onRetry={() => setPreviewNonce((n) => n + 1)}
              locale={locale}
            />
          )}
        </div>

        {/* The action for the chosen format. */}
        {isFileExportFormat(format) ? (
          /* The download is enabled with a workspace selected even when the
             selection holds no tasks: the backend returns valid empty
             content. */
          <Button onClick={handleDownload} disabled={downloading} className="w-full">
            {downloading ? (
              <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            ) : (
              <Download className="mr-2 h-4 w-4" />
            )}
            {downloading ? t.exportPage.downloading : t.exportPage.download}
          </Button>
        ) : (
          <div className="space-y-2">
            {/* D3, stated where the button is rather than buried: re-exporting
                creates a second board, on purpose. */}
            <p className="text-xs text-muted-foreground">{t.exportPage.trello_new_board_note}</p>
            <Button onClick={handleTrelloExport} disabled={trelloStarting} className="w-full">
              {trelloStarting ? (
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
              ) : (
                <ExternalLink className="mr-2 h-4 w-4" />
              )}
              {trelloStarting ? t.exportPage.trello_triggering : t.exportPage.trello_trigger}
            </Button>
          </div>
        )}

        {/* ── The Trello job: in flight, completed, or failed. ── */}
        {format === 'trello' && trelloJob && !trelloJobTerminal && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t.exportPage.trello_running}
          </div>
        )}
        {format === 'trello' && trelloJob?.status === 'completed' && (
          <div className="space-y-2">
            <p className="text-sm font-medium text-foreground">{t.exportPage.trello_completed}</p>
            {trelloJob.cardsCreated !== null && (
              <p className="text-sm text-muted-foreground">
                {t.exportPage.trello_cards_created.replace(
                  '{count}',
                  String(trelloJob.cardsCreated),
                )}
              </p>
            )}
            {trelloJob.boardUrl && (
              <a
                href={trelloJob.boardUrl}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-sm font-medium text-primary underline"
              >
                <ExternalLink className="h-4 w-4" />
                {t.exportPage.trello_board_link}
              </a>
            )}
          </div>
        )}
        {format === 'trello' && trelloJob?.status === 'failed' && (
          <ErrorDisplay
            // Headline priority inside ErrorDisplay: the translated code beats
            // this fallback sentence — the failure speaks its own registry copy.
            friendlyMessage={t.exportPage.trello_error_generic}
            errorCode={trelloJob.errorCode ?? undefined}
            retryLabel={t.exportPage.trello_trigger}
            onRetry={handleTrelloExport}
            locale={locale}
          />
        )}
        {format === 'trello' && trelloJob?.status === 'failed' && trelloJob.boardUrl && (
          // A half-built board stays reachable: the job row keeps its URL on
          // failure, and burying it would lose work the API says exists.
          <a
            href={trelloJob.boardUrl}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-sm font-medium text-primary underline"
          >
            <ExternalLink className="h-4 w-4" />
            {t.exportPage.trello_board_link}
          </a>
        )}
        {format === 'trello' && trelloFailure && (
          <ErrorDisplay
            friendlyMessage={trelloFailure.message}
            rawDetail={trelloFailure.rawDetail}
            status={trelloFailure.status}
            errorCode={trelloFailure.errorCode}
            retryLabel={t.exportPage.trello_trigger}
            onRetry={handleTrelloExport}
            onDismiss={() => setTrelloFailure(null)}
            locale={locale}
          />
        )}

        {/* ── The download's failure. ── */}
        {downloadError && (
          <ErrorDisplay
            friendlyMessage={downloadError.message}
            rawDetail={downloadError.rawDetail}
            status={downloadError.status}
            errorCode={downloadError.errorCode}
            retryLabel={t.exportPage.retry_download}
            onRetry={handleDownload}
            onDismiss={() => setDownloadError(null)}
            locale={locale}
          />
        )}
      </section>
    </div>
  );
}
