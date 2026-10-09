'use client';

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useProjectStore } from '@/stores/projectStore';
import { useTranslations, type Locale } from '@/i18n/utils';
import { Button } from '@/components/ui/button';
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
import {
  getTrelloExport,
  isTerminalTrelloExportStatus,
  resolveTrelloExportTarget,
  triggerTrelloExport,
  type TrelloExportJob,
} from '@/lib/trello-api';
import type { UserStory } from '@/types/story';

/** The extraction poll's cadence (2 s); D5 makes the export ride the same shape. */
const TRELLO_POLL_INTERVAL_MS = 2000;

/** One failure the Trello section renders: trigger refusals and poll faults. */
interface TrelloFailure {
  message: string;
  errorCode?: string;
  status?: number;
  rawDetail?: unknown;
}

interface ExportPanelProps {
  locale?: Locale;
}

export function ExportPanel({ locale = 'en' }: ExportPanelProps) {
  const t = useTranslations(locale);
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspace?.id);
  const { workspaceTasks, loading, error, fetchTasksForWorkspace } = useTaskStore();
  const { projects, fetchProjects } = useProjectStore();

  const [format, setFormat] = useState<'json' | 'markdown'>('json');
  const [downloading, setDownloading] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  const [downloadError, setDownloadError] = useState<Error | null>(null);

  /* ── Trello export state ── */

  // The scope cascade (D1), the board's pattern: project → story, moving up
  // clears everything below, and `null` at a level means "not narrowed here".
  const [projectFilter, setProjectFilter] = useState<string | null>(null);
  const [storyFilter, setStoryFilter] = useState<string | null>(null);
  const [storyOptions, setStoryOptions] = useState<UserStory[]>([]);
  const [trelloStarting, setTrelloStarting] = useState(false);
  const [trelloJob, setTrelloJob] = useState<TrelloExportJob | null>(null);
  const [trelloFailure, setTrelloFailure] = useState<TrelloFailure | null>(null);

  // Fetch tasks on mount
  const doFetch = useCallback(async () => {
    if (!workspaceId) return;
    setInitialLoad(true);
    await fetchTasksForWorkspace(workspaceId);
    setInitialLoad(false);
  }, [workspaceId, fetchTasksForWorkspace]);

  // Fetch on mount and when workspace changes
  useEffect(() => {
    doFetch();
  }, [doFetch]);

  // Fetch projects if they haven't been loaded yet (needed for the scope dropdown),
  // exactly as the Kanban board feeds its filter select.
  useEffect(() => {
    if (workspaceId && projects.length === 0) {
      void fetchProjects();
    }
  }, [workspaceId, projects.length, fetchProjects]);

  // Stories of the selected project, capped at 100 like every story list read.
  // A failed read leaves the story select empty and so unusable — narrowing to a
  // story then becomes impossible, which fails safe: the export falls back to
  // the project, never to a scope the user did not pick.
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

  // Moving up the cascade clears everything below it, so the resolved target can
  // never name a story orphaned from its project.
  const handleProjectChange = useCallback((value: string | null) => {
    setProjectFilter(value ?? null);
    setStoryFilter(null);
  }, []);

  const handleStoryChange = useCallback((value: string | null) => {
    setStoryFilter(value ?? null);
  }, []);

  /**
   * The request body's scope: exactly one target, resolved most-specific-wins.
   *
   * The cascade already makes two levels coherent, and `resolveTrelloExportTarget`
   * closes the construction: even a state holding both ids yields a body with one
   * key, so the backend's `422` for two targets is unreachable from here rather
   * than merely unlikely.
   */
  const trelloTarget = useMemo(
    () => resolveTrelloExportTarget(projectFilter, storyFilter),
    [projectFilter, storyFilter],
  );

  // Select options, the board's convention: the top-level "whole workspace" row
  // (value `null`) means "not narrowed", and a story row reads as the human
  // sentence `${actor}: ${feature}`, never the short id.
  const projectItems = useMemo<{ label: string; value: string | null }[]>(
    () => [
      { label: t.exportPage.trello_scope_workspace, value: null },
      ...projects.map((p) => ({ label: p.name, value: p.id })),
    ],
    [projects, t],
  );
  const storyItems = useMemo<{ label: string; value: string | null }[]>(
    () => [
      { label: t.exportPage.trello_scope_all_stories, value: null },
      ...storyOptions.map((s) => ({ label: `${s.actor}: ${s.feature}`, value: s.id })),
    ],
    [storyOptions, t],
  );

  const handleTrelloExport = async () => {
    if (!workspaceId) return;
    setTrelloStarting(true);
    setTrelloFailure(null);
    try {
      const job = await triggerTrelloExport(workspaceId, trelloTarget);
      setTrelloJob(job);
    } catch (err) {
      if (err instanceof ApiRequestError) {
        setTrelloFailure({
          message: err.message,
          errorCode: err.errorCode,
          status: err.status,
          rawDetail: err.rawError.rawBody,
        });
      } else {
        setTrelloFailure({ message: err instanceof Error ? err.message : String(err) });
      }
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
          if (err instanceof ApiRequestError) {
            setTrelloFailure({
              message: err.message,
              errorCode: err.errorCode,
              status: err.status,
              rawDetail: err.rawError.rawBody,
            });
          } else {
            setTrelloFailure({ message: err instanceof Error ? err.message : String(err) });
          }
        });
    }, TRELLO_POLL_INTERVAL_MS);
    return () => clearTimeout(timer);
  }, [trelloJob, workspaceId]);

  const handleDownload = async () => {
    if (!workspaceId) return;

    const baseUrl = import.meta.env.PUBLIC_API_URL || '';
    const url = `${baseUrl}/api/v1/workspaces/${workspaceId}/export/tasks?format=${format}`;

    setDownloading(true);
    setDownloadError(null);
    try {
      const response = await fetch(url, { credentials: 'include' });
      if (!response.ok) {
        let detail: unknown;
        try {
          const errorBody = await response.json();
          detail = errorBody.detail ?? errorBody.message ?? errorBody;
        } catch {
          detail = `HTTP ${response.status}`;
        }
        throw new Error(detail as string, { cause: { status: response.status, detail } });
      }

      const blob = await response.blob();
      const disposition = response.headers.get('Content-Disposition');
      const filename = disposition
        ? disposition.split('filename=')[1]?.replace(/['"]/g, '')
        : `tasks-export.${format === 'json' ? 'json' : 'md'}`;

      // Trigger download
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);

      toast.success(`Tasks exported as ${format.toUpperCase()}`);
    } catch (err) {
      setDownloadError(err instanceof Error ? err : new Error(String(err)));
      toast.error(t.exportPage.error_download);
    } finally {
      setDownloading(false);
    }
  };

  if (!workspaceId) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
        <Download className="mb-3 h-10 w-10 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">{t.exportPage.no_workspace}</p>
      </div>
    );
  }

  if (initialLoad && loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const hasTasks = workspaceTasks.length > 0;
  const trelloJobTerminal = trelloJob ? isTerminalTrelloExportStatus(trelloJob.status) : false;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">{t.exportPage.title}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{t.exportPage.description}</p>
      </div>

      <div className="rounded-xl border border-border bg-(--color-surface) p-6 space-y-5">
        {/* Format selector */}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">{t.exportPage.format_label}</label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setFormat('json')}
              className={`flex-1 rounded-lg border px-4 py-3 text-sm font-medium text-left transition-all ${
                format === 'json'
                  ? 'border-primary bg-primary/5 text-primary shadow-xs'
                  : 'border-border bg-(--color-surface) text-muted-foreground hover:text-foreground hover:bg-muted/30'
              }`}
            >
              {t.exportPage.format_json}
            </button>
            <button
              type="button"
              onClick={() => setFormat('markdown')}
              className={`flex-1 rounded-lg border px-4 py-3 text-sm font-medium text-left transition-all ${
                format === 'markdown'
                  ? 'border-primary bg-primary/5 text-primary shadow-xs'
                  : 'border-border bg-(--color-surface) text-muted-foreground hover:text-foreground hover:bg-muted/30'
              }`}
            >
              {t.exportPage.format_markdown}
            </button>
          </div>
        </div>

        {/* Task count */}
        <div className="text-sm text-muted-foreground">
          {hasTasks
            ? `${workspaceTasks.length} task${workspaceTasks.length === 1 ? '' : 's'} to export`
            : t.exportPage.no_tasks}
        </div>

        {/* Download button — enabled with a workspace selected even when it
                has no tasks: the backend returns valid empty content. */}
        <Button onClick={handleDownload} disabled={downloading} className="w-full">
          {downloading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Download className="mr-2 h-4 w-4" />
          )}
          {downloading ? t.exportPage.downloading : t.exportPage.download}
        </Button>
      </div>

      {/* Trello export: the scope cascade, the trigger and its poll (D1, D3, D5). */}
      <section className="rounded-xl border border-border bg-(--color-surface) p-6 space-y-5">
        <div>
          <h2 className="text-base font-semibold text-foreground">
            {t.exportPage.trello_section_title}
          </h2>
          <p className="mt-1 text-sm text-muted-foreground">
            {t.exportPage.trello_section_description}
          </p>
        </div>

        {/* Scope cascade: whole workspace by default, narrowed by project, then
            story. The story select stays disabled until a project is chosen, and
            the resolved body carries exactly one target — never two. */}
        <div className="space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <Select
              value={projectFilter}
              onValueChange={handleProjectChange}
              items={projectItems}
            >
              <SelectTrigger
                className="w-56"
                aria-label={t.exportPage.trello_scope_project_label}
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {projectItems.map((item) => (
                    <SelectItem key={item.value ?? '_whole_workspace'} value={item.value}>
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
              <SelectTrigger className="w-56" aria-label={t.exportPage.trello_scope_story_label}>
                <SelectValue>
                  {projectFilter ? undefined : t.exportPage.trello_scope_select_project}
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
          </div>
        </div>

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

        {/* The job: in flight, completed, or failed. */}
        {trelloJob && !trelloJobTerminal && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            {t.exportPage.trello_running}
          </div>
        )}
        {trelloJob?.status === 'completed' && (
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
        {trelloJob?.status === 'failed' && (
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
        {trelloJob?.status === 'failed' && trelloJob.boardUrl && (
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

        {/* A refused trigger or an unanswered poll — with the canonical envelope's
            code translated when the backend named one. */}
        {trelloFailure && (
          <ErrorDisplay
            friendlyMessage={trelloFailure.message || t.exportPage.trello_error_start}
            rawDetail={trelloFailure.rawDetail}
            status={trelloFailure.status}
            errorCode={trelloFailure.errorCode}
            retryLabel={t.exportPage.trello_trigger}
            onRetry={handleTrelloExport}
            onDismiss={() => setTrelloFailure(null)}
            locale={locale}
          />
        )}
      </section>

      {/* Task load error — retry */}
      {error && !initialLoad && (
        <ErrorDisplay
          friendlyMessage={t.exportPage.error_fetch}
          // This page supplies its own headline, so the store's message belongs in the detail
          // rather than in the sentence. Falling back to it keeps the disclosure panel from
          // being empty when the failure carried no body at all.
          rawDetail={error.rawDetail ?? error.friendlyMessage}
          status={error.status}
          errorCode={error.errorCode}
          retryLabel={t.common.retry}
          onRetry={() => workspaceId && fetchTasksForWorkspace(workspaceId)}
          locale={locale}
        />
      )}

      {/* Download error — retry */}
      {downloadError && (
        <ErrorDisplay
          friendlyMessage={downloadError.message}
          rawDetail={downloadError.cause}
          status={(downloadError.cause as { status?: number })?.status}
          retryLabel={t.exportPage.retry_download}
          onRetry={handleDownload}
          onDismiss={() => setDownloadError(null)}
          locale={locale}
        />
      )}
    </div>
  );
}
