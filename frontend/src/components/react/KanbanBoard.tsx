"use client";

import { useEffect, useState, useCallback } from 'react';
import { DragDropContext, type DropResult } from '@hello-pangea/dnd';
import { KanbanColumn } from '@/components/react/KanbanColumn';
import { DndErrorBoundary } from '@/components/react/DndErrorBoundary';
import { useTaskStore } from '@/stores/taskStore';
import { useWorkspaceStore } from '@/stores/workspaceStore';
import { useTranslations, type Locale } from '@/i18n/utils';
import { Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import type { Task } from '@/types/task';

const COLUMNS = ['backlog', 'todo', 'in_progress', 'review', 'done'] as const;
type ColumnId = (typeof COLUMNS)[number];

interface KanbanBoardProps {
  locale?: Locale;
}

export function KanbanBoard({ locale = 'en' }: KanbanBoardProps) {
  const t = useTranslations(locale);
  const workspaceId = useWorkspaceStore((s) => s.currentWorkspace?.id);
  const { workspaceTasks, loading, error, fetchTasksForWorkspace, updateTaskStatus } = useTaskStore();

  const [initialLoad, setInitialLoad] = useState(true);
  const [localTasks, setLocalTasks] = useState<Record<ColumnId, Task[]>>({
    backlog: [],
    todo: [],
    in_progress: [],
    review: [],
    done: [],
  });

  // Fetch tasks on mount
  useEffect(() => {
    if (workspaceId) {
      fetchTasksForWorkspace(workspaceId).then(() => setInitialLoad(false));
    } else {
      setInitialLoad(false);
    }
  }, [fetchTasksForWorkspace, workspaceId]);

  // Group tasks by status whenever workspaceTasks changes
  useEffect(() => {
    const grouped: Record<string, Task[]> = {
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

    setLocalTasks(grouped as Record<ColumnId, Task[]>);
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

      // Optimistic reorder
      const newTasks = { ...localTasks };
      const [movedTask] = newTasks[sourceCol].splice(result.source.index, 1);
      if (!movedTask) return;

      const moved = { ...movedTask, status: destCol };
      newTasks[destCol].splice(result.destination.index, 0, moved);
      setLocalTasks(newTasks);

      // Persist
      await updateTaskStatus(taskId, destCol);
    },
    [localTasks, updateTaskStatus],
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

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-border py-20">
        <p className="text-sm text-muted-foreground">{t.kanban.error_load}</p>
        <Button
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => workspaceId && fetchTasksForWorkspace(workspaceId)}
        >
          {t.common.retry}
        </Button>
      </div>
    );
  }

  return (
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
  );
}
