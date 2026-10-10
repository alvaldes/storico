'use client';

import { IconDisplay } from '@/components/ui/icon-display';
import { SelectItem } from '@/components/ui/select';
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip';
import type { ContextTreatment } from '@/lib/context-treatment';

/** One row of a context select's dropdown — the project and story rows the
 * board's cascade and the export page's toolbar both render. The label is the
 * visible (truncated) one; `treatment` is the shared context treatment — its
 * icon is a name plus fallback rendered through ``IconDisplay`` (D23 of
 * feature ``kanban-project-icons``) and its `tooltip` is the full value the
 * row's hover raises —, `null` for the "All …" rows that name no project or
 * story. Moved here from ``KanbanBoard`` so the two surfaces cannot drift: the
 * row markup carries a load-bearing subtlety (see ``ContextSelectRow``), and
 * two hand-maintained copies of it is how that comes back. */
export interface ContextSelectItem {
  label: string;
  value: string | null;
  /** The shared treatment, which carries the icon and the tooltip's full value;
   * `null` for the "All …" rows that name no project or story. */
  treatment: ContextTreatment | null;
}

/** One treated row of a context select's dropdown, shared by every surface
 * that names a project or a story the way the board does — today the board's
 * cascade and the export page's toolbar (EP6 of ``export-page-rework``). The
 * icon, the truncated label and the tooltip's full value all come from the
 * row's shared treatment, so both surfaces agree by construction rather than
 * by accident.
 *
 * Two things here are load-bearing, not style:
 *
 * - The row's hover is our tooltip, never a native `title`: the title arrives
 *   late in the browser's own style, and it is the only way to read a value
 *   the shared cap shortened — a row cut to a dozen characters behind a
 *   tooltip nobody sees loses the name entirely (D18 of feature
 *   ``kanban-context-tooltips``).
 * - The ``TooltipTrigger`` **is** the ``SelectItem`` (``render={<SelectItem
 *   value={item.value} />}``), never a wrapper around it: a wrapper span
 *   inside the option swallowed the click and the row stopped selecting, which
 *   is a worse failure than the hover it was meant to fix.
 *
 * The React `key` stays with the caller, which knows its own row identity. */
export function ContextSelectRow({ item }: { item: ContextSelectItem }) {
  return (
    <Tooltip disabled={!item.treatment}>
      <TooltipTrigger render={<SelectItem value={item.value} />}>
        {item.treatment && (
          <span aria-hidden="true">
            <IconDisplay name={item.treatment.iconName} fallback={item.treatment.fallback} />
          </span>
        )}
        {item.label}
      </TooltipTrigger>
      {item.treatment && <TooltipContent>{item.treatment.tooltip}</TooltipContent>}
    </Tooltip>
  );
}
