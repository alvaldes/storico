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
 * marked, failed runs offered with their error info, model and date.
 *
 * Every version is selectable (W6-B1 lifted W6-A's restriction): the store's
 * version-aware read re-fetches a frozen version's tasks through its
 * extraction id, so selecting one displays that version's own tasks rather
 * than the current version's. A failed version's honest state is "no output",
 * which the story page renders.
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
    if (v.status === 'failed' && v.errorInfo) parts.push(v.errorInfo);
    return parts.join(' · ');
  };

  return (
    <div className="flex items-center gap-2">
      <label
        htmlFor="version-selector"
        className="text-sm font-medium text-muted-foreground"
      >
        {t.versionSelector.label}
      </label>
      <select
        id="version-selector"
        value={selectedId ?? versions[0]?.id ?? ''}
        onChange={(e) => onSelect(e.target.value)}
        className="rounded-md border border-input bg-background px-3 py-1.5 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
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
