import { FolderKanban, Plus } from 'lucide-react';
import { useProjectStore } from '@/stores/projectStore';
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';

export function Dashboard() {
  const { projects, loading } = useProjectStore();

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-border border-t-primary-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold text-foreground">
          Dashboard
        </h1>
        <Button>
          <Plus className="h-4 w-4" />
          New Project
        </Button>
      </div>

      {/* Project grid */}
      {projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
          <FolderKanban className="mb-4 h-12 w-12 text-muted-foreground" />
          <p className="text-lg font-medium text-foreground">
            No projects yet
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            Create your first project to start extracting tasks from user
            stories.
          </p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Card key={project.id}>
              <CardHeader>
                <CardTitle>{project.name}</CardTitle>
              </CardHeader>
              {project.description && (
                <CardContent>
                  <p className="text-sm text-muted-foreground">
                    {project.description}
                  </p>
                </CardContent>
              )}
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
