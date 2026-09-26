import { useEffect, useMemo, useState } from 'react';
import {
  FileText,
  Fingerprint,
  FileUp,
  Info,
  Plus,
  Pencil,
  Trash2,
  LoaderCircle,
  ArrowUp,
  ArrowDown,
} from 'lucide-react';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { useStoryStore } from '@/stores/storyStore';
import { useProjectStore } from '@/stores/projectStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import type { UserStory } from '@/types/story';
import { shortUUID } from '@/lib/utils';
import { StoryForm } from '@/components/react/StoryForm';
import { ImportStoriesDialog } from '@/components/react/ImportStoriesDialog';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import { useTranslations, type Locale } from '@/i18n/utils';
import { ApiRequestError } from '@/lib/api';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  pending_extraction: 'outline',
  extracting: 'secondary',
  extracted: 'default',
  failed_extraction: 'destructive',
};

interface StoriesListProps {
  locale?: Locale;
  projectId?: string;
}

export function StoriesList({ locale = 'en', projectId: initialProjectId }: StoriesListProps) {
  const t = useTranslations(locale);
  const { projects, fetchProjects } = useProjectStore();
  const { stories, loading, fetchStories, createStory, updateStory, deleteStory } = useStoryStore();
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspace?.id);
  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>(initialProjectId);
  const [formOpen, setFormOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);
  const [editingStory, setEditingStory] = useState<UserStory | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [deleteSaving, setDeleteSaving] = useState(false);
  const [sortBy, setSortBy] = useState<string>('createdAt_desc');

  // Sort options with labels and icons
  const sortOptions = useMemo(
    () => [
      {
        value: 'createdAt_desc',
        label: t.stories.sort_created_desc,
        icon: ArrowDown,
      },
      {
        value: 'createdAt_asc',
        label: t.stories.sort_created_asc,
        icon: ArrowUp,
      },
      {
        value: 'status_desc',
        label: t.stories.sort_status_desc,
        icon: ArrowDown,
      },
      { value: 'status_asc', label: t.stories.sort_status_asc, icon: ArrowUp },
      {
        value: 'actor_desc',
        label: t.stories.sort_actor_desc,
        icon: ArrowDown,
      },
      { value: 'actor_asc', label: t.stories.sort_actor_asc, icon: ArrowUp },
    ],
    [t],
  );

  // Find current sort option for display
  const currentSortOption = useMemo(
    () => sortOptions.find((opt) => opt.value === sortBy) ?? sortOptions[0],
    [sortOptions, sortBy],
  );

  // Build items array for the Base Select (supports null as a native value)
  const projectItems: { label: string; value: string | null }[] = useMemo(
    () => [
      { label: t.stories?.allProjects ?? 'All projects', value: null },
      ...projects.map((p) => ({ label: p.name, value: p.id })),
    ],
    [projects],
  );

  // Fetch projects if they haven't been loaded yet (needed for the filter dropdown)
  useEffect(() => {
    if (projects.length === 0) {
      fetchProjects();
    }
  }, [fetchProjects, projects.length]);

  // Get the project name for the dialog title
  const selectedProjectName = useMemo(
    () => projects.find((p) => p.id === selectedProjectId)?.name,
    [projects, selectedProjectId],
  );

  const createDialogTitle = selectedProjectName
    ? t.stories.create_title_with_project.replace('{projectName}', selectedProjectName)
    : t.stories.create_title;

  // Sync selectedProjectId when the prop changes (e.g. Astro View Transitions), and
  // reset it when the workspace changes: a project chosen in the previous workspace
  // must not keep scoping the new workspace's query.
  useEffect(() => {
    setSelectedProjectId(initialProjectId);
  }, [initialProjectId, workspaceId]);

  useEffect(() => {
    fetchStories(selectedProjectId, workspaceId);
  }, [fetchStories, selectedProjectId, workspaceId]);

  // Client-side filter: guard against View Transition stale store data.
  // Stories from a previous page survive in the Zustand singleton until
  // the async fetch completes. Only show stories that belong to the
  // current project when a filter is active.
  const visibleStories = useMemo(() => {
    const filtered = selectedProjectId
      ? stories.filter((s) => s.projectId === selectedProjectId)
      : stories;
    const sorted = [...filtered];
    switch (sortBy) {
      case 'createdAt_asc':
        return sorted.sort(
          (a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
        );
      case 'createdAt_desc':
        return sorted.sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        );
      case 'status_asc':
        return sorted.sort((a, b) => {
          const statusOrder: Record<string, number> = {
            pending_extraction: 0,
            extracting: 1,
            extracted: 2,
            failed_extraction: 3,
          };
          return (statusOrder[a.status] ?? 99) - (statusOrder[b.status] ?? 99);
        });
      case 'status_desc':
        return sorted.sort((a, b) => {
          const statusOrder: Record<string, number> = {
            pending_extraction: 0,
            extracting: 1,
            extracted: 2,
            failed_extraction: 3,
          };
          return (statusOrder[b.status] ?? 99) - (statusOrder[a.status] ?? 99);
        });
      case 'actor_asc':
        return sorted.sort((a, b) => a.actor.localeCompare(b.actor));
      case 'actor_desc':
        return sorted.sort((a, b) => b.actor.localeCompare(a.actor));
      default:
        return sorted.sort(
          (a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime(),
        );
    }
  }, [stories, selectedProjectId, sortBy]);

  const handleCreate = async (data: {
    actor: string;
    feature: string;
    benefit: string;
    rawText: string;
  }) => {
    if (!selectedProjectId) {
      toast.error(t.stories?.selectProjectFirst ?? 'Select a project first');
      return;
    }
    try {
      await createStory({ projectId: selectedProjectId, ...data });
      toast.success(t.stories.create_toast);
    } catch (err) {
      // Extract the detailed error message from the API error
      // Backend returns: "User story with the same actor, feature, and benefit already exists in this project. Existing story ID: {id}"
      const message = err instanceof Error ? err.message : t.stories.create_error;
      // Detect duplicate: check status code first (most reliable), then message content
      const isApiError = err instanceof ApiRequestError;
      const isDuplicate =
        (isApiError && err.status === 409) ||
        message.toLowerCase().includes('already exists') ||
        message.toLowerCase().includes('ya existe') ||
        message.toLowerCase().includes('duplicate') ||
        message.toLowerCase().includes('conflict');

      // Always show a toast for any error
      if (isDuplicate) {
        // Extract the story ID from the backend message
        const idMatch = message.match(/Existing story ID:\s*([a-f0-9-]+)/i);
        const existingId = idMatch ? idMatch[1] : '';
        // Use localized message and append the ID
        const localizedMsg = t.stories.create_duplicate_error;
        toast.error(existingId ? `${localizedMsg}. ID: ${existingId}` : localizedMsg);
      } else {
        toast.error(message || t.stories.create_error);
      }
      // Re-throw so StoryForm can show ErrorDisplay with full backend details
      throw err;
    }
  };

  const handleUpdate = async (data: {
    actor: string;
    feature: string;
    benefit: string;
    rawText: string;
  }) => {
    if (!editingStory) return;
    try {
      await updateStory(editingStory.id, data);
      setEditingStory(null);
      toast.success(t.stories.updated_toast);
    } catch (err) {
      toast.error(t.stories.update_error);
      // Re-throw so StoryForm can show ErrorDisplay with full backend details
      throw err;
    }
  };

  const handleDelete = async () => {
    if (!deletingId) return;
    setDeleteSaving(true);
    try {
      await deleteStory(deletingId);
      setDeletingId(null);
      toast.success(t.stories.deleted_toast);
    } catch (err) {
      toast.error(t.stories.delete_error);
      // Re-throw so any parent component can show ErrorDisplay with full backend details
      throw err;
    } finally {
      setDeleteSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Filters and actions */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {!initialProjectId && (
            <Select
              items={projectItems}
              value={selectedProjectId ?? null}
              onValueChange={(val) => setSelectedProjectId(val ?? undefined)}
            >
              <SelectTrigger className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectGroup>
                  {projectItems.map((item) => (
                    <SelectItem key={item.value ?? '_all'} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectGroup>
              </SelectContent>
            </Select>
          )}
          <Select
            items={sortOptions.map((opt) => ({
              value: opt.value,
              label: opt.label,
            }))}
            value={sortBy}
            onValueChange={(value) => {
              if (value !== null) setSortBy(value);
            }}
          >
            <SelectTrigger className="w-48 flex items-center gap-2">
              <currentSortOption.icon className="h-4 w-4 text-muted-foreground" />
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {sortOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    <option.icon className="h-4 w-4 mr-2 text-muted-foreground" />
                    {option.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
        </div>

        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={() => setImportOpen(true)}
            disabled={!selectedProjectId && !initialProjectId}
          >
            <FileUp className="h-4 w-4" />
            {t.stories.import_button}
          </Button>
          <Button
            onClick={() => setFormOpen(true)}
            disabled={!selectedProjectId && !initialProjectId}
          >
            <Plus className="h-4 w-4" />
            {t.stories.create_title}
          </Button>

          {!selectedProjectId && !initialProjectId && (
            <HoverCard>
              <HoverCardTrigger
                render={
                  <span className="inline-flex items-center justify-center rounded-full h-5 w-5 text-muted-foreground hover:text-foreground hover:bg-(--color-surface-tertiary) transition-colors cursor-help">
                    <Info className="h-4 w-4" />
                  </span>
                }
              />
              <HoverCardContent side="top" align="start" className="w-72">
                <p className="text-sm">{t.stories.create_disabled_hint}</p>
              </HoverCardContent>
            </HoverCard>
          )}
        </div>
      </div>

      {/* Stories list */}
      {loading && visibleStories.length === 0 ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-border border-t-primary-500" />
        </div>
      ) : visibleStories.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
          <FileText className="mb-4 h-12 w-12 text-muted-foreground" />
          <p className="text-lg font-medium text-foreground">{t.stories.empty_title}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t.stories.empty_description}</p>
          <div className="flex items-center gap-2 mt-4">
            <Button
              variant="outline"
              onClick={() => setFormOpen(true)}
              disabled={!selectedProjectId && !initialProjectId}
            >
              <Plus className="mr-2 h-4 w-4" />
              {t.stories.create_title}
            </Button>

            {!selectedProjectId && !initialProjectId && (
              <HoverCard>
                <HoverCardTrigger
                  render={
                    <span className="inline-flex items-center justify-center rounded-full h-5 w-5 text-muted-foreground hover:text-foreground hover:bg-(--color-surface-tertiary) transition-colors cursor-help">
                      <Info className="h-4 w-4" />
                    </span>
                  }
                />
                <HoverCardContent side="top" align="start" className="w-72">
                  <p className="text-sm">{t.stories.create_disabled_hint}</p>
                </HoverCardContent>
              </HoverCard>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {visibleStories.map((story) => (
            <div
              key={story.id}
              onClick={() => window.location.assign(`/${locale}/stories/${story.id}`)}
              className="flex items-start justify-between rounded-lg border border-border bg-(--color-surface) p-4 transition-colors hover:bg-(--color-surface-secondary) cursor-pointer"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant={STATUS_VARIANTS[story.status] ?? 'outline'}>
                    {
                      t.stories[
                        `status_${story.status ?? 'pending_extraction'}` as keyof typeof t.stories
                      ]
                    }
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {new Date(story.createdAt).toLocaleDateString(
                      locale === 'es' ? 'es-MX' : 'en-US',
                      {
                        year: 'numeric',
                        month: 'short',
                        day: 'numeric',
                      },
                    )}
                  </span>
                  <span className="inline-flex items-center gap-1 text-xs text-muted-foreground/60 font-mono">
                    <Fingerprint className="h-3 w-3" />
                    {shortUUID(story.id)}
                  </span>
                </div>
                <p className="text-sm font-medium text-foreground">
                  {t.stories?.keyword_as_a ?? 'As a(n)'}{' '}
                  <span className="text-primary">{story.actor}</span>,{' '}
                  {t.stories?.keyword_i_want ?? 'I want'}{' '}
                  <span className="text-primary">{story.feature}</span>,{' '}
                  {t.stories?.keyword_so_that ?? 'so that'}{' '}
                  <span className="text-primary">{story.benefit}</span>
                </p>
              </div>

              <div className="flex items-center gap-1 ml-4 shrink-0">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-(--color-surface-tertiary)"
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditingStory(story);
                  }}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  onClick={(e) => {
                    e.stopPropagation();
                    setDeletingId(story.id);
                  }}
                >
                  <Trash2 className="h-4 w-4" />
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create dialog */}
      <StoryForm
        open={formOpen}
        onOpenChange={setFormOpen}
        onSubmit={handleCreate}
        locale={locale}
        title={createDialogTitle}
      />

      {/* CSV import dialog */}
      <ImportStoriesDialog
        open={importOpen}
        onOpenChange={setImportOpen}
        locale={locale}
        projectId={selectedProjectId ?? initialProjectId ?? ''}
        workspaceId={workspaceId ?? ''}
      />

      {/* Edit dialog */}
      <StoryForm
        key={editingStory?.id ?? 'edit-none'}
        open={editingStory !== null}
        onOpenChange={(open) => {
          if (!open) setEditingStory(null);
        }}
        onSubmit={handleUpdate}
        locale={locale}
        initialData={{
          actor: editingStory?.actor,
          feature: editingStory?.feature,
          benefit: editingStory?.benefit,
          rawText: editingStory?.rawText,
        }}
        title={t.stories.edit_title}
      />

      {/* Delete confirmation */}
      <AlertDialog
        open={deletingId !== null}
        onOpenChange={(open) => {
          if (!open) setDeletingId(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.stories.delete_confirm_title}</AlertDialogTitle>
            <AlertDialogDescription>{t.stories.delete_confirm_description}</AlertDialogDescription>
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
    </div>
  );
}
