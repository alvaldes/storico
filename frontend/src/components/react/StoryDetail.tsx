import { useEffect, useState } from 'react';
import {
  ArrowLeft,
  Pencil,
  Trash2,
  Sparkles,
  Loader2,
  LoaderCircle,
  FileText,
  ListTree,
  Fingerprint,
  CheckCircle2,
  AlertCircle,
  Flag,
} from 'lucide-react';
import { shortUUID } from '@/lib/utils';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useAuthStore } from '@/stores/authStore';
import { getProject } from '@/lib/projects-api';
import { getLLMConfigStatus, type LLMConfigStatus } from '@/lib/llm-config-api';
import { listInvalidations, listStoryInvalidations } from '@/lib/versioning-api';
import { canManageVersions } from '@/lib/workspace-role';
import type { StoryVersion } from '@/types/story';
import type { TaskInvalidation } from '@/types/task';
import { StoryForm } from '@/components/react/StoryForm';
import { TaskEditor } from '@/components/react/TaskEditor';
import { VersionSelector } from '@/components/react/VersionSelector';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
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
import { toast } from 'sonner';
import { useTranslations, localizedPath, type Locale } from '@/i18n/utils';
import { ErrorDisplay } from '@/components/react/ErrorDisplay';

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  pending_extraction: 'outline',
  extracting: 'secondary',
  extracted: 'default',
  failed_extraction: 'destructive',
};

interface StoryDetailProps {
  locale?: Locale;
  storyId: string;
}

export function StoryDetail({ locale = 'en', storyId }: StoryDetailProps) {
  const t = useTranslations(locale);
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspace?.id);
  const workspaceRole = useWorkspaceStore((s) => s.currentWorkspace?.role);
  const currentWorkspace = useWorkspaceStore((s) => s.currentWorkspace);
  const currentUserId = useAuthStore((s) => s.user?.id);
  const { stories, loading: storyLoading, fetchStory, updateStory, deleteStory, fetchVersions, versionsByStory } = useStoryStore();
  const {
    tasks,
    loading: tasksLoading,
    extractions,
    fetchTasks,
    extractTasks,
    resetExtraction,
  } = useTaskStore();

  const [initialLoad, setInitialLoad] = useState(true);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteSaving, setDeleteSaving] = useState(false);
  const [editingTaskId, setEditingTaskId] = useState<string | null>(null);
  // Which entry point opened the editor: the "Marcar como inválida" button
  // opens it with the mark checkbox checked and the focus in the reason field
  // (the Edit pencil does not). Nothing is applied until the user saves.
  const [markIntent, setMarkIntent] = useState(false);
  // The edited task's active mark, read when the editor opens. `'loading'` is
  // the read in flight; the editor renders only once it has settled, so its
  // checkbox/reason initializers see the final value.
  const [activeMark, setActiveMark] = useState<TaskInvalidation | null | 'loading'>(null);
  // The story's version history, read into the store so the delete dialog's
  // version count and the selector share one read. `null` is "the read has not
  // answered (or failed)": the selector stays hidden and the page falls back
  // to its pre-versioning behavior instead of blocking on a hiccup.
  const versions = versionsByStory[storyId] ?? null;
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  // The tasks the story-scoped marks read answered as actively marked, by id.
  // It is the card flag's only source, so marking a task needs no re-read: the
  // editor's confirmed write flips this set through `onInvalidationChange`. A
  // failed read leaves it empty — the flags stay unmarked rather than blocking
  // the page, the same posture the versions read has.
  const [markedTaskIds, setMarkedTaskIds] = useState<ReadonlySet<string>>(() => new Set());
  // Whether the extract confirmation is open. The confirmation is where the
  // version facts are named; the store's request only starts on accept.
  const [extractConfirming, setExtractConfirming] = useState(false);
  const [parentProject, setParentProject] = useState<{ id: string; name: string } | null>(null);
  const [resolvingProject, setResolvingProject] = useState(false);
  // Track previous extraction status to detect failure transitions during polling
  const [prevExtractionStatus, setPrevExtractionStatus] = useState<string | null>(null);
  // Whether this workspace can extract at all. `null` is "not answered yet", and it is
  // also what an unreachable status route leaves behind: both let the action through,
  // because the API still refuses a configuration that cannot work. Failing closed here
  // would lock the user out of the attempt over a hiccup in the answer.
  const [llmStatus, setLlmStatus] = useState<LLMConfigStatus | null>(null);

  const story = stories.find((s) => s.id === storyId);
  const storyTasks = tasks[storyId] ?? [];
  const extraction = extractions[storyId];

  useEffect(() => {
    fetchStory(storyId).then(() => setInitialLoad(false));
  }, [fetchStory, storyId]);

  // Version-aware task read (W6-B1): without a selected version the backend's
  // current-version predicate answers; with one, the read carries the selected
  // version's extraction_id so a frozen version shows its OWN tasks.
  useEffect(() => {
    fetchTasks(storyId, selectedVersionId ?? undefined);
  }, [fetchTasks, storyId, selectedVersionId]);

  // Load the version history once per story, into the store. The selector read
  // doubles as the delete dialog's version count here — the dialog reuses what
  // the page has.
  useEffect(() => {
    void fetchVersions(storyId);
  }, [fetchVersions, storyId]);

  // Read the story's active marks once, for the card flags. One request for the
  // whole story: the read is story-scoped and the page already knows which
  // tasks it is showing.
  useEffect(() => {
    let active = true;
    listStoryInvalidations(storyId)
      .then((marks) => {
        if (active) setMarkedTaskIds(new Set(marks.map((mark) => mark.taskId)));
      })
      .catch(() => {
        if (active) setMarkedTaskIds(new Set());
      });
    return () => {
      active = false;
    };
  }, [storyId]);

  // The confirmed mark write flips the set, so the card updates without a
  // re-read. A mark that was already created and a PUT that then failed still
  // count: the mark exists server-side regardless of the PUT.
  const handleInvalidationChange = (taskId: string, hasActiveInvalidation: boolean) => {
    setMarkedTaskIds((previous) => {
      const next = new Set(previous);
      if (hasActiveInvalidation) next.add(taskId);
      else next.delete(taskId);
      return next;
    });
  };

  // Default the displayed version to the current one once the history lands.
  useEffect(() => {
    if (!versions) return;
    if (selectedVersionId === null || !versions.some((v) => v.id === selectedVersionId)) {
      setSelectedVersionId(versions.find((v) => v.isCurrent)?.id ?? versions[0]?.id ?? null);
    }
  }, [versions, selectedVersionId]);

  // Follow the run the user just started: as soon as the version the 202 minted
  // shows up in the history — pending or settled — it becomes the displayed one,
  // so the selector names the run instead of waiting for a reload. The effect
  // only re-runs when the history or the minted number changes, so a manual
  // selection made while the run is going still sticks until the next refresh.
  useEffect(() => {
    const minted = extraction?.versionNumber;
    if (!versions || minted == null) return;
    const match = versions.find((v) => v.versionNumber === minted);
    if (match) setSelectedVersionId(match.id);
  }, [versions, extraction?.versionNumber]);

  // Reset extraction state on unmount
  useEffect(() => {
    return () => {
      resetExtraction(storyId);
    };
  }, [storyId, resetExtraction]);

  // Read the edited task's active mark when the editor opens, whichever entry
  // point opened it: an already-marked task must open with the checkbox checked
  // and the reason populated. The editor renders only once this read settles,
  // so its initial state sees the final value. A failed read leaves the task
  // treated as unmarked — the server's 409 TASK_ALREADY_MARKED is the backstop.
  useEffect(() => {
    if (!editingTaskId) return;
    let active = true;
    setActiveMark('loading');
    listInvalidations(editingTaskId)
      .then((history) => {
        if (active) setActiveMark(history.find((m) => m.revokedAt === null) ?? null);
      })
      .catch(() => {
        if (active) setActiveMark(null);
      });
    return () => {
      active = false;
    };
  }, [editingTaskId]);

  // Ask once per workspace whether extraction is possible here, so the refusal can be
  // shown before the attempt instead of only after it fails.
  useEffect(() => {
    if (!workspaceId) {
      setLlmStatus(null);
      return;
    }
    let active = true;
    getLLMConfigStatus(workspaceId)
      .then((status) => {
        if (active) setLlmStatus(status);
      })
      .catch(() => {
        if (active) setLlmStatus(null);
      });
    return () => {
      active = false;
    };
  }, [workspaceId]);

  // Show a toast when extraction fails, or an auth-themed toast when the
  // session expired (HTTP 401) — the latter is not an extraction failure.
  // `extractTasks` never rejects, so this effect is the single authority for
  // the failure message; `handleExtract` must not report one itself.
  useEffect(() => {
    if (extraction) {
      const settled = extraction.status === 'failed' || extraction.status === 'unauthorized';
      if (settled && prevExtractionStatus === 'pending') {
        if (extraction.status === 'unauthorized') {
          toast.error(t.stories.extractionUnauthorized);
        } else if (extraction.errorCode === 'config') {
          // The API refused because the configuration cannot extract. Not a failure of
          // the extraction, and not something to retry: it is a prerequisite.
          toast.error(t.stories.extractionNeedsConfig);
        } else if (extraction.errorCode === 'timeout') {
          toast.error(t.stories.extractionTimeout);
        } else {
          toast.error(extraction.error?.friendlyMessage ?? t.stories.extractionFailed);
        }
      }
      setPrevExtractionStatus(extraction.status);
    }
  }, [extraction?.status, extraction?.error, extraction?.errorCode, prevExtractionStatus, t]);

  // Resolve parent project for contextual back link
  useEffect(() => {
    if (!story?.projectId || !workspaceId) {
      setParentProject(null);
      return;
    }

    const projectStore = useProjectStore.getState();
    const cached = projectStore.getById(story.projectId);
    if (cached) {
      setParentProject({ id: cached.id, name: cached.name });
      return;
    }

    setResolvingProject(true);
    getProject(workspaceId, story.projectId)
      .then((project) => setParentProject({ id: project.id, name: project.name }))
      .catch(() => setParentProject(null))
      .finally(() => setResolvingProject(false));
  }, [story?.projectId, workspaceId]);

  const handleUpdate = async (data: {
    actor: string;
    feature: string;
    benefit: string;
    rawText: string;
  }) => {
    try {
      await updateStory(storyId, data);
      setEditing(false);
      toast.success(t.stories.updated_toast);
    } catch (err) {
      toast.error(t.stories.update_error);
      throw err;
    }
  };

  const handleDelete = async () => {
    setDeleteSaving(true);
    try {
      await deleteStory(storyId);
      setDeleting(false);
      toast.success(t.stories.deleted_toast);
      window.history.back();
    } catch (err) {
      toast.error(t.stories.delete_error);
      throw err;
    } finally {
      setDeleteSaving(false);
    }
  };

  const handleExtract = async () => {
    if (!workspaceId) {
      // Same localized prompt the click handler gives: the handler is also the
      // confirmation's accept path, and neither may issue a request blind.
      toast.error(t.stories.select_workspace_required);
      return;
    }
    // `extractTasks` swallows its own errors: it records the failure into
    // `extractions[storyId]`, so awaiting it here can never reject and the
    // toast effect above owns the failure message.
    await extractTasks(storyId, workspaceId);
  };

  // Click on "Extract": with a workspace, open the confirmation that names the
  // version facts; without one, the localized prompt and no request at all.
  const handleExtractClick = () => {
    if (!workspaceId) {
      toast.error(t.stories.select_workspace_required);
      return;
    }
    setExtractConfirming(true);
  };

  const handleExtractConfirm = () => {
    setExtractConfirming(false);
    void handleExtract();
  };

  // ── Extract button rendering ──

  const getExtractButtonProps = () => {
    if (!extraction || extraction.status === 'idle') {
      return {
        enabled: true,
        icon: Sparkles,
        label: t.stories.detail_extract,
        variant: 'default' as const,
      };
    }
    switch (extraction.status) {
      case 'pending':
        return {
          enabled: false,
          icon: Loader2,
          label: t.stories.extraction_pending,
          variant: 'secondary' as const,
        };
      case 'completed':
        return {
          enabled: false,
          icon: CheckCircle2,
          label: t.stories.extraction_complete,
          variant: 'outline' as const,
        };
      case 'failed':
        return {
          enabled: true,
          icon: AlertCircle,
          label: t.stories.extraction_retry,
          variant: 'destructive' as const,
        };
      default:
        return {
          enabled: true,
          icon: Sparkles,
          label: t.stories.detail_extract,
          variant: 'default' as const,
        };
    }
  };

  const extractButton = getExtractButtonProps();

  /* ── Configuration gate ── */

  // A disabled control that explains itself: the configuration is a prerequisite, so
  // the refusal has to be visible before the click rather than only after it.
  const configIncomplete = llmStatus !== null && !llmStatus.configured;
  const extractDisabled = !extractButton.enabled || configIncomplete;
  const settingsHref = workspaceId
    ? localizedPath(`/workspaces/${workspaceId}/settings`, locale)
    : null;

  // The status route answers with field codes (`model`, `api_key`, `base_url`) and the
  // copy lives here, which is why the two are mapped rather than concatenated.
  const missingConfigLabels: Record<string, string> = {
    model: t.settings?.llm_ollama_model ?? 'Model',
    api_key: t.settings?.llm_openai_api_key ?? 'API Key',
    base_url: t.settings?.llm_base_url ?? 'Base URL',
  };
  const missingConfigNames = (llmStatus?.missing ?? [])
    .map((field) => missingConfigLabels[field] ?? field)
    .join(', ');

  /* ── Version-aware state ── */

  // The client mirror of the owner-or-admin gate. It only hides or disables
  // controls as a courtesy; the server's 403 and its localized copy remain the
  // authority if a refusal ever reaches the client.
  const canManage = canManageVersions(currentWorkspace, currentUserId);
  const selectedVersion = versions?.find((v) => v.id === selectedVersionId) ?? null;
  const currentVersion = versions?.find((v) => v.isCurrent) ?? null;
  const nextVersionNumber =
    (versions?.reduce((max, v) => Math.max(max, v.versionNumber ?? 0), 0) ?? 0) + 1;
  // The displayed tasks are the current version's (the backend filters every
  // read to it), so `frozen` follows the displayed version's currency.
  const displayedVersionFrozen = selectedVersion ? !selectedVersion.isCurrent : false;
  // No workspace is the one state where the extract control stays reachable on
  // purpose: its click path owns the localized "select a workspace" prompt.
  const extractGateLocked = !!workspaceId && !canManage;
  const extractButtonDisabled = extractDisabled || extractGateLocked;

  // The in-progress state, shared by the two ways the page knows a run is going:
  // the store's extraction entry, and the displayed version's own `pending`
  // status (the version the user just started is selected as soon as its row
  // exists). A pending version has no output yet, but it is not a failed one —
  // the no-output card belongs to a run that ended.
  const pendingPanel = (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-12">
      <Loader2 className="mb-3 h-8 w-8 text-muted-foreground animate-spin" />
      <p className="text-sm text-muted-foreground">{t.stories.extraction_tasks_in_progress}</p>
      <p className="text-xs text-muted-foreground mt-1 opacity-60">
        {t.stories.extraction_takes_up_to_minute}
      </p>
    </div>
  );

  // ── Render ──

  if (initialLoad || storyLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-border border-t-primary-500" />
      </div>
    );
  }

  if (!story) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-destructive">{t.stories.detail_not_found}</p>
        <Button variant="outline" className="mt-4" onClick={() => window.history.back()}>
          {t.stories.detail_back_to_stories}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Contextual back link */}
      {parentProject ? (
        <a
          href={`/${locale}/projects/${parentProject.id}`}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          {t.stories.detail_back_to_project} &laquo;{parentProject.name}&raquo;
        </a>
      ) : (
        <a
          href={`/${locale}/stories`}
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          {resolvingProject ? (
            <span className="inline-flex items-center gap-1">
              <Loader2 className="h-3 w-3 animate-spin" />
              {t.stories.detail_back_to_stories}
            </span>
          ) : (
            t.stories.detail_back_to_stories
          )}
        </a>
      )}

      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <Badge variant={STATUS_VARIANTS[story.status] ?? 'outline'}>
            {t.stories[`status_${story.status ?? 'pending_extraction'}` as keyof typeof t.stories]}
          </Badge>
          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground/60 font-mono">
            <Fingerprint className="h-3 w-3" />
            {shortUUID(story.id)}
          </span>
          <span className="text-xs text-muted-foreground">
            {t.stories.detail_created}{' '}
            {new Date(story.createdAt).toLocaleDateString(locale === 'es' ? 'es-MX' : 'en-US', {
              year: 'numeric',
              month: 'long',
              day: 'numeric',
            })}
          </span>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
            <Pencil className="mr-2 h-4 w-4" />
            {t.common.edit}
          </Button>
          {canManage && (
            <Button
              variant="outline"
              size="sm"
              className="text-destructive"
              onClick={() => setDeleting(true)}
            >
              <Trash2 className="mr-2 h-4 w-4" />
              {t.common.delete}
            </Button>
          )}
        </div>
      </div>

      {/* Full story text */}
      <div className="rounded-xl border border-border bg-(--color-surface) p-6">
        <div className="flex items-center gap-2 mb-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          <FileText className="h-3.5 w-3.5" />
          {t.stories.raw_text_label}
        </div>
        <p className="text-base text-foreground leading-relaxed">
          {story.rawText ||
            `${t.stories?.keyword_as_a ?? 'As a(n)'} ${story.actor}, ${t.stories?.keyword_i_want ?? 'I want'} ${story.feature}, ${t.stories?.keyword_so_that ?? 'so that'} ${story.benefit}`}
        </p>
      </div>

      {/* Parts */}
      <div className="rounded-xl border border-border bg-(--color-surface) p-6">
        <div className="flex items-center gap-2 mb-4 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          <ListTree className="h-3.5 w-3.5" />
          {t.stories.detail_parts}
        </div>
        <div className="grid gap-4 sm:grid-cols-3">
          <div>
            <p className="text-xs text-muted-foreground mb-1">{t.stories.actor_label}</p>
            <p className="text-sm font-medium text-foreground">{story.actor}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">{t.stories.feature_label}</p>
            <p className="text-sm font-medium text-foreground">{story.feature}</p>
          </div>
          <div>
            <p className="text-xs text-muted-foreground mb-1">{t.stories.benefit_label}</p>
            <p className="text-sm font-medium text-foreground">{story.benefit}</p>
          </div>
        </div>
      </div>

      {/* Version selector — the story's history; hidden when the read failed. */}
      {versions !== null && versions.length > 0 && (
        <VersionSelector
          versions={versions}
          selectedId={selectedVersionId}
          onSelect={setSelectedVersionId}
          locale={locale}
        />
      )}

      {/* Tasks section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">{t.stories.detail_tasks_title}</h2>
          <Button
            size="sm"
            variant={extractButton.variant}
            onClick={extractButtonDisabled ? undefined : handleExtractClick}
            disabled={extractButtonDisabled}
          >
            <extractButton.icon
              className={'mr-2 h-4 w-4' + (extraction?.status === 'pending' ? ' animate-spin' : '')}
            />
            {extractButton.label}
          </Button>
        </div>

        {configIncomplete && (
          <div
            role="alert"
            className="flex items-start gap-3 rounded-lg border border-(--color-destructive-border) bg-(--color-destructive-bg) p-3"
          >
            <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-(--color-destructive-text)">
                {t.stories.extractionBlockedTitle}
              </p>
              <p className="text-sm text-(--color-destructive-text)">
                {t.stories.extractionBlockedDesc}
              </p>
              {missingConfigNames !== '' && (
                <p className="text-sm text-(--color-destructive-text)">
                  {t.stories.extractionBlockedMissing.replace('{fields}', missingConfigNames)}
                </p>
              )}
              {/* Who can act on it differs, so say which: an admin is sent to the fix,
                  a member is told whose job it is instead of being pointed at a page
                  that refuses them. */}
              {workspaceRole === 'admin' && settingsHref ? (
                <a
                  href={settingsHref}
                  className="inline-block text-sm text-destructive underline hover:text-(--color-destructive-text)"
                >
                  {t.stories.extractionBlockedAction}
                </a>
              ) : (
                <p className="text-sm text-(--color-destructive-text)">
                  {t.stories.extractionBlockedAskAdmin}
                </p>
              )}
            </div>
          </div>
        )}

        {selectedVersion?.status === 'pending' ||
        (!selectedVersion && extraction?.status === 'pending') ? (
          pendingPanel
        ) : selectedVersion && !selectedVersion.hasOutput ? (
          /* A failed version is shown honestly: what it is, which model ran it
             and why it produced nothing — never an empty board that reads as
             "this story has no tasks". */
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-12">
            <AlertCircle className="mb-3 h-8 w-8 text-muted-foreground" />
            <p className="text-sm font-medium text-foreground">
              {t.versionSelector.no_output_title}
            </p>
            <p className="mt-1 text-sm text-muted-foreground">
              {t.versionSelector.no_output_desc
                .replace('{model}', selectedVersion.modelUsed)
                .replace('{error}', selectedVersion.errorInfo ?? '—')}
            </p>
          </div>
        ) : tasksLoading ? (
          <div className="flex items-center justify-center py-12">
            <div className="h-6 w-6 animate-spin rounded-full border-4 border-border border-t-primary-500" />
          </div>
        ) : storyTasks.length > 0 ? (
          <div className="space-y-2">
            {storyTasks.map((task) => (
              <div
                key={task.id}
                className="rounded-lg border border-border bg-(--color-surface) p-4 space-y-2"
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-sm font-medium text-foreground">{task.title}</p>
                  <div className="flex items-center gap-2 shrink-0">
                    {task.labels.length > 0 && (
                      <div className="flex gap-1">
                        {task.labels.map((label) => (
                          <Badge key={label} variant="outline" className="text-[10px]">
                            {label}
                          </Badge>
                        ))}
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setMarkIntent(false);
                        setEditingTaskId(task.id);
                      }}
                      className="text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                      disabled={extraction?.status === 'pending'}
                      title={t.taskEditor.title}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
                    {canManage && !displayedVersionFrozen && (
                      <button
                        type="button"
                        onClick={() => {
                          setMarkIntent(true);
                          setEditingTaskId(task.id);
                        }}
                        className={
                          markedTaskIds.has(task.id)
                            ? 'text-destructive transition-colors'
                            : 'text-muted-foreground/50 hover:text-muted-foreground transition-colors'
                        }
                        disabled={extraction?.status === 'pending'}
                        title={t.stories.mark_invalid}
                        aria-label={t.stories.mark_invalid}
                        aria-pressed={markedTaskIds.has(task.id)}
                      >
                        <Flag
                          className="h-3.5 w-3.5"
                          fill={markedTaskIds.has(task.id) ? 'currentColor' : 'none'}
                        />
                      </button>
                    )}
                  </div>
                </div>
                {task.description && (
                  <p className="text-sm text-muted-foreground">{task.description}</p>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-12">
            {extraction?.status === 'failed' || extraction?.status === 'unauthorized' ? (
              <>
                <ErrorDisplay
                  friendlyMessage={
                    extraction?.status === 'unauthorized'
                      ? t.stories.extractionUnauthorized
                      : extraction?.errorCode === 'config'
                        ? t.stories.extractionNeedsConfig
                        : (extraction?.error?.friendlyMessage ?? t.stories.extractionFailed)
                  }
                  rawDetail={extraction?.error?.rawDetail}
                  status={extraction?.error?.status}
                  errorCode={extraction?.error?.errorCode}
                  retryLabel={t.stories.extraction_retry}
                  onRetry={handleExtract}
                  locale={locale}
                />
              </>
            ) : (
              <>
                <Sparkles className="mb-3 h-8 w-8 text-muted-foreground" />
                <p className="text-sm text-muted-foreground">{t.stories.detail_tasks_empty}</p>
              </>
            )}
          </div>
        )}
      </div>

      {/* Edit dialog */}
      <StoryForm
        key="story-detail-edit"
        open={editing}
        onOpenChange={setEditing}
        onSubmit={handleUpdate}
        locale={locale}
        initialData={{
          actor: story.actor,
          feature: story.feature,
          benefit: story.benefit,
          rawText: story.rawText,
        }}
        title={t.common.edit}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.stories.delete_confirm_title}</AlertDialogTitle>
            <AlertDialogDescription>{t.stories.delete_confirm_description}</AlertDialogDescription>
            {/* The count is a fact about the destructive action, read from the
                selector data this page already holds. A failed read drops the
                count and says so instead of blocking the confirmation: the
                count is informational, the gate and the record are the
                interlocks. */}
            <AlertDialogDescription>
              {versions === null
                ? t.stories.delete_confirm_versions_unknown
                : t.stories.delete_confirm_versions.replace('{count}', String(versions.length))}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t.common.cancel}</AlertDialogCancel>
            <AlertDialogAction
              className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
              onClick={handleDelete}
              disabled={deleteSaving}
            >
              {deleteSaving && <LoaderCircle className="animate-spin" />}
              <span className={deleteSaving ? 'opacity-50' : ''}>{t.common.delete}</span>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Extract confirmation — names the version being frozen and the new one. */}
      <AlertDialog open={extractConfirming} onOpenChange={setExtractConfirming}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.stories.extract_confirm_title}</AlertDialogTitle>
            <AlertDialogDescription>
              {currentVersion?.versionNumber != null
                ? t.stories.extract_confirm_body
                    .replace('{newVersion}', String(nextVersionNumber))
                    .replace('{currentVersion}', String(currentVersion.versionNumber))
                : t.stories.extract_confirm_body_first.replace(
                    '{newVersion}',
                    String(nextVersionNumber),
                  )}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t.common.cancel}</AlertDialogCancel>
            <AlertDialogAction onClick={handleExtractConfirm}>
              {t.stories.detail_extract}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Task Editor dialog — rendered only once the task's mark read has
          settled, so the editor's checkbox/reason initializers see the final
          mark state. */}
      {editingTaskId &&
        activeMark !== 'loading' &&
        (() => {
          const editingTask = storyTasks.find((t) => t.id === editingTaskId);
          if (!editingTask) return null;
          return (
            <TaskEditor
              key={editingTask.id}
              task={editingTask}
              open={!!editingTaskId}
              // The displayed tasks are the selected version's, so the editor's
              // frozen state follows the displayed version's currency.
              frozen={displayedVersionFrozen}
              activeMark={activeMark}
              markDefaultChecked={markIntent && !activeMark}
              reasonAutofocus={markIntent}
              onInvalidationChange={handleInvalidationChange}
              onOpenChange={(open) => {
                if (!open) setEditingTaskId(null);
              }}
              locale={locale}
            />
          );
        })()}
    </div>
  );
}
