import { useEffect, useState } from 'react';
import { FolderKanban, Plus, MoreHorizontal, Pencil, Trash2, CalendarDays, FileText, LoaderCircle } from 'lucide-react';
import { IconDisplay } from '@/components/ui/icon-display';
import { useProjectStore } from '@/stores/projectStore';
import { ProjectForm } from '@/components/react/ProjectForm';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
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

interface ProjectsListProps {
  locale?: Locale;
  userId?: string;
}

export function ProjectsList({ locale = 'en', userId }: ProjectsListProps) {
  const t = useTranslations(locale);
  const { projects, loading, error, fetchProjects, createProject, updateProject, deleteProject } = useProjectStore();
  const [formOpen, setFormOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<{ id: string; name: string; description: string; icon?: string } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [isRetrying, setIsRetrying] = useState(false);
  const [deleteSaving, setDeleteSaving] = useState(false);

  useEffect(() => {
    fetchProjects().finally(() => setInitialLoading(false));
  }, [fetchProjects]);

  useEffect(() => {
    if (error) setLocalError(error);
  }, [error]);

  const handleCreate = async (data: { name: string; description: string; icon?: string }) => {
    if (!userId) {
      toast.error(t.stories?.signedInRequired ?? 'You must be signed in to create a project');
      return;
    }
    try {
      setLocalError(null);
      await createProject(data);
      toast.success(t.projects.create_toast);
    } catch {
      toast.error(t.projects.create_error);
    }
  };

  const handleUpdate = async (data: { name: string; description: string; icon?: string }) => {
    if (!editingProject) return;
    try {
      setLocalError(null);
      await updateProject(editingProject.id, data);
      setEditingProject(null);
      toast.success(t.projects.updated_toast);
    } catch {
      toast.error(t.projects.update_error);
    }
  };

  const handleDelete = async () => {
    if (!deletingId) return;
    setDeleteSaving(true);
    try {
      setLocalError(null);
      await deleteProject(deletingId);
      setDeletingId(null);
      toast.success(t.projects.deleted_toast);
    } catch {
      toast.error(t.projects.delete_error);
    } finally {
      setDeleteSaving(false);
    }
  };

  if (initialLoading || (loading && projects.length === 0)) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-border border-t-primary-500" />
      </div>
    );
  }

  if (localError && projects.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-destructive">{localError}</p>
        <Button
          variant="outline"
          className="mt-4"
          onClick={async () => {
            setIsRetrying(true);
            await fetchProjects();
            setIsRetrying(false);
          }}
          disabled={isRetrying}
        >
          {isRetrying && <LoaderCircle className="animate-spin" />}
          <span className={isRetrying ? "opacity-50" : ""}>
            {t.common?.retry ?? 'Retry'}
          </span>
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">
            {t.nav.projects}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t.dashboard.description ?? 'Manage your projects'}
          </p>
        </div>
        <Button onClick={() => setFormOpen(true)}>
          <Plus className="h-4 w-4" />
          {t.dashboard.new_project}
        </Button>
      </div>

      {projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
          <FolderKanban className="mb-4 h-12 w-12 text-muted-foreground" />
          <p className="text-lg font-medium text-foreground">
            {t.dashboard.empty_title}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {t.dashboard.empty_description}
          </p>
          <Button variant="outline" className="mt-4" onClick={() => setFormOpen(true)}>
            <Plus className="mr-2 h-4 w-4" />
            {t.dashboard.new_project}
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <div
              key={project.id}
              onClick={() => window.location.href = `/${locale}/projects/${project.id}`}
              className="cursor-pointer flex"
            >
              <Card className="group flex flex-col w-full">
                <CardHeader className="flex flex-row items-start justify-between space-y-0">
                  <div className="flex items-center gap-2">
                    <IconDisplay name={project.icon} className="size-4 shrink-0 text-muted-foreground" fallback={FolderKanban} />
                    <CardTitle className="text-base">{project.name}</CardTitle>
                  </div>
                  <div onClick={(e) => e.stopPropagation()}>
                    <DropdownMenu>
                      <DropdownMenuTrigger
                        render={
                          <Button variant="ghost" size="icon" className="h-8 w-8 opacity-0 group-hover:opacity-100 transition-opacity">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        }
                      />
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() =>
                            setEditingProject({
                              id: project.id,
                              name: project.name,
                              description: project.description,
                              icon: project.icon ?? undefined,
                            })
                          }
                        >
                          <Pencil className="mr-2 h-4 w-4" />
                          {t.common.edit}
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => setDeletingId(project.id)}
                        >
                          <Trash2 className="mr-2 h-4 w-4" />
                          {t.common.delete}
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </CardHeader>
                <CardContent className="flex flex-col gap-3 pt-0 flex-1">
                  {project.description ? (
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {project.description}
                    </p>
                  ) : (
                    <p className="text-sm text-muted-foreground/50 italic">
                      {t.projects.no_description}
                    </p>
                  )}

                  <div className="mt-auto flex items-center gap-4 text-xs text-muted-foreground">
                    <span className="inline-flex items-center gap-1">
                      <CalendarDays className="h-3.5 w-3.5" />
                      {new Date(project.createdAt).toLocaleDateString(
                        locale === 'es' ? 'es-MX' : 'en-US',
                        { year: 'numeric', month: 'short', day: 'numeric' }
                      )}
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <FileText className="h-3.5 w-3.5" />
                      {project.storyCount === 1
                        ? t.projects.story_count.replace('{count}', String(project.storyCount))
                        : t.projects.story_count_plural.replace('{count}', String(project.storyCount))}
                    </span>
                  </div>
                </CardContent>
              </Card>
            </div>
          ))}
        </div>
      )}

      {/* Create dialog */}
      <ProjectForm
        open={formOpen}
        onOpenChange={setFormOpen}
        onSubmit={handleCreate}
        locale={locale}
      />

      {/* Edit dialog */}
      <ProjectForm
        key={editingProject?.id ?? 'edit'}
        open={editingProject !== null}
        onOpenChange={(open) => { if (!open) setEditingProject(null); }}
        onSubmit={handleUpdate}
        locale={locale}
        initialData={editingProject ?? undefined}
        title={t.common.edit}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deletingId !== null} onOpenChange={(open) => { if (!open) setDeletingId(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t.projects.delete_confirm_title}</AlertDialogTitle>
            <AlertDialogDescription>
              {t.projects.delete_confirm_description}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t.common.cancel}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
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
    </div>
  );
}
