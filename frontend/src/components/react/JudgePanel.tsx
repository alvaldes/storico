import { Gavel, Info, ShieldAlert } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { getTranslations, type Locale } from '@/i18n/utils';
import type { JudgeResult } from '@/types/extraction';

/* ── The judge panel (S8) ──────────────────────────────────────────────────
 *
 * One rubric for experts and judge (S1): the seven items on 1–7, plus the two
 * thesis indices (S2) and the total. Nothing is recomputed here: every number
 * comes from the record. Criteria scores and the total render verbatim; TAS
 * and IFI are the two derived means, so they render fixed to one decimal
 * (4.666… reads 4.7) instead of leaking the float's full precision.
 *
 * Three record shapes, three renderings:
 *
 * - `state: "ok"` — the criteria the record carries, in wire order; TAS/IFI
 *   only when the record has them (legacy rows on the old 0–10 rubric do not,
 *   and the panel must not invent them).
 * - `state: "failed"` — the judge was requested and failed: the panel says so,
 *   with the error, and never renders as an empty card (S5).
 * - `null` — the run did not judge, the normal case (D8): nothing at all.
 *
 * Every term on the panel that carries a number the reader cannot decode on its
 * own — each criterion, the approval stamp, TAS and IFI — carries an (i) beside
 * it with the rule behind it. The copy is not rewritten here: the criteria reuse
 * the judge prompt's own question and 1/4/7 anchors (`single_judge.j2`), so the
 * panel explains the scale the judge was actually given.
 */

/** Wire order of the criteria, in the rubric's canonical sequence (F3). `format` is
 * the retired wire name of the fourth position on pre-rubric rows, so it renders in
 * that fourth slot — between feasibility and granularity — and unknown keys still
 * come after the known ones. */
const CRITERION_ORDER = [
  'coherence',
  'completeness',
  'feasibility',
  'format',
  'clarity',
  'granularity',
  'dependencies',
  'usefulness',
] as const;

type CriterionName = (typeof CRITERION_ORDER)[number];

interface JudgePanelProps {
  result: JudgeResult | null;
  locale?: Locale;
}

/** The (i) beside a term. A real `button`, not a decorative span: hovering is not
 * the only way in — the control is focusable and named, so a keyboard or a screen
 * reader reaches the same copy a mouse gets. `delay={0}` because Base UI waits
 * 600 ms by default and a reader who hovers and moves on would see nothing. */
function JudgeHelp({ label, text }: { label: string; text: string }) {
  return (
    <HoverCard>
      <HoverCardTrigger
        delay={0}
        render={
          <button
            type="button"
            aria-label={label}
            className="inline-flex h-4 w-4 shrink-0 cursor-help items-center justify-center rounded-full text-muted-foreground transition-colors outline-none hover:bg-(--color-surface-secondary) hover:text-foreground focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            <Info className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        }
      />
      <HoverCardContent side="top" align="start" className="w-72">
        <p className="text-sm">{text}</p>
      </HoverCardContent>
    </HoverCard>
  );
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

  /** The question the judge was asked for a criterion, and the anchors it was
   * given. A key this build does not know gets no (i) rather than an empty card. */
  const criterionHelp = (name: string): string | null => {
    const helps: Record<CriterionName, string> = {
      coherence: t.judgePanel.help_criterion_coherence,
      completeness: t.judgePanel.help_criterion_completeness,
      feasibility: t.judgePanel.help_criterion_feasibility,
      clarity: t.judgePanel.help_criterion_clarity,
      granularity: t.judgePanel.help_criterion_granularity,
      dependencies: t.judgePanel.help_criterion_dependencies,
      usefulness: t.judgePanel.help_criterion_usefulness,
      format: t.judgePanel.help_criterion_format,
    };
    return helps[name as CriterionName] ?? null;
  };

  const helpLabel = (label: string): string =>
    t.judgePanel.help_trigger.replace('{label}', label);

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
          const label = criterionLabel(name);
          const help = criterionHelp(name);
          return (
            <li key={name} className="space-y-1">
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-1.5">
                  <span className="text-sm font-medium text-foreground">{label}</span>
                  {help && <JudgeHelp label={helpLabel(label)} text={help} />}
                </span>
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
          <span className="inline-flex items-center gap-1.5">
            <Badge variant={result.approved ? 'default' : 'outline'}>
              {result.approved ? t.judgePanel.approved : t.judgePanel.not_approved}
            </Badge>
            <JudgeHelp
              label={helpLabel(
                result.approved ? t.judgePanel.approved : t.judgePanel.not_approved,
              )}
              text={t.judgePanel.help_approved}
            />
          </span>
        )}
        {/* The thesis indices only exist on post-rubric rows; absent means omitted,
            never derived here. One decimal because they are means: a repeating
            third has no meaningful tail. */}
        {result.tas != null && (
          <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
            {t.judgePanel.tas} {result.tas.toFixed(1)}
            <JudgeHelp label={helpLabel(t.judgePanel.tas)} text={t.judgePanel.help_tas} />
          </span>
        )}
        {result.ifi != null && (
          <span className="inline-flex items-center gap-1.5 text-sm text-muted-foreground">
            {t.judgePanel.ifi} {result.ifi.toFixed(1)}
            <JudgeHelp label={helpLabel(t.judgePanel.ifi)} text={t.judgePanel.help_ifi} />
          </span>
        )}
      </div>
    </div>
  );
}
