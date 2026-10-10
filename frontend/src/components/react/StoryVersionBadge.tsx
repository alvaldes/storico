import { Badge } from '@/components/ui/badge';
import { getTranslations, type Locale } from '@/i18n/utils';
import type { StoryVersionSummary } from '@/types/story';

interface StoryVersionBadgeProps {
  /** The story's projected version summary; `null`/absent means the story has no runs at all. */
  summary?: StoryVersionSummary | null;
  locale?: Locale;
}

/**
 * Shared version badge for every story-list surface (versioning-visibility,
 * WU3 + WU3b): `StoriesList` story cards and the Dashboard's "Recent stories"
 * rows all render this one piece so the copy cannot drift.
 *
 * Decision D1 (owner's choice, 2026-10-07): the current completed run gets the
 * currency marker (`v2 · current`); with no completed run the newest run is
 * shown muted on the `outline` variant (`v2`) — never lie about currency: a
 * run that never completed is never called "current". The story-status badge
 * next to it names that run's outcome.
 *
 * A story with no runs (`summary` null or absent) renders nothing — no badge
 * and no count; nothing is invented.
 */
export function StoryVersionBadge({ summary, locale = 'en' }: StoryVersionBadgeProps) {
  const t = getTranslations(locale);

  if (!summary) return null;

  return (
    <Badge
      variant={summary.currentNumber !== null ? 'default' : 'outline'}
      className={summary.currentNumber !== null ? undefined : 'text-muted-foreground'}
    >
      {summary.currentNumber !== null
        ? `v${summary.currentNumber} · ${t.versionSelector.current}`
        : `v${summary.latestNumber}`}
    </Badge>
  );
}

/**
 * The version-count label shared by the same surfaces (`1 version` /
 * `{count} versions`), singular at exactly 1. Pure so the copy cannot drift
 * between call sites.
 */
export function versionCountLabel(count: number, locale: Locale): string {
  const t = getTranslations(locale);

  return count === 1 ? t.stories.version_count_one : t.stories.version_count_other.replace('{count}', String(count));
}
