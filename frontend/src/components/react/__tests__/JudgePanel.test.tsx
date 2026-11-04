import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { JudgePanel } from '@/components/react/JudgePanel';
import { getTranslations } from '@/i18n/utils';
import type { JudgeResult } from '@/types/extraction';

/* ── Why this file exists ──────────────────────────────────────────────────
 *
 * The judge record (S8) reaches the UI in three shapes, and every one has an
 * observable obligation:
 *
 * - `state: "ok"` — the seven rubric criteria on the 1–7 scale with their
 *   justifications, plus TAS, IFI and the total, all displayed from the record
 *   and never recomputed. Criteria scores and the total render verbatim;
 *   TAS/IFI are the two derived indices and render fixed to one decimal.
 * - `state: "failed"` — the panel must say the judge was requested and failed,
 *   with its error. Never an empty panel: "requested and failed" is a third
 *   state (S5), not a missing one.
 * - legacy rows (written before the 1–7 rubric) — five 0–10 criteria with the
 *   wire name `format` and no `tas`/`ifi` keys. The panel renders what the
 *   record has and omits TAS/IFI rather than inventing them.
 *
 * `null` — the run did not judge, the normal case — renders nothing at all.
 * ─────────────────────────────────────────────────────────────────────────── */

const t = getTranslations('en');

// `satisfies` pins the wire shape at compile time: the ok record proves the type
// admits concrete indices, the failed record proves it admits `tas: null` /
// `ifi: null` — what the backend persists on every failed record (F1).
const okRecord = {
  state: 'ok',
  criteria: {
    coherence: { score: 5, justification: 'All tasks belong to the story.' },
    completeness: { score: 6, justification: null },
    feasibility: { score: 4, justification: 'One task needs a fix before it can run.' },
    clarity: { score: 6.5, justification: 'Clear enough to work from.' },
    granularity: { score: 5, justification: null },
    dependencies: { score: 6, justification: null },
    usefulness: { score: 7, justification: 'Usable in a sprint as is.' },
  },
  total_score: 39.5,
  max_total: 49,
  approved: true,
  tas: 4.5,
  ifi: 5.833333333333333,
  model: 'qwen2.5:7b',
  model_source: 'workspace',
  error: null,
  error_type: null,
} satisfies JudgeResult;

const failedRecord = {
  state: 'failed',
  criteria: {},
  total_score: null,
  max_total: 49,
  approved: false,
  tas: null,
  ifi: null,
  model: 'qwen2.5:7b',
  model_source: 'workspace',
  error: 'model returned an unusable rubric',
  error_type: 'JudgeOutputError',
} satisfies JudgeResult;

/** Pre-rubric row (written before T3): five criteria on 0–10, `format`, no TAS/IFI. */
const legacyRecord = {
  state: 'ok',
  criteria: {
    coherence: { score: 8, justification: 'coherent' },
    completeness: { score: 7, justification: null },
    feasibility: { score: 9, justification: null },
    format: { score: 6, justification: null },
    granularity: { score: 5, justification: null },
  },
  total_score: 35,
  max_total: 50,
  approved: true,
  error: null,
  error_type: null,
} as unknown as JudgeResult;

describe('JudgePanel', () => {
  it('renders the seven criteria, their justifications, TAS, IFI, the total and the model for an ok record', () => {
    render(<JudgePanel result={okRecord} locale="en" />);

    expect(screen.getByText(t.judgePanel.title)).toBeInTheDocument();
    for (const key of [
      'criterion_coherence',
      'criterion_completeness',
      'criterion_feasibility',
      'criterion_clarity',
      'criterion_granularity',
      'criterion_dependencies',
      'criterion_usefulness',
    ] as const) {
      expect(screen.getByText(t.judgePanel[key])).toBeInTheDocument();
    }

    // Justifications travel with their criterion.
    expect(screen.getByText('One task needs a fix before it can run.')).toBeInTheDocument();
    expect(screen.getByText('All tasks belong to the story.')).toBeInTheDocument();

    // TAS is the stored mean (already one decimal) and IFI is the stored
    // non-terminating mean, shown fixed to one decimal: 5.833… reads 5.8. The
    // criterion score 6.5 and the total still render exactly as persisted.
    expect(screen.getByText('TAS 4.5')).toBeInTheDocument();
    expect(screen.getByText('IFI 5.8')).toBeInTheDocument();
    expect(screen.getByText('39.5/49')).toBeInTheDocument();
    expect(screen.getByText('6.5')).toBeInTheDocument();
    expect(screen.getByText('Judged by qwen2.5:7b')).toBeInTheDocument();
  });

  it('shows an integer TAS/IFI with the fixed decimal rather than a bare integer', () => {
    render(
      <JudgePanel
        result={{ ...okRecord, tas: 7, ifi: 4.666666666666667 }}
        locale="en"
      />,
    );

    // "Fixed to one decimal" is the rule, not "as many decimals as it happens
    // to carry": a whole-number mean keeps its decimal and a repeating mean
    // stops at one place.
    expect(screen.getByText('TAS 7.0')).toBeInTheDocument();
    expect(screen.getByText('IFI 4.7')).toBeInTheDocument();
  });

  it('carries an info control beside every criterion, the status, TAS and IFI', () => {
    render(<JudgePanel result={okRecord} locale="en" />);

    // Every explained term owns one control, and the control is NAMED after the
    // term it explains — a hover is not the only way in: the control is a real
    // button, so keyboard and screen-reader users reach the same copy.
    const explained = [
      t.judgePanel.criterion_coherence,
      t.judgePanel.criterion_completeness,
      t.judgePanel.criterion_feasibility,
      t.judgePanel.criterion_clarity,
      t.judgePanel.criterion_granularity,
      t.judgePanel.criterion_dependencies,
      t.judgePanel.criterion_usefulness,
      t.judgePanel.approved,
      t.judgePanel.tas,
      t.judgePanel.ifi,
    ];
    for (const label of explained) {
      expect(
        screen.getByRole('button', { name: t.judgePanel.help_trigger.replace('{label}', label) }),
      ).toBeInTheDocument();
    }
  });

  it('explains a criterion with the rubric question and its 1/4/7 anchors on hover', async () => {
    const user = userEvent.setup();
    render(<JudgePanel result={okRecord} locale="en" />);

    await user.hover(
      screen.getByRole('button', {
        name: t.judgePanel.help_trigger.replace('{label}', t.judgePanel.criterion_coherence),
      }),
    );

    // The copy is the judge prompt's own anchor set, so the panel explains the
    // scale the judge was actually given, not a paraphrase written later.
    expect(await screen.findByText(t.judgePanel.help_criterion_coherence)).toBeInTheDocument();
  });

  it('explains what approval means and what TAS and IFI are', async () => {
    const user = userEvent.setup();
    render(<JudgePanel result={okRecord} locale="en" />);

    await user.hover(
      screen.getByRole('button', {
        name: t.judgePanel.help_trigger.replace('{label}', t.judgePanel.approved),
      }),
    );
    expect(await screen.findByText(t.judgePanel.help_approved)).toBeInTheDocument();
  });

  it('explains the retired format criterion with its own retired-rubric copy', async () => {
    const user = userEvent.setup();
    render(<JudgePanel result={legacyRecord} locale="en" />);

    await user.hover(
      screen.getByRole('button', {
        name: t.judgePanel.help_trigger.replace('{label}', t.judgePanel.criterion_format),
      }),
    );
    expect(await screen.findByText(t.judgePanel.help_criterion_format)).toBeInTheDocument();
  });

  it('renders the failure with its error for a failed record — never an empty panel', () => {
    render(<JudgePanel result={failedRecord} locale="en" />);

    expect(screen.getByText(t.judgePanel.failed_title)).toBeInTheDocument();
    expect(
      screen.getByText(t.judgePanel.failed_desc.replace('{error}', failedRecord.error!)),
    ).toBeInTheDocument();
    // The failed record still names who was asked (D7).
    expect(screen.getByText('Judged by qwen2.5:7b')).toBeInTheDocument();
    // No criteria and no indices are invented for a run that produced none.
    expect(screen.queryByText(t.judgePanel.criterion_coherence)).not.toBeInTheDocument();
    expect(screen.queryByText('TAS 4.5')).not.toBeInTheDocument();
    // And nothing is explained that is not on screen: no stamp, no indices, no
    // info controls to hover.
    expect(screen.queryAllByRole('button')).toHaveLength(0);
  });

  it('renders a legacy record with its five criteria and omits TAS/IFI without throwing', () => {
    render(<JudgePanel result={legacyRecord} locale="en" />);

    // The five criteria the row actually carries — including the retired wire
    // name `format` — render with their 0–10 scores untouched.
    expect(screen.getByText(t.judgePanel.criterion_coherence)).toBeInTheDocument();
    expect(screen.getByText(t.judgePanel.criterion_completeness)).toBeInTheDocument();
    expect(screen.getByText(t.judgePanel.criterion_feasibility)).toBeInTheDocument();
    expect(screen.getByText(t.judgePanel.criterion_format)).toBeInTheDocument();
    expect(screen.getByText(t.judgePanel.criterion_granularity)).toBeInTheDocument();
    expect(screen.getByText('35/50')).toBeInTheDocument();

    // The thesis indices are absent from the record, so they are absent from
    // the panel — the frontend must not derive them.
    expect(screen.queryByText(/TAS/)).not.toBeInTheDocument();
    expect(screen.queryByText(/IFI/)).not.toBeInTheDocument();

    // The retired `format` renders in the rubric's fourth position — the slot
    // `clarity` occupies post-rubric — between feasibility and granularity,
    // and the unknown keys would come after the known ones (F3).
    const labels = screen
      .getAllByRole('listitem')
      .map((li) => li.querySelector('span')?.textContent);
    expect(labels).toEqual([
      t.judgePanel.criterion_coherence,
      t.judgePanel.criterion_completeness,
      t.judgePanel.criterion_feasibility,
      t.judgePanel.criterion_format,
      t.judgePanel.criterion_granularity,
    ]);
  });

  it('renders nothing at all for a null record — the run did not judge', () => {
    const { container } = render(<JudgePanel result={null} locale="en" />);

    expect(container.firstElementChild).toBeNull();
  });
});
