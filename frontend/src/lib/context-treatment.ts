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
 * carries UI decisions — an icon name plus fallback per kind, a truncation cap per
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

/** How much of a project or story label stays visible before the ellipsis.
 *
 * One cap for both surfaces, which is the owner's call of 2026-10-08: the card
 * chip and the select's rows must show the same short text, because seeing
 * ``Version Test...`` on a card and ``Version Test LongTitle`` in the dropdown
 * for the same project reads as two different projects. It reverses D21, which
 * gave the select a wider cap of its own on the argument that a truncated
 * dropdown row is choosable only by hovering every option; the owner weighed
 * that and chose the shorter, consistent row — the tooltip carries the rest,
 * and it opens without a perceptible pause since `e8fe5a1`. */
export const CONTEXT_LABEL_CAP = 12;

/** What one surface shows for a project or a story: the icon — a **name plus
 * a fallback component** for `IconDisplay` (D23 of feature
 * ``kanban-project-icons``: the project's icon is a kebab-case name from the
 * picker, while the story's fingerprint is a fixed component that name map
 * does not contain, so a purely name-based treatment would draw the story a
 * folder) —, the visible (truncated) label and the tooltip's full value (D17).
 * Both surfaces render through `<IconDisplay name={t.iconName}
 * fallback={t.fallback} />`. */
export interface ContextTreatment {
  /** The icon name `IconDisplay` resolves, or `null` when the kind has no
   * name — the story's is a fixed component, never a name. */
  iconName: string | null;
  /** The fallback `IconDisplay` draws when the name is null or unknown. */
  fallback: LucideIcon;
  label: string;
  tooltip: string;
}

/** The project treatment: the project's own icon name — the card passes the
 * task payload's, the select the project row's (D24) — falling back to
 * `FolderKanban`, which is what the rest of the app already draws for a
 * project without an icon (`ProjectForm` seeds `'folder-kanban'`), so the
 * fallback is not a second opinion (D22). The full name in the tooltip, the
 * name truncated at `maxCharacters` as the label. Both surfaces take the
 * default cap now: the select used to pass a wider one of its own (D21), and
 * the owner asked for the badge's short text on both. */
export function projectTreatment(
  name: string,
  maxCharacters: number = CONTEXT_LABEL_CAP,
  iconName: string | null = null,
): ContextTreatment {
  return {
    iconName,
    fallback: FolderKanban,
    label: shortProjectTitle(name, maxCharacters),
    tooltip: name,
  };
}

/** The story treatment on the card: the same ``shortUUID`` label the story
 * cards show (D12), and the story's full sentence in the tooltip (D17). A
 * missing sentence (``story_raw_text`` null) falls back to the id — the
 * tooltip shows what the card has, never an empty popup. */
export function storyCardTreatment(storyId: string, sentence: string | null): ContextTreatment {
  // The story has no icon name: `'fingerprint'` is absent from `IconDisplay`'s
  // map, so the fingerprint must stay a fallback, never a name (D23) — a name
  // here would silently draw a folder.
  return { iconName: null, fallback: Fingerprint, label: shortUUID(storyId), tooltip: sentence ?? storyId };
}

/** The story treatment in the cascade's select: the story's short id, then the
 * human ``${actor}: ${feature}`` label shortened by the shared cap, and the
 * full sentence in the tooltip, falling back to the label when the sentence is
 * missing.
 *
 * The id is the owner's addition of 2026-10-08 (``01a10dee · UI designer:...``)
 * so a story reads the same way on the board's card and in the dropdown; it
 * amends D16, which had kept the select on the human label alone. The id is not
 * truncated — it is already short, and cutting it would make two stories of one
 * actor share six characters *and* lose the two that separate them. */
export function storySelectTreatment(story: {
  id: string;
  actor: string;
  feature: string;
  rawText: string | null;
}): ContextTreatment {
  const label = `${story.actor}: ${story.feature}`;
  const shortLabel = `${shortUUID(story.id)} · ${shortProjectTitle(label, CONTEXT_LABEL_CAP)}`;
  return { iconName: null, fallback: Fingerprint, label: shortLabel, tooltip: story.rawText ?? label };
}
