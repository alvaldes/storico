import { useEffect, useState } from 'react';
import { FolderKanban, Plus, MoreHorizontal, Pencil, Trash2 } from 'lucide-react';
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

export function Dashboard({ locale = 'en', userId }: { locale?: Locale; userId?: string }) {
  const t = useTranslations(locale);
  const { projects, loading, error, fetchProjects, createProject, updateProject, deleteProject } = useProjectStore();
  const [formOpen, setFormOpen] = useState(false);
  const [editingProject, setEditingProject] = useState<{ id: string; name: string; description: string } | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  useEffect(() => {
    if (error) setLocalError(error);
  }, [error]);

  const handleCreate = async (data: { name: string; description: string }) => {
    if (!userId) {
      toast.error('You must be signed in to create a project');
      return;
    }
    try {
      setLocalError(null);
      await createProject({ ...data, ownerId: userId });
      toast.success(t.projects.create_toast);
    } catch {
      toast.error(t.projects.create_error);
    }
  };

  const handleUpdate = async (data: { name: string; description: string }) => {
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
    try {
      setLocalError(null);
      await deleteProject(deletingId);
      setDeletingId(null);
      toast.success(t.projects.deleted_toast);
    } catch {
      toast.error(t.projects.delete_error);
    }
  };

  if (loading && projects.length === 0) {
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
        <Button variant="outline" className="mt-4" onClick={fetchProjects}>
          {t.common.retry ?? 'Retry'}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold text-foreground">
            {t.nav.dashboard}
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
              className="cursor-pointer"
            >
              <Card className="group">
                <CardHeader className="flex flex-row items-start justify-between space-y-0">
                  <CardTitle className="text-base">{project.name}</CardTitle>
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
                {project.description && (
                  <CardContent>
                    <p className="text-sm text-muted-foreground line-clamp-2">
                      {project.description}
                    </p>
                  </CardContent>
                )}
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
            >
              {t.common.delete}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
