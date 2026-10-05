import { useTranslations, type Locale } from '@/i18n/utils';
import type { StoryVersion } from '@/types/story';

interface VersionSelectorProps {
  /** Every version of the story, `version_number DESC` as the read returns them. */
  versions: StoryVersion[];
  /** The displayed version's extraction id; `null` before the story's read settles. */
  selectedId: string | null;
  onSelect: (id: string) => void;
  locale?: Locale;
}

/**
 * The story's version selector: one entry per extraction run, the current one
 * marked, failed runs offered with their model and date.
 *
 * Every version is selectable (W6-B1 lifted W6-A's restriction): the store's
 * version-aware read re-fetches a frozen version's tasks through its
 * extraction id, so selecting one displays that version's own tasks rather
 * than the current version's. A failed version's honest state is "no output",
 * which the story page renders — and that card is where its failure reason is
 * read in full.
 *
 * The reason is deliberately **not** part of an option's label: `error_info` is
 * arbitrary-length prose (a refused pooler connection alone runs to a full
 * sentence), and a native `<select>` sizes itself to its widest option, so an
 * embedded reason pushed the control past the content column and clipped it
 * mid-word. The label identifies the run; the card explains it.
 */
export function VersionSelector({
  versions,
  selectedId,
  onSelect,
  locale = 'en',
}: VersionSelectorProps) {
  const t = useTranslations(locale);

  const formatDate = (iso: string) =>
    new Date(iso).toLocaleDateString(locale === 'es' ? 'es-MX' : 'en-US');

  const versionLabel = (v: StoryVersion): string => {
    const parts = [`v${v.versionNumber ?? '?'}`];
    if (v.isCurrent) parts.push(`(${t.versionSelector.current})`);
    if (v.status === 'failed') parts.push(t.versionSelector.failed);
    parts.push(v.modelUsed);
    parts.push(formatDate(v.createdAt));
    return parts.join(' · ');
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <label
        htmlFor="version-selector"
        className="shrink-0 text-sm font-medium text-muted-foreground"
      >
        {t.versionSelector.label}
      </label>
      <select
        id="version-selector"
        value={selectedId ?? versions[0]?.id ?? ''}
        onChange={(e) => onSelect(e.target.value)}
        /* `min-w-0` overrides the flex item's automatic minimum content size, so the
           control can shrink to the row instead of forcing the row wider; `max-w-full`
           bounds it to the container. Together they make an over-long label clip inside
           the control rather than push it off the page. */
        className="min-w-0 max-w-full rounded-md border border-input bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        {versions.map((v) => (
          <option key={v.id} value={v.id}>
            {versionLabel(v)}
          </option>
        ))}
      </select>
    </div>
  );
}
