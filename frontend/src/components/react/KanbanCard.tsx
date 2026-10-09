'use client';

import { Draggable } from '@hello-pangea/dnd';
import { GripVertical, Loader2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import { IconDisplay } from '@/components/ui/icon-display';
import { useTranslations, type Locale } from '@/i18n/utils';
import {
  CONTEXT_LABEL_CAP,
  projectTreatment,
  storyCardTreatment,
} from '@/lib/context-treatment';
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
  // The context chips' treatment comes from the one shared definition in
  // ``lib/context-treatment.ts`` — the same functions the cascade's selects
  // consume, so the two surfaces cannot drift (WU17). The project's icon comes
  // from the task payload (D24 of feature ``kanban-project-icons``): the same
  // batched read that resolves the label, so the card never depends on the
  // capped project list. A null icon draws the folder fallback (D22) and
  // touches neither the label nor the tooltip.
  const projectChip = task.projectName
    ? projectTreatment(task.projectName, CONTEXT_LABEL_CAP, task.projectIcon ?? null)
    : null;
  const storyChip = task.storyId
    ? storyCardTreatment(task.storyId, task.storyRawText ?? null)
    : null;

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
                    Ordered project → story → version → labels (D20 of feature
                    ``kanban-context-tooltips``): the owner moved the labels
                    last, so the three context chips lead and the task's own
                    attributes trail. The labels keep the foreground colour
                    because they are the task's own attributes; the context
                    chips around them are the "where" and sit muted like the
                    version chip. The project is a name as text, not a link
                    (D13) — the card's one click target stays the title — and
                    the story is the same ``shortUUID`` the story cards show
                    (D12), reused so the two surfaces cannot drift.

                    Each chip's tooltip (D17: the project's full name, the
                    story's full sentence) and icon come from the shared
                    treatment, and the real ``Tooltip`` replaced the native
                    ``title`` (D18) so a hover cannot raise two tooltips.
                    ``disabled`` while dragging keeps the popup off the drag
                    clone: the preview is a copy of this tree, and an open
                    tooltip would travel with the pointer.
                  */}
                  {projectChip && (
                    <Tooltip disabled={snapshot.isDragging}>
                      <TooltipTrigger
                        render={
                          <Badge
                            variant="outline"
                            className="max-w-[10rem] text-[10px] leading-none px-1.5 py-0.5 text-muted-foreground"
                          />
                        }
                      >
                        <IconDisplay
                          name={projectChip.iconName}
                          fallback={projectChip.fallback}
                          className="h-3 w-3"
                        />
                        <span className="min-w-0 truncate">{projectChip.label}</span>
                      </TooltipTrigger>
                      <TooltipContent>{projectChip.tooltip}</TooltipContent>
                    </Tooltip>
                  )}
                  {storyChip && (
                    <Tooltip disabled={snapshot.isDragging}>
                      <TooltipTrigger
                        render={
                          <Badge
                            variant="outline"
                            className="text-[10px] leading-none px-1.5 py-0.5 text-muted-foreground"
                          />
                        }
                      >
                        <IconDisplay
                          name={storyChip.iconName}
                          fallback={storyChip.fallback}
                          className="h-3 w-3"
                        />
                        {storyChip.label}
                      </TooltipTrigger>
                      <TooltipContent>{storyChip.tooltip}</TooltipContent>
                    </Tooltip>
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
