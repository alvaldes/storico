"use client";

import { Draggable } from '@hello-pangea/dnd';
import { GripVertical } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useTranslations, type Locale } from '@/i18n/utils';
import type { Task } from '@/types/task';

interface KanbanCardProps {
  task: Task;
  index: number;
  locale: Locale;
}

export function KanbanCard({ task, index, locale }: KanbanCardProps) {
  const t = useTranslations(locale);

  return (
    <Draggable draggableId={task.id} index={index}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          className={`rounded-lg border border-border bg-(--color-surface) p-3 transition-shadow ${
            snapshot.isDragging ? 'shadow-lg ring-2 ring-primary/30' : 'shadow-sm'
          }`}
        >
          <div className="flex items-start gap-2">
            <div
              {...provided.dragHandleProps}
              className="mt-0.5 shrink-0 text-muted-foreground/40 hover:text-muted-foreground cursor-grab active:cursor-grabbing"
            >
              <GripVertical className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <a
                href={`/${locale}/stories/${task.storyId}`}
                className="text-sm font-medium text-foreground hover:text-primary transition-colors line-clamp-2"
              >
                {task.title}
              </a>
              {task.description && (
                <p className="mt-1 text-xs text-muted-foreground line-clamp-2">
                  {task.description}
                </p>
              )}
              {task.labels.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {task.labels.map((label) => (
                    <Badge key={label} variant="outline" className="text-[10px] leading-none px-1.5 py-0.5">
                      {label}
                    </Badge>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </Draggable>
  );
}
