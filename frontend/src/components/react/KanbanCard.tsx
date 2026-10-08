'use client';

import { Draggable } from '@hello-pangea/dnd';
import { Fingerprint, FolderKanban, GripVertical, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { useTranslations, type Locale } from '@/i18n/utils';
import { shortUUID, shortProjectTitle } from '@/lib/utils';
import { useTaskStore } from '@/stores/taskStore';
import type { Task } from '@/types/task';

interface KanbanCardProps {
  task: Task;
  index: number;
  locale: Locale;
}

export function KanbanCard({ task, index, locale }: KanbanCardProps) {
  const t = useTranslations(locale);
  // While a status PUT is in flight for this task, the card shows a subtle
  // loading indicator and must not be re-draggable.
  const isUpdating = useTaskStore((s) => s.updatingTaskId === task.id);

  return (
    <Draggable draggableId={task.id} index={index} isDragDisabled={isUpdating}>
      {(provided, snapshot) => (
        <div
          ref={provided.innerRef}
          {...provided.draggableProps}
          className={`rounded-lg border border-border bg-(--color-surface) p-3 transition-shadow ${
            snapshot.isDragging ? 'shadow-lg ring-2 ring-primary/30' : 'shadow-sm'
          } ${isUpdating ? 'opacity-70' : ''}`}
          aria-busy={isUpdating}
        >
          <div className="flex items-start gap-2">
            <div
              {...(isUpdating ? {} : provided.dragHandleProps)}
              className={`mt-0.5 shrink-0 text-muted-foreground/40 ${
                isUpdating
                  ? 'cursor-wait'
                  : 'hover:text-muted-foreground cursor-grab active:cursor-grabbing'
              }`}
            >
              {isUpdating ? (
                <Loader2 className="h-4 w-4 animate-spin" aria-label={t.common.loading} />
              ) : (
                <GripVertical className="h-4 w-4" />
              )}
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
              {(task.projectName ||
                task.storyId ||
                task.labels.length > 0 ||
                task.versionNumber !== null) && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {/*
                    Ordered project → story → labels → version (D15 of feature
                    ``kanban-card-project-story``): the labels keep the foreground
                    colour because they are the task's own attributes; the three
                    context chips around them are the "where" and sit muted like
                    the version chip. The project is a name as text, not a link
                    (D13) — the card's one click target stays the title — and the
                    story is the same ``shortUUID`` the story cards show (D12),
                    reused so the two surfaces cannot drift. The long project
                    name ellipsizes inside its bounded chip (title keeps the
                    full name) instead of pushing the row out of the card.
                  */}
                  {task.projectName && (
                    <Badge
                      variant="outline"
                      className="max-w-[10rem] text-[10px] leading-none px-1.5 py-0.5 text-muted-foreground"
                      title={task.projectName}
                    >
                      <FolderKanban className="h-3 w-3" />
                      <span className="min-w-0 truncate">
                        {shortProjectTitle(task.projectName)}
                      </span>
                    </Badge>
                  )}
                  {task.storyId && (
                    <Badge
                      variant="outline"
                      className="text-[10px] leading-none px-1.5 py-0.5 text-muted-foreground"
                    >
                      <Fingerprint className="h-3 w-3" />
                      {shortUUID(task.storyId)}
                    </Badge>
                  )}
                  {/*
                    Bare `v{n}`: never a currency marker. A card cannot tell a
                    current-version board read from a frozen-version read — only the
                    story's summary knows which run is current (D1/D8 of feature
                    ``versioning-visibility``) — so `v2 · current` here would be a lie.
                    Null renders nothing, not a degraded badge.
                  */}
                  {task.versionNumber !== null && (
                    <Badge
                      variant="outline"
                      className="text-[10px] leading-none px-1.5 py-0.5 text-muted-foreground"
                    >
                      {`v${task.versionNumber}`}
                    </Badge>
                  )}
                  {task.labels.map((label) => (
                    <Badge
                      key={label}
                      variant="outline"
                      className="text-[10px] leading-none px-1.5 py-0.5"
                    >
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
