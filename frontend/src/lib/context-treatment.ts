/**
 * What the board says about a project and a story, in one place.
 *
 * The Kanban card's context chips and the cascade's selects name the same two
 * things — project, story — and must agree by construction rather than by
 * accident: the icon, the label rule and the tooltip text for each kind live
 * only here, and both surfaces consume these functions (WU17 of feature
 * ``kanban-context-tooltips``).
 *
 * This is not a generic helper, which is why it is not in ``utils.ts``: it
 * carries UI decisions — an icon component per kind, a truncation cap per
 * surface — and ``utils.ts`` is imported by 41 modules that have no business
 * pulling an icon library for ``cn()``.
 */

import { Fingerprint, FolderKanban, type LucideIcon } from 'lucide-react';

import { shortProjectTitle, shortUUID } from '@/lib/utils';

/* ── Context-chip treatment (WU17 of feature ``kanban-context-tooltips``) ──
 *
 * The Kanban card's chips and the cascade's selects name the same two things —
 * project, story — and must agree by construction, not by accident. The icon,
 * the label rule and the tooltip text for each kind live only here; both
 * surfaces consume these functions.
 */

/** The project name's character cap on the card chip (the owner's, `0fa72d3`). */
export const CARD_PROJECT_CAP = 12;
/** The wider cap the cascade's select options pass through `maxCharacters`
 * (D21): a dropdown row is far wider than a card chip, and truncating it to
 * the card's 12 characters would make choosing impossible without hovering
 * every option. */
export const SELECT_PROJECT_CAP = 32;

/** What one surface shows for a project or a story: the icon, the visible
 * (truncated) label and the tooltip's full value (D17). */
export interface ContextTreatment {
  Icon: LucideIcon;
  label: string;
  tooltip: string;
}

/** The project treatment: the full name in the tooltip, the name truncated at
 * `maxCharacters` as the label. The card calls it with the default (its
 * 12-character cap); the select's options and trigger pass `SELECT_PROJECT_CAP`. */
export function projectTreatment(
  name: string,
  maxCharacters: number = CARD_PROJECT_CAP,
): ContextTreatment {
  return { Icon: FolderKanban, label: shortProjectTitle(name, maxCharacters), tooltip: name };
}

/** The story treatment on the card: the same ``shortUUID`` label the story
 * cards show (D12), and the story's full sentence in the tooltip (D17). A
 * missing sentence (``story_raw_text`` null) falls back to the id — the
 * tooltip shows what the card has, never an empty popup. */
export function storyCardTreatment(storyId: string, sentence: string | null): ContextTreatment {
  return { Icon: Fingerprint, label: shortUUID(storyId), tooltip: sentence ?? storyId };
}

/** The story treatment in the cascade's select: the human label
 * ``${actor}: ${feature}`` — not the short id, which a list of uuid prefixes
 * is not choosable by (D16) — and the full sentence in the tooltip, falling
 * back to the label when the sentence is missing. */
export function storySelectTreatment(story: {
  actor: string;
  feature: string;
  rawText: string | null;
}): ContextTreatment {
  const label = `${story.actor}: ${story.feature}`;
  return { Icon: Fingerprint, label, tooltip: story.rawText ?? label };
}
