import { useEffect, useState } from 'react';
import { FolderKanban, FileText, Sparkles, ChevronRight } from 'lucide-react';
import { useProjectStore } from '@/stores/projectStore';
import { useStoryStore } from '@/stores/storyStore';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { useTranslations, type Locale } from '@/i18n/utils';

export function Dashboard({ locale = 'en' }: { locale?: Locale }) {
  const t = useTranslations(locale);
  const { projects, fetchProjects } = useProjectStore();
  const { stories, fetchStories } = useStoryStore();
  const [initialLoading, setInitialLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchProjects(),
      fetchStories(),
    ]).finally(() => setInitialLoading(false));
  }, [fetchProjects, fetchStories]);

  const totalProjects = projects.length;
  const totalStories = stories.length;
  const recentStories = [...stories]
    .sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())
    .slice(0, 5);

  if (initialLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-border border-t-primary-500" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold text-foreground">
          {t.nav.dashboard}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Welcome back — here's an overview of your workspace.
        </p>
      </div>

      {/* Summary cards */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center gap-3 space-y-0 pb-2">
            <FolderKanban className="h-5 w-5 text-primary" />
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t.nav.projects}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold text-foreground">{totalProjects}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center gap-3 space-y-0 pb-2">
            <FileText className="h-5 w-5 text-primary" />
            <CardTitle className="text-sm font-medium text-muted-foreground">
              {t.stories.title}
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold text-foreground">{totalStories}</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center gap-3 space-y-0 pb-2">
            <Sparkles className="h-5 w-5 text-primary" />
            <CardTitle className="text-sm font-medium text-muted-foreground">
              Extractions
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-3xl font-semibold text-foreground">—</p>
          </CardContent>
        </Card>
      </div>

      {/* Recent stories */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">Recent stories</CardTitle>
          <a
            href={`/${locale}/stories`}
            className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground transition-colors"
          >
            {t.nav.stories}
            <ChevronRight className="h-4 w-4" />
          </a>
        </CardHeader>
        <CardContent>
          {recentStories.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-center">
              <FileText className="mb-2 h-8 w-8 text-muted-foreground/50" />
              <p className="text-sm text-muted-foreground">{t.stories.empty_title}</p>
              <p className="text-xs text-muted-foreground/60 mt-1">{t.stories.empty_description}</p>
            </div>
          ) : (
            <div className="space-y-3">
              {recentStories.map((story) => {
                const project = projects.find((p) => p.id === story.projectId);
                return (
                  <a
                    key={story.id}
                    href={`/${locale}/stories/${story.id}`}
                    className="flex items-start justify-between gap-4 rounded-lg border border-border bg-(--color-surface) p-3 transition-colors hover:bg-(--color-surface-secondary)"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-medium text-foreground truncate">
                        {story.rawText || `As a(n) ${story.actor}, I want ${story.feature}`}
                      </p>
                      <div className="flex items-center gap-2 mt-1">
                        {project && (
                          <span className="text-xs text-muted-foreground/60">{project.name}</span>
                        )}
                        <Badge variant="outline" className="text-[10px]">
                          {new Date(story.createdAt).toLocaleDateString(
                            locale === 'es' ? 'es-MX' : 'en-US',
                            { month: 'short', day: 'numeric' }
                          )}
                        </Badge>
                      </div>
                    </div>
                    <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/50 mt-0.5" />
                  </a>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
