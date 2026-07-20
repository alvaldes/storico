import { useEffect, useState } from 'react';
import { ArrowLeft, Pencil, Trash2, Sparkles, Loader2, LoaderCircle, FileText, ListTree, Fingerprint, CheckCircle2, AlertCircle } from 'lucide-react';
import { shortUUID } from '@/lib/utils';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { getProject } from '@/lib/projects-api';
import { StoryForm } from '@/components/react/StoryForm';
import { TaskEditor } from '@/components/react/TaskEditor';
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
import { useTranslations, type Locale } from '@/i18n/utils';

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  pending: 'outline',
  processing: 'secondary',
  completed: 'default',
  error: 'destructive',
};

interface StoryDetailProps {
  locale?: Locale;
  storyId: string;
}

export function StoryDetail({ locale = 'en', storyId }: StoryDetailProps) {
  const t = useTranslations(locale);
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspace?.id);
  const { stories, loading: storyLoading, fetchStory, updateStory, deleteStory } = useStoryStore();
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
  const [parentProject, setParentProject] = useState<{ id: string; name: string } | null>(null);
  const [resolvingProject, setResolvingProject] = useState(false);

  const story = stories.find((s) => s.id === storyId);
  const storyTasks = tasks[storyId] ?? [];
  const extraction = extractions[storyId];

  useEffect(() => {
    fetchStory(storyId).then(() => setInitialLoad(false));
  }, [fetchStory, storyId]);

  useEffect(() => {
    if (storyId) {
      fetchTasks(storyId);
    }
  }, [fetchTasks, storyId]);

  // Reset extraction state on unmount
  useEffect(() => {
    return () => {
      resetExtraction(storyId);
    };
  }, [storyId, resetExtraction]);

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

  const handleUpdate = async (data: { actor: string; feature: string; benefit: string; rawText: string }) => {
    try {
      await updateStory(storyId, data);
      setEditing(false);
      toast.success(t.stories.updated_toast);
    } catch {
      toast.error(t.stories.update_error);
    }
  };

  const handleDelete = async () => {
    setDeleteSaving(true);
    try {
      await deleteStory(storyId);
      setDeleting(false);
      toast.success(t.stories.deleted_toast);
      window.history.back();
    } catch {
      toast.error(t.stories.delete_error);
    } finally {
      setDeleteSaving(false);
    }
  };

  const handleExtract = async () => {
    if (!workspaceId) {
      toast.error(t.stories?.extractionFailed ?? 'Extraction failed');
      return;
    }
    try {
      await extractTasks(storyId, workspaceId);
    } catch (err) {
      if (err instanceof Error && 'status' in err) {
        const apiErr = err as { status: number; message: string };
        if (apiErr.status === 401) {
          toast.error(t.stories?.extractionUnauthorized ?? 'Extraction failed — session expired');
        } else if (apiErr.status === 400) {
          toast.error(apiErr.message);
        } else if (apiErr.status === 504) {
          toast.error(t.stories?.extractionTimeout ?? 'Extraction timed out');
        } else {
          toast.error(apiErr.message || (t.stories?.extractionFailed ?? 'Extraction failed'));
        }
      } else if (err instanceof Error) {
        toast.error(err.message);
      } else {
        toast.error(t.stories?.extractionFailed ?? 'Extraction failed');
      }
      // Reset extraction state on failure so the user can retry
      resetExtraction(storyId);
    }
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
            {t.stories[`status_${story.status ?? 'pending'}` as keyof typeof t.stories]}
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
          <Button variant="outline" size="sm" className="text-destructive" onClick={() => setDeleting(true)}>
            <Trash2 className="mr-2 h-4 w-4" />
            {t.common.delete}
          </Button>
        </div>
      </div>

      {/* Full story text */}
      <div className="rounded-xl border border-border bg-(--color-surface) p-6">
        <div className="flex items-center gap-2 mb-3 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          <FileText className="h-3.5 w-3.5" />
          {t.stories.raw_text_label}
        </div>
        <p className="text-base text-foreground leading-relaxed">
          {story.rawText || `${t.stories?.keyword_as_a ?? 'As a(n)'} ${story.actor}, ${t.stories?.keyword_i_want ?? 'I want'} ${story.feature}, ${t.stories?.keyword_so_that ?? 'so that'} ${story.benefit}`}
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

      {/* Tasks section */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-foreground">{t.stories.detail_tasks_title}</h2>
          <Button
            size="sm"
            variant={extractButton.variant}
            onClick={extractButton.enabled ? handleExtract : undefined}
            disabled={!extractButton.enabled}
          >
            <extractButton.icon className={'mr-2 h-4 w-4' + (extraction?.status === 'pending' ? ' animate-spin' : '')} />
            {extractButton.label}
          </Button>
        </div>

        {tasksLoading ? (
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
                      onClick={() => setEditingTaskId(task.id)}
                      className="text-muted-foreground/50 hover:text-muted-foreground transition-colors"
                      disabled={extraction?.status === 'pending'}
                      title="Edit task"
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </button>
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
            {extraction?.status === 'pending' ? (
              <>
                <Loader2 className="mb-3 h-8 w-8 text-muted-foreground animate-spin" />
                <p className="text-sm text-muted-foreground">Extracting tasks...</p>
                <p className="text-xs text-muted-foreground mt-1 opacity-60">
                  This can take up to a minute
                </p>
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
        initialData={{ actor: story.actor, feature: story.feature, benefit: story.benefit, rawText: story.rawText }}
        title={t.common.edit}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleting} onOpenChange={setDeleting}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.stories.delete_confirm_title}</AlertDialogTitle>
            <AlertDialogDescription>
              {t.stories.delete_confirm_description}
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
              <span className={deleteSaving ? "opacity-50" : ""}>
                {t.common.delete}
              </span>
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Task Editor dialog */}
      {editingTaskId && (() => {
        const editingTask = storyTasks.find((t) => t.id === editingTaskId);
        if (!editingTask) return null;
        return (
          <TaskEditor
            key={editingTask.id}
            task={editingTask}
            open={!!editingTaskId}
            onOpenChange={(open) => { if (!open) setEditingTaskId(null); }}
            locale={locale}
          />
        );
      })()}
    </div>
  );
}
