import { useEffect, useState, useCallback } from 'react';
import { DragDropContext, type DropResult } from '@hello-pangea/dnd';
import { KanbanColumn } from '@/components/react/KanbanColumn';
import { DndErrorBoundary } from '@/components/react/DndErrorBoundary';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useTranslations, type Locale } from '@/i18n/utils';
import { Loader2, AlertCircle } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Task, TaskStatus } from '@/types/task';
import { getAllowedTaskTransitions, TASK_STATUSES } from '@/types/task';
import { ErrorDisplay } from '@/components/react/ErrorDisplay';
import { ApiRequestError } from '@/lib/api';

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
  const {
    workspaceTasks,
    loading,
    fetchTasksForWorkspace,
    updateTaskStatus,
  } = useTaskStore();

  const [initialLoad, setInitialLoad] = useState(true);
  const [localTasks, setLocalTasks] = useState<Record<ColumnId, Task[]>>({
    backlog: [],
    todo: [],
    in_progress: [],
    review: [],
    done: [],
  });
  const [invalidDropToast, setInvalidDropToast] = useState<InvalidDropToast>({ show: false, message: '', allowed: [] });
  const [loadError, setLoadError] = useState<ApiRequestError | null>(null);

  // Fetch tasks on mount
  useEffect(() => {
    if (workspaceId) {
      fetchTasksForWorkspace(workspaceId)
        .then(() => {
          setInitialLoad(false);
          setLoadError(null);
        })
        .catch((err) => {
          setInitialLoad(false);
          if (err instanceof ApiRequestError) {
            setLoadError(err);
          } else {
            setLoadError(new ApiRequestError(0, 'Unknown Error', err instanceof Error ? err.message : 'Unknown error', err));
          }
        });
    } else {
      setInitialLoad(false);
    }
  }, [fetchTasksForWorkspace, workspaceId]);

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
        if (err instanceof Error && 'errorCode' in err && (err as any).errorCode === 'INVALID_STATE_TRANSITION') {
          const apiError = err as any;
          const allowedLabels = apiError.allowedTransitions.map((s: string) => t.kanban.columns[s as TaskStatus]).join(', ');
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
    [localTasks, updateTaskStatus]
  );

  if (initialLoad && loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!workspaceId) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
        <p className="text-sm text-muted-foreground">
          {t.kanban.no_workspace}
        </p>
      </div>
    );
  }

  if (loadError) {
    return (
      <ErrorDisplay
        friendlyMessage={loadError.message}
        rawDetail={loadError.rawError.rawBody}
        status={loadError.status}
        errorCode={loadError.errorCode}
        retryLabel={t.common.retry}
        onRetry={() => workspaceId && fetchTasksForWorkspace(workspaceId)}
        onDismiss={() => setLoadError(null)}
        locale={locale}
      />
    );
  }

  return (
    <div className="absolute inset-0 flex flex-col overflow-hidden">
      {/* Invalid drop toast */}
      {invalidDropToast.show && (
        <div className="fixed top-4 right-4 z-50 max-w-md animate-slide-in">
          <div className="flex items-start gap-3 rounded-lg border border-destructive bg-destructive/10 p-4 text-destructive shadow-lg">
            <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
            <div className="flex-1">
              <p className="text-sm font-medium">{t.kanban.invalid_drop_title}</p>
              <p className="mt-1 text-sm text-destructive/90">{invalidDropToast.message}</p>
            </div>
            <Button variant="ghost" size="sm" onClick={() => setInvalidDropToast({ show: false, message: '', allowed: [] })}>
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

        <div className="flex-1 min-h-0 overflow-hidden overflow-x-auto px-4 lg:px-6 pb-4 lg:pb-6 pt-4">
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
        </div>
      </div>
    </div>
  );
}