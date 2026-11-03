import { Gavel, ShieldAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { getTranslations, type Locale } from '@/i18n/utils';
import type { JudgeResult } from '@/types/extraction';

/* ── The judge panel (S8) ──────────────────────────────────────────────────
 *
 * One rubric for experts and judge (S1): the seven items on 1–7, plus the two
 * thesis indices (S2) and the total. Every number is displayed exactly as the
 * record carries it — the frontend never recomputes TAS/IFI and never rounds
 * a score to an integer.
 *
 * Three record shapes, three renderings:
 *
 * - `state: "ok"` — the criteria the record carries, in wire order; TAS/IFI
 *   only when the record has them (legacy rows on the old 0–10 rubric do not,
 *   and the panel must not invent them).
 * - `state: "failed"` — the judge was requested and failed: the panel says so,
 *   with the error, and never renders as an empty card (S5).
 * - `null` — the run did not judge, the normal case (D8): nothing at all.
 */

/** Wire order of the criteria. `format` is the retired wire name for clarity on
 * pre-rubric rows; it sorts last so a legacy record still reads in a stable order. */
const CRITERION_ORDER = [
  'coherence',
  'completeness',
  'feasibility',
  'clarity',
  'granularity',
  'dependencies',
  'usefulness',
  'format',
] as const;

type CriterionName = (typeof CRITERION_ORDER)[number];

interface JudgePanelProps {
  result: JudgeResult | null;
  locale?: Locale;
}

export function JudgePanel({ result, locale = 'en' }: JudgePanelProps) {
  const t = getTranslations(locale);

  if (!result) return null;

  if (result.state === 'failed') {
    return (
      <div
        role="alert"
        className="flex items-start gap-3 rounded-xl border border-(--color-destructive-border) bg-(--color-destructive-bg) p-4"
      >
        <ShieldAlert className="mt-0.5 h-4 w-4 shrink-0 text-destructive" />
        <div className="space-y-1">
          <p className="text-sm font-medium text-(--color-destructive-text)">
            {t.judgePanel.failed_title}
          </p>
          {(result.error || result.error_type) && (
            <p className="text-sm text-(--color-destructive-text)">
              {t.judgePanel.failed_desc.replace('{error}', result.error ?? result.error_type!)}
            </p>
          )}
          {result.model && (
            <p className="text-sm text-(--color-destructive-text)">
              {t.judgePanel.model.replace('{model}', result.model)}
            </p>
          )}
        </div>
      </div>
    );
  }

  const criteria = result.criteria ?? {};
  // The criteria the record actually carries: the canonical wire order first,
  // then any unknown key the record brought along, so nothing is dropped.
  const names: string[] = [
    ...CRITERION_ORDER.filter((name) => name in criteria),
    ...Object.keys(criteria).filter((name) => !CRITERION_ORDER.includes(name as CriterionName)),
  ];

  const criterionLabel = (name: string): string => {
    const labels: Record<CriterionName, string> = {
      coherence: t.judgePanel.criterion_coherence,
      completeness: t.judgePanel.criterion_completeness,
      feasibility: t.judgePanel.criterion_feasibility,
      clarity: t.judgePanel.criterion_clarity,
      granularity: t.judgePanel.criterion_granularity,
      dependencies: t.judgePanel.criterion_dependencies,
      usefulness: t.judgePanel.criterion_usefulness,
      format: t.judgePanel.criterion_format,
    };
    return labels[name as CriterionName] ?? name;
  };

  return (
    <div className="rounded-xl border border-border bg-(--color-surface) p-6">
      <div className="flex items-center justify-between gap-2 mb-4">
        <div className="flex items-center gap-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">
          <Gavel className="h-3.5 w-3.5" />
          {t.judgePanel.title}
        </div>
        {result.model && (
          <span className="text-xs text-muted-foreground">
            {t.judgePanel.model.replace('{model}', result.model)}
          </span>
        )}
      </div>

      <ul className="space-y-3">
        {names.map((name) => {
          const criterion = criteria[name];
          return (
            <li key={name} className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium text-foreground">{criterionLabel(name)}</span>
                {/* As it comes: a 4.5 stays 4.5, never rounded to an integer. */}
                <span className="text-sm font-mono text-foreground">{String(criterion.score)}</span>
              </div>
              {criterion.justification && (
                <p className="text-sm text-muted-foreground">{criterion.justification}</p>
              )}
            </li>
          );
        })}
      </ul>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-t border-border pt-3 mt-4">
        {result.total_score != null && result.max_total != null && (
          <span className="text-sm text-muted-foreground">
            {t.judgePanel.total}{' '}
            <span className="font-mono text-foreground">
              {String(result.total_score)}/{String(result.max_total)}
            </span>
          </span>
        )}
        {result.approved != null && (
          <Badge variant={result.approved ? 'default' : 'outline'}>
            {result.approved ? t.judgePanel.approved : t.judgePanel.not_approved}
          </Badge>
        )}
        {/* The thesis indices only exist on post-rubric rows; absent means omitted,
            never derived here. */}
        {result.tas != null && (
          <span className="text-sm text-muted-foreground">
            {t.judgePanel.tas} {String(result.tas)}
          </span>
        )}
        {result.ifi != null && (
          <span className="text-sm text-muted-foreground">
            {t.judgePanel.ifi} {String(result.ifi)}
          </span>
        )}
      </div>
    </div>
  );
}
