import { FolderKanban, Plus } from 'lucide-react';
import { useProjectStore } from '@/stores/projectStore';

export function Dashboard() {
  const { projects, loading } = useProjectStore();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-(--color-border) border-t-(--color-primary-500)" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-(--color-text)">
          Dashboard
        </h1>
        <button className="inline-flex items-center gap-2 rounded-lg bg-(--color-primary-500) px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-(--color-primary-600)">
          <Plus className="h-4 w-4" />
          New Project
        </button>
      </div>

      {/* Project grid */}
      {projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-(--color-border) py-20">
          <FolderKanban className="mb-4 h-12 w-12 text-(--color-text-secondary)" />
          <p className="text-lg font-medium text-(--color-text)">
            No projects yet
          </p>
          <p className="mt-1 text-sm text-(--color-text-secondary)">
            Create your first project to start extracting tasks from user
            stories.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <div
              key={project.id}
              className="rounded-xl border border-(--color-border) bg-(--color-surface) p-4 transition-shadow hover:shadow-md"
            >
              <h3 className="font-medium text-(--color-text)">{project.name}</h3>
              {project.description && (
                <p className="mt-1 text-sm text-(--color-text-secondary)">
                  {project.description}
                </p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
