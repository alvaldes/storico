"use client";

import { Droppable } from '@hello-pangea/dnd';
import { KanbanCard } from '@/components/react/KanbanCard';
import { useTranslations, type Locale } from '@/i18n/utils';
import type { Task } from '@/types/task';

interface KanbanColumnProps {
  columnId: string;
  title: string;
  tasks: Task[];
  locale: Locale;
}

export function KanbanColumn({ columnId, title, tasks, locale }: KanbanColumnProps) {
  const t = useTranslations(locale);

  return (
    <div className="flex w-72 shrink-0 flex-col rounded-xl border border-border bg-(--color-surface-secondary)/50">
      {/* Column header */}
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <span className="inline-flex items-center justify-center rounded-full bg-(--color-surface-tertiary) px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {tasks.length}
        </span>
      </div>

      {/* Tasks */}
      <Droppable droppableId={columnId}>
        {(provided, snapshot) => (
          <div
            ref={provided.innerRef}
            {...provided.droppableProps}
            className={`flex flex-col gap-2 p-3 min-h-[120px] transition-colors ${
              snapshot.isDraggingOver ? 'bg-primary/5' : ''
            }`}
          >
            {tasks.length === 0 && !snapshot.isDraggingOver && (
              <div className="flex flex-col items-center justify-center py-8 text-xs text-muted-foreground">
                {t.kanban.empty_column}
              </div>
            )}
            {tasks.map((task, index) => (
              <KanbanCard key={task.id} task={task} index={index} locale={locale} />
            ))}
            {provided.placeholder}
          </div>
        )}
      </Droppable>
    </div>
  );
}
