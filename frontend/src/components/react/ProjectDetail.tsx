import { useEffect, useState } from 'react';
import { ArrowLeft, Pencil, Trash2, LoaderCircle } from 'lucide-react';
import { useProjectStore } from '@/stores/projectStore';
import { StoriesList } from '@/components/react/StoriesList';
import { ProjectForm } from '@/components/react/ProjectForm';
import { Button } from '@/components/ui/button';
import { IconDisplay } from '@/components/ui/icon-display';
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

interface ProjectDetailProps {
  locale?: Locale;
  projectId: string;
  userId: string;
}

export function ProjectDetail({ locale = 'en', projectId, userId }: ProjectDetailProps) {
  const t = useTranslations(locale);
  const { projects, loading, fetchProjects, updateProject, deleteProject } = useProjectStore();
  const project = projects.find((p) => p.id === projectId);
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteSaving, setDeleteSaving] = useState(false);
  const [initialLoading, setInitialLoading] = useState(true);

  useEffect(() => {
    if (projects.length === 0) {
      fetchProjects().finally(() => setInitialLoading(false));
    } else {
      setInitialLoading(false);
    }
  }, [fetchProjects, projects.length]);

  const handleUpdate = async (data: { name: string; description: string; icon?: string }) => {
    await updateProject(projectId, data);
    setEditing(false);
    toast.success(t.projects.updated_toast);
  };

  const handleDelete = async () => {
    setDeleteSaving(true);
    try {
      await deleteProject(projectId);
      setDeleting(false);
      toast.success(t.projects.deleted_toast);
      window.history.back();
    } finally {
      setDeleteSaving(false);
    }
  };

  if (initialLoading || (loading && !project)) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-border border-t-primary-500" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="flex flex-col items-center justify-center py-20">
        <p className="text-destructive">{t.projects?.notFound ?? "Project not found"}</p>
        <Button variant="outline" className="mt-4" onClick={() => window.history.back()}>
          {t.nav.back_to_home}
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Back link */}
      <button
        onClick={() => window.history.back()}
        className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
      >
        <ArrowLeft className="h-4 w-4" />
        {t.nav.back}
      </button>

      {/* Project header */}
      <div className="flex items-start justify-between">
        <div className="flex items-start gap-3">
          <IconDisplay name={project.icon} className="mt-1 size-6 shrink-0 text-muted-foreground" />
          <div>
            <h1 className="text-2xl font-semibold text-foreground">{project.name}</h1>
            {project.description && (
              <p className="mt-1 text-sm text-muted-foreground">{project.description}</p>
            )}
            <p className="mt-1 text-xs text-muted-foreground">
              Created {new Date(project.createdAt).toLocaleDateString(locale === 'es' ? 'es-MX' : 'en-US', {
                year: 'numeric',
                month: 'long',
                day: 'numeric',
              })}
            </p>
          </div>
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

      {/* Stories section */}
      <div>
        <StoriesList locale={locale} projectId={projectId} />
      </div>

      {/* Edit dialog */}
      <ProjectForm
        key="project-detail-edit"
        open={editing}
        onOpenChange={setEditing}
        onSubmit={handleUpdate}
        locale={locale}
        initialData={{ name: project.name, description: project.description, icon: project.icon ?? undefined }}
        title={t.common.edit}
      />

      {/* Delete confirmation */}
      <AlertDialog open={deleting} onOpenChange={setDeleting}>
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
    </div>
  );
}
