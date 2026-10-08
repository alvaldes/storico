import { useEffect, useState, useCallback, useMemo } from 'react';
import { DragDropContext, type DropResult } from '@hello-pangea/dnd';
import { KanbanColumn } from '@/components/react/KanbanColumn';
import { DndErrorBoundary } from '@/components/react/DndErrorBoundary';
import { useTaskStore } from '@/stores/taskStore';
import { useProjectStore } from '@/stores/projectStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { listStories } from '@/lib/stories-api';
import { listVersions } from '@/lib/versioning-api';
import type { WorkspaceTaskFilters } from '@/lib/tasks-api';
import type { StoryVersion, UserStory } from '@/types/story';
import { useTranslations, type Locale } from '@/i18n/utils';
import { AlertCircle, X } from 'lucide-react';
import { LoadingVeil } from '@/components/react/LoadingVeil';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectGroup,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import type { Task, TaskStatus } from '@/types/task';
import { getAllowedTaskTransitions, TASK_STATUSES } from '@/types/task';
import { ErrorDisplay } from '@/components/react/ErrorDisplay';

const COLUMNS = TASK_STATUSES;
type ColumnId = TaskStatus;

interface KanbanBoardProps {
  locale?: Locale;
}

interface InvalidDropToast {
  show: boolean;
  message: string;
  allowed: TaskStatus[];
}

export function KanbanBoard({ locale = 'en' }: KanbanBoardProps) {
  const t = useTranslations(locale);
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspace?.id);
  const { projects, fetchProjects } = useProjectStore();
  const {
    workspaceTasks,
    loading,
    // The failure the store actually records. This page used to keep its own `loadError`
    // state set from a `.catch()` on `fetchTasksForWorkspace` — a promise that never rejects
    // (the store swallows the error and records it here), so the error branch below was
    // unreachable and a failed load showed the empty board with no explanation.
    error: loadError,
    fetchTasksForWorkspace,
    updateTaskStatus,
  } = useTaskStore();

  // The cascade (D5): project → story → version. `null` at a level means "not
  // filtered here"; choosing a project enables the story select, a story the
  // version select. Moving up the cascade clears everything below it, so the
  // resolved query never carries a scope orphaned from its parent.
  const [projectFilter, setProjectFilter] = useState<string | null>(null);
  const [storyFilter, setStoryFilter] = useState<string | null>(null);
  const [versionFilter, setVersionFilter] = useState<string | null>(null);
  // The story and version options are the selected project's/story's data, read
  // straight from their APIs into local state: `useStoryStore` belongs to the
  // stories page, and the board must not write into it (the page's list, cache
  // and selectors would all see the board's reads). Each read also carries its
  // own pending flag: the veil has to cover the cascade's option reads (D3),
  // and an empty select must not be indistinguishable from a loading one.
  const [storiesLoading, setStoriesLoading] = useState(false);
  const [versionsLoading, setVersionsLoading] = useState(false);
  // Which board scope the last settled read answered for, as a string key. The
  // empty states below are only honest once a read has settled *for the filters
  // currently in the bar*: without this, the first paint (and the first paint
  // after a workspace switch) renders an empty `workspaceTasks` as "no tasks
  // yet" for one frame, before the effect has even started the request. A false
  // "no tasks" is the same class of lie as a false "current" badge.
  const [loadedFiltersKey, setLoadedFiltersKey] = useState<string | null>(null);
  const [storyOptions, setStoryOptions] = useState<UserStory[]>([]);
  const [versionOptions, setVersionOptions] = useState<StoryVersion[]>([]);
  const [localTasks, setLocalTasks] = useState<Record<ColumnId, Task[]>>({
    backlog: [],
    todo: [],
    in_progress: [],
    review: [],
    done: [],
  });
  const [invalidDropToast, setInvalidDropToast] = useState<InvalidDropToast>({
    show: false,
    message: '',
    allowed: [],
  });

  // Filters do not survive a workspace switch: a project chosen in workspace A is
  // meaningless in B, where `project_id` belongs to another workspace and would
  // answer 403 or an empty board with the bar still naming it. The reset happens
  // during render (the "adjust state when a prop changes" pattern) rather than in
  // an effect, so the fetch effect committed for the new workspace already sees
  // cleared filters and the board refetches the new workspace unfiltered — an
  // effect here would run one commit late, after a mis-scoped fetch had left.
  const [prevWorkspaceId, setPrevWorkspaceId] = useState(workspaceId);
  if (prevWorkspaceId !== workspaceId) {
    setPrevWorkspaceId(workspaceId);
    setProjectFilter(null);
    setStoryFilter(null);
    setVersionFilter(null);
    setStoryOptions([]);
    setVersionOptions([]);
  }

  // Fetch projects if they haven't been loaded yet (needed for the filter dropdown),
  // exactly as StoriesList feeds its project select.
  useEffect(() => {
    if (projects.length === 0) {
      fetchProjects();
    }
  }, [fetchProjects, projects.length]);

  // Stories of the selected project, capped at 100 like every story list read.
  // A failed read leaves the select empty (and so unusable); it never blocks
  // the unfiltered board. While the read is pending `storiesLoading` holds the
  // veil up (D3) — an empty select must not look like a loaded one.
  useEffect(() => {
    if (!projectFilter) {
      setStoryOptions([]);
      setStoriesLoading(false);
      return;
    }
    let active = true;
    setStoryOptions([]);
    setStoriesLoading(true);
    listStories(projectFilter, 1, 100, workspaceId)
      .then((page) => {
        if (active) {
          setStoryOptions(page.items);
          setStoriesLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setStoryOptions([]);
          setStoriesLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [projectFilter, workspaceId]);

  // Versions of the selected story, ordered `version_number DESC` by the read.
  // Same pending-flag contract as the stories read above.
  useEffect(() => {
    if (!storyFilter) {
      setVersionOptions([]);
      setVersionsLoading(false);
      return;
    }
    let active = true;
    setVersionOptions([]);
    setVersionsLoading(true);
    listVersions(storyFilter)
      .then((history) => {
        if (active) {
          setVersionOptions(history);
          setVersionsLoading(false);
        }
      })
      .catch(() => {
        if (active) {
          setVersionOptions([]);
          setVersionsLoading(false);
        }
      });
    return () => {
      active = false;
    };
  }, [storyFilter]);

  // The cascade as it stands, resolved to the API's most-specific-wins shape (D5):
  // only the most specific scope the user picked is ever handed downstream, so the
  // request that leaves the client can never name two scopes — the backend refuses
  // those with 422 `REQUEST_VALIDATION_FAILED`. (`listTasksByWorkspace` re-resolves
  // with the same rule for any caller that passes a wider set; this board resolves
  // first because it owns the cascade.) `undefined` when nothing is filtered, so the
  // unfiltered call is byte-identical to the pre-filtering one `ExportPanel` makes.
  const activeFilters: WorkspaceTaskFilters | undefined = useMemo(() => {
    if (storyFilter) {
      return versionFilter
        ? { storyId: storyFilter, versionId: versionFilter }
        : { storyId: storyFilter };
    }
    if (projectFilter) return { projectId: projectFilter };
    return undefined;
  }, [projectFilter, storyFilter, versionFilter]);

  /** The board load, with whatever filters are selected right now.
   *
   * Every path — mount effect, cascade change, and the error retry below —
   * goes through this one closure, so a retried load carries the same filters
   * the bar shows instead of silently swapping back to the whole workspace.
   */
  const loadTasks = useCallback(
    (wsId: string) => fetchTasksForWorkspace(wsId, activeFilters),
    [fetchTasksForWorkspace, activeFilters],
  );

  /** The identity of the read the board currently wants: workspace plus cascade. */
  const filtersKey = useMemo(
    () => `${workspaceId ?? ''}|${JSON.stringify(activeFilters ?? null)}`,
    [workspaceId, activeFilters],
  );

  // Fetch tasks on mount, and refetch whenever the cascade changes.
  //
  // `fetchTasksForWorkspace` never rejects: the store swallows the failure and records it
  // in `error`, which is the channel rendered above. The `.catch()` that used to live here
  // could not run, which is why the board had an error branch nothing could reach.
  useEffect(() => {
    if (workspaceId) {
      void loadTasks(workspaceId).then(() => setLoadedFiltersKey(filtersKey));
    }
  }, [loadTasks, workspaceId, filtersKey]);

  // Group tasks by status whenever workspaceTasks changes
  useEffect(() => {
    const grouped: Record<ColumnId, Task[]> = {
      backlog: [],
      todo: [],
      in_progress: [],
      review: [],
      done: [],
    };

    for (const task of workspaceTasks) {
      const status = task.status || 'backlog';
      if (grouped[status]) {
        grouped[status].push(task);
      } else {
        grouped.backlog.push(task);
      }
    }

    setLocalTasks(grouped);
  }, [workspaceTasks]);

  // Patch document.head.removeChild to prevent @hello-pangea/dnd from
  // throwing "Node.removeChild: not a child of this node" during Astro
  // View Transitions. dnd's useStyleMarshal calls head.removeChild(style)
  // during cleanup, but Astro may have already removed the <style> element
  // from <head> as part of the DOM swap. This override handles that case
  // gracefully: if the child is not a child of <head>, just return it.
  useEffect(() => {
    const head = document.head;
    const originalRemoveChild = head.removeChild.bind(head);

    head.removeChild = function safeRemoveChild<T extends Node>(child: T): T {
      if (head.contains(child)) {
        return originalRemoveChild(child);
      }
      return child;
    } as typeof head.removeChild;

    return () => {
      head.removeChild = originalRemoveChild;
    };
  }, []);

  // ── Filter handlers ──
  // Moving up the cascade clears everything below it, so no fetch ever carries a
  // scope orphaned from its parent and the API's one-scope contract is never raced.
  const handleProjectChange = useCallback((value: string | null) => {
    setProjectFilter(value ?? null);
    setStoryFilter(null);
    setVersionFilter(null);
  }, []);

  const handleStoryChange = useCallback((value: string | null) => {
    setStoryFilter(value ?? null);
    setVersionFilter(null);
  }, []);

  const handleVersionChange = useCallback((value: string | null) => {
    setVersionFilter(value ?? null);
  }, []);

  const hasActiveFilter =
    projectFilter !== null || storyFilter !== null || versionFilter !== null;

  const clearFilters = useCallback(() => {
    setProjectFilter(null);
    setStoryFilter(null);
    setVersionFilter(null);
  }, []);

  // Select options: an "All …" entry (value `null`) means "not filtered at this
  // level", the same null-means-unfiltered convention StoriesList's project
  // select uses. "All projects" reuses the stories page's copy — same idea, one key.
  const projectItems = useMemo(
    () => [
      { label: t.stories.allProjects, value: null as string | null },
      ...projects.map((p) => ({ label: p.name, value: p.id as string | null })),
    ],
    [projects, t],
  );

  const storyItems = useMemo(
    () => [
      { label: t.kanban.filter_all_stories, value: null as string | null },
      ...storyOptions.map((s) => ({ label: `${s.actor}: ${s.feature}`, value: s.id as string | null })),
    ],
    [storyOptions, t],
  );

  // D10: the label is `v{n}` plus the currency marker, reusing
  // `versionSelector.current` — not the full model-and-date label the story
  // page's selector needs, which is not a filter key.
  const versionItems = useMemo(
    () => [
      { label: t.kanban.filter_all_versions, value: null as string | null },
      ...versionOptions.map((v) => ({
        label: v.isCurrent
          ? `v${v.versionNumber ?? '?'} · ${t.versionSelector.current}`
          : `v${v.versionNumber ?? '?'}`,
        value: v.id as string | null,
      })),
    ],
    [versionOptions, t],
  );

  const handleDragEnd = useCallback(
    async (result: DropResult) => {
      if (!result.destination) return;
      if (result.source.droppableId === result.destination.droppableId) return;

      const sourceCol = result.source.droppableId as ColumnId;
      const destCol = result.destination.droppableId as ColumnId;
      const taskId = result.draggableId;

      // Find the task to get its current status
      let task: Task | null = null;
      for (const col of COLUMNS) {
        const found = localTasks[col].find((t) => t.id === taskId);
        if (found) {
          task = found;
          break;
        }
      }

      if (!task) return;

      // Client-side validation before attempting the move
      const allowed = getAllowedTaskTransitions(task.status);
      if (!allowed.includes(destCol)) {
        // Show toast with explanation
        const allowedLabels = allowed.map((s) => t.kanban.columns[s]).join(', ');
        setInvalidDropToast({
          show: true,
          message: t.kanban.invalid_drop
            .replace('{from}', t.kanban.columns[task.status])
            .replace('{to}', t.kanban.columns[destCol])
            .replace('{allowed}', allowedLabels),
          allowed,
        });
        setTimeout(() => setInvalidDropToast({ show: false, message: '', allowed: [] }), 5000);
        return;
      }

      // Optimistic reorder
      const newTasks = { ...localTasks };
      const [movedTask] = newTasks[sourceCol].splice(result.source.index, 1);
      if (!movedTask) return;

      const moved = { ...movedTask, status: destCol };
      newTasks[destCol].splice(result.destination.index, 0, moved);
      setLocalTasks(newTasks);

      // Persist
      try {
        await updateTaskStatus(taskId, destCol);
      } catch (err) {
        // Revert optimistic update on error
        setLocalTasks({ ...localTasks });
        if (
          err instanceof Error &&
          'errorCode' in err &&
          (err as any).errorCode === 'INVALID_STATE_TRANSITION'
        ) {
          const apiError = err as any;
          const allowedLabels = apiError.allowedTransitions
            .map((s: string) => t.kanban.columns[s as TaskStatus])
            .join(', ');
          setInvalidDropToast({
            show: true,
            message: t.kanban.backend_invalid_transition
              .replace('{from}', t.kanban.columns[task.status])
              .replace('{to}', t.kanban.columns[destCol])
              .replace('{allowed}', allowedLabels),
            allowed: apiError.allowedTransitions,
          });
          setTimeout(() => setInvalidDropToast({ show: false, message: '', allowed: [] }), 5000);
        }
      }
    },
    [localTasks, updateTaskStatus],
  );

  // WU7 (D2/D3): the veil covers every board read — the tasks fetch (the store
  // claims `loading` for its own request and releases it when it settles), the
  // cascade's stories read and its versions read. It does NOT cover the
  // no-workspace prompt (nothing is being read; the prompt returns below before
  // the veil renders) or a drag-and-drop status update (that path is optimistic,
  // shows the card-level spinner and reports failure by toast — D4). The error
  // branch also wins over the veil: a failed read replaces the page with the
  // error card, veil or not.
  const boardReadInFlight = loading || storiesLoading || versionsLoading;

  if (!workspaceId) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
        <p className="text-sm text-muted-foreground">{t.kanban.no_workspace}</p>
      </div>
    );
  }

  /**
   * Retry the board load, with the filters the bar currently shows.
   *
   * `fetchTasksForWorkspace` raises the store's `loading` before it awaits, so
   * the retry holds the veil up for as long as it is in flight — the same
   * mechanism as every other board read since the inline spinner retired. A
   * retry that fails again still lands on the error branch, which wins over
   * the veil.
   *
   * `loadTasks` reads the cascade from its closure, so the retry refetches the
   * filtered query — a failed filtered load must not quietly become a whole-
   * workspace load with the bar still naming the filter.
   */
  const reload = () => {
    if (workspaceId) void loadTasks(workspaceId);
  };

  if (loadError) {
    return (
      <ErrorDisplay
        friendlyMessage={loadError.friendlyMessage}
        // The store now keeps what the API layer captured, so the card can disclose the HTTP
        // status, the machine code and the raw body instead of only a sentence.
        rawDetail={loadError.rawDetail}
        status={loadError.status}
        errorCode={loadError.errorCode}
        retryLabel={t.common.retry}
        // A refetch is the retry: it clears the recorded error before it starts.
        onRetry={reload}
        locale={locale}
      />
    );
  }

  // Workspace selected but with no tasks and no filter: today's empty copy, with
  // its hint to extract tasks from a story. A board emptied by a filter gets the
  // filtered copy below — the workspace may well have tasks, and the claim must
  // not outlive the filter that emptied it. The filter bar renders in both cases,
  // so an empty workspace can still gain its first filter and a filtered one can
  // always be cleared.
  //
  // Neither copy may render while a board read is in flight (WU7), and neither
  // may render before one has settled *for the filters the bar currently shows*:
  // an empty `workspaceTasks` is not evidence of an empty board, it is only
  // evidence that no answer has arrived yet. `loadedFiltersKey` supplies that
  // proof, so a slow first load cannot paint "no tasks yet" behind the veil or
  // into the accessibility tree.
  const settled = !boardReadInFlight && loadedFiltersKey === filtersKey;
  const unfilteredEmpty = settled && workspaceTasks.length === 0 && !hasActiveFilter;
  const filteredEmpty = settled && workspaceTasks.length === 0 && hasActiveFilter;

  return (
    <div className="absolute inset-0 flex flex-col overflow-hidden">
      {/* Board reads in flight: full-screen veil (WU7). Sits after the error and
          no-workspace returns, so it can only ever cover a settled-layout read. */}
      {boardReadInFlight && <LoadingVeil label={t.common.loading} />}
      {/* Invalid drop toast */}
      {invalidDropToast.show && (
        <div className="fixed top-4 right-4 z-50 max-w-md animate-slide-in">
          <div className="flex items-start gap-3 rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive shadow-lg">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium">{t.kanban.invalid_drop_title}</p>
              <p className="mt-1 text-sm text-destructive/90">{invalidDropToast.message}</p>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setInvalidDropToast({ show: false, message: '', allowed: [] })}
            >
              ✕
            </Button>
          </div>
        </div>
      )}

      <div className="absolute inset-0 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between shrink-0 px-4 lg:px-6 pt-4 lg:pt-6">
          <h1 className="text-2xl font-semibold text-foreground">{t.kanban.title}</h1>
          <span className="text-sm text-muted-foreground">
            {t.kanban.total_tasks.replace('{count}', String(workspaceTasks.length))}
          </span>
        </div>

        {/* Filter bar: cascade Project → Story → Version, resolved server-side by
            most specific wins (D5). Each "All …" option means "not filtered at
            this level"; a select below an unchosen parent stays disabled and says
            what to pick first. */}
        <div className="flex flex-wrap items-center gap-2 shrink-0 px-4 lg:px-6 pt-3">
          <Select
            items={projectItems}
            value={projectFilter ?? null}
            onValueChange={handleProjectChange}
          >
            <SelectTrigger className="w-44" aria-label={t.kanban.filter_project}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {projectItems.map((item) => (
                  <SelectItem key={item.value ?? '_all_projects'} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          <Select
            items={storyItems}
            value={storyFilter ?? null}
            onValueChange={handleStoryChange}
            disabled={!projectFilter}
          >
            <SelectTrigger className="w-52" aria-label={t.kanban.filter_story}>
              {/* While the parent is unchosen the select is disabled; the value
                  is null and the placeholder — not the "All stories" label —
                  names what to pick first. */}
              <SelectValue>{projectFilter ? undefined : t.stories.selectProjectFirst}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {storyItems.map((item) => (
                  <SelectItem key={item.value ?? '_all_stories'} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          <Select
            items={versionItems}
            value={versionFilter ?? null}
            onValueChange={handleVersionChange}
            disabled={!storyFilter}
          >
            <SelectTrigger className="w-44" aria-label={t.kanban.filter_version}>
              <SelectValue>{storyFilter ? undefined : t.kanban.filter_select_story}</SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectGroup>
                {versionItems.map((item) => (
                  <SelectItem key={item.value ?? '_all_versions'} value={item.value}>
                    {item.label}
                  </SelectItem>
                ))}
              </SelectGroup>
            </SelectContent>
          </Select>
          {hasActiveFilter && (
            <Button variant="ghost" size="sm" onClick={clearFilters}>
              <X className="h-4 w-4" />
              {t.kanban.filter_clear}
            </Button>
          )}
        </div>

        <div className="flex-1 min-h-0 overflow-hidden overflow-x-auto px-4 lg:px-6 pb-4 lg:pb-6 pt-4">
          {filteredEmpty ? (
            // The filter emptied the board — the workspace may well have tasks.
            // Its own copy, with the hint that leads back out via the bar above.
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
              <p className="text-sm font-medium text-foreground">{t.kanban.empty_filtered}</p>
              <p className="mt-2 text-sm text-muted-foreground">{t.kanban.empty_filtered_hint}</p>
            </div>
          ) : unfilteredEmpty ? (
            <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
              <p className="text-sm font-medium text-foreground">{t.kanban.empty_board}</p>
              <p className="mt-2 text-sm text-muted-foreground">{t.kanban.empty_board_hint}</p>
            </div>
          ) : (
            <DndErrorBoundary>
              <DragDropContext onDragEnd={handleDragEnd}>
                <div className="flex gap-4 h-full items-stretch" style={{ minWidth: 'fit-content' }}>
                  {COLUMNS.map((colId) => (
                    <KanbanColumn
                      key={colId}
                      columnId={colId}
                      title={t.kanban.columns[colId]}
                      tasks={localTasks[colId]}
                      locale={locale}
                    />
                  ))}
                </div>
              </DragDropContext>
            </DndErrorBoundary>
          )}
        </div>
      </div>
    </div>
  );
}
