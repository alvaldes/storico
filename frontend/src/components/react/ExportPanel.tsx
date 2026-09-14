'use client';

import { useState, useEffect, useCallback } from 'react';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useTranslations, type Locale } from '@/i18n/utils';
import { Button } from '@/components/ui/button';
import { Loader2, Download } from 'lucide-react';
import { toast } from 'sonner';
import { ErrorDisplay } from '@/components/react/ErrorDisplay';

interface ExportPanelProps {
  locale?: Locale;
}

export function ExportPanel({ locale = 'en' }: ExportPanelProps) {
  const t = useTranslations(locale);
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspace?.id);
  const { workspaceTasks, loading, error, fetchTasksForWorkspace } = useTaskStore();

  const [format, setFormat] = useState<'json' | 'markdown'>('json');
  const [downloading, setDownloading] = useState(false);
  const [initialLoad, setInitialLoad] = useState(true);
  const [downloadError, setDownloadError] = useState<Error | null>(null);

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

        {/* Download button */}
        <Button onClick={handleDownload} disabled={!hasTasks || downloading} className="w-full">
          {downloading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <Download className="mr-2 h-4 w-4" />
          )}
          {downloading ? t.exportPage.downloading : t.exportPage.download}
        </Button>
      </div>

      {/* Task load error — retry */}
      {error && !initialLoad && (
        <ErrorDisplay
          friendlyMessage={t.exportPage.error_fetch}
          rawDetail={error}
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
          retryLabel={t.common.retry}
          onRetry={handleDownload}
          onDismiss={() => setDownloadError(null)}
          locale={locale}
        />
      )}
    </div>
  );
}
