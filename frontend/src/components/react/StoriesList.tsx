import { useEffect, useState } from 'react';
import {
  FileText,
  Plus,
  Pencil,
  Trash2,
} from 'lucide-react';
import { useStoryStore } from '@/stores/storyStore';
import { useProjectStore } from '@/stores/projectStore';
import type { UserStory } from '@/types/story';
import { StoryForm } from '@/components/react/StoryForm';
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { useTranslations, type Locale } from '@/i18n/utils';

const STATUS_VARIANTS: Record<string, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  pending: 'outline',
  processing: 'secondary',
  completed: 'default',
  error: 'destructive',
};

interface StoriesListProps {
  locale?: Locale;
  projectId?: string;
}

export function StoriesList({ locale = 'en', projectId: initialProjectId }: StoriesListProps) {
  const t = useTranslations(locale);
  const { projects } = useProjectStore();
  const { stories, loading, fetchStories, createStory, updateStory, deleteStory } = useStoryStore();
  const [selectedProjectId, setSelectedProjectId] = useState<string | undefined>(initialProjectId);
  const [formOpen, setFormOpen] = useState(false);
  const [editingStory, setEditingStory] = useState<UserStory | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  useEffect(() => {
    fetchStories(selectedProjectId);
  }, [fetchStories, selectedProjectId]);

  const handleCreate = async (data: { actor: string; feature: string; benefit: string; rawText: string }) => {
    if (!selectedProjectId) {
      toast.error('Select a project first');
      return;
    }
    try {
      await createStory({ projectId: selectedProjectId, ...data });
      toast.success(t.stories.create_toast);
    } catch {
      toast.error(t.stories.create_error);
    }
  };

  const handleUpdate = async (data: { actor: string; feature: string; benefit: string; rawText: string }) => {
    if (!editingStory) return;
    try {
      await updateStory(editingStory.id, data);
      setEditingStory(null);
      toast.success(t.stories.updated_toast);
    } catch {
      toast.error(t.stories.update_error);
    }
  };

  const handleDelete = async () => {
    if (!deletingId) return;
    try {
      await deleteStory(deletingId);
      setDeletingId(null);
      toast.success(t.stories.deleted_toast);
    } catch {
      toast.error(t.stories.delete_error);
    }
  };

  return (
    <div className="space-y-6">
      {/* Filters and actions */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          {!initialProjectId && (
            <Select
              value={selectedProjectId ?? '_all'}
              onValueChange={(val) => setSelectedProjectId(val === '_all' ? undefined : val)}
            >
              <SelectTrigger className="w-56">
                <SelectValue placeholder="All projects" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="_all">All projects</SelectItem>
                {projects.map((p) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>

        <Button onClick={() => setFormOpen(true)} disabled={!selectedProjectId && !initialProjectId}>
          <Plus className="h-4 w-4" />
          {t.stories.create_title}
        </Button>
      </div>

      {/* Stories list */}
      {loading && stories.length === 0 ? (
        <div className="flex items-center justify-center py-20">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-border border-t-primary-500" />
        </div>
      ) : stories.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
          <FileText className="mb-4 h-12 w-12 text-muted-foreground" />
          <p className="text-lg font-medium text-foreground">
            {t.stories.empty_title}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {t.stories.empty_description}
          </p>
          <Button variant="outline" className="mt-4" onClick={() => setFormOpen(true)} disabled={!selectedProjectId && !initialProjectId}>
            <Plus className="mr-2 h-4 w-4" />
            {t.stories.create_title}
          </Button>
        </div>
      ) : (
        <div className="space-y-3">
          {stories.map((story) => (
            <div
              key={story.id}
              onClick={() => window.location.href = `/${locale}/stories/${story.id}`}
              className="flex items-start justify-between rounded-lg border border-border bg-(--color-surface) p-4 transition-colors hover:bg-(--color-surface-secondary) cursor-pointer"
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-1">
                  <Badge variant={STATUS_VARIANTS[story.status] ?? 'outline'}>
                    {t.stories[`status_${story.status ?? 'pending'}` as keyof typeof t.stories]}
                  </Badge>
                  <span className="text-xs text-muted-foreground">
                    {new Date(story.createdAt).toLocaleDateString(locale === 'es' ? 'es-MX' : 'en-US', {
                      year: 'numeric',
                      month: 'short',
                      day: 'numeric',
                    })}
                  </span>
                </div>
                <p className="text-sm font-medium text-foreground">
                  As a(n) <span className="text-primary">{story.actor}</span>, I want{' '}
                  <span className="text-primary">{story.feature}</span>, so that{' '}
                  <span className="text-primary">{story.benefit}</span>
                </p>
              </div>

              <div className="flex items-center gap-1 ml-4 shrink-0">
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-foreground hover:bg-(--color-surface-tertiary)"
                  onClick={(e) => { e.stopPropagation(); setEditingStory(story); }}
                >
                  <Pencil className="h-4 w-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon"
                  className="h-8 w-8 text-muted-foreground hover:text-destructive"
                  onClick={(e) => { e.stopPropagation(); setDeletingId(story.id); }}
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
      />

      {/* Edit dialog */}
      <StoryForm
        open={editingStory !== null}
        onOpenChange={(open) => { if (!open) setEditingStory(null); }}
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
      <AlertDialog open={deletingId !== null} onOpenChange={(open) => { if (!open) setDeletingId(null); }}>
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
            >
              {t.common.delete}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
