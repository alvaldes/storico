import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { JudgePanel } from '@/components/react/JudgePanel';
import { getTranslations } from '@/i18n/utils';
import type { JudgeResult } from '@/types/extraction';

/* ── Why this file exists ──────────────────────────────────────────────────
 *
 * The judge record (S8) reaches the UI in three shapes, and every one has an
 * observable obligation:
 *
 * - `state: "ok"` — the seven rubric criteria on the 1–7 scale with their
 *   justifications, plus TAS, IFI and the total, all displayed exactly as the
 *   record carries them (no recomputation, no rounding).
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

const okRecord: JudgeResult = {
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
};

const failedRecord: JudgeResult = {
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
};

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

    // Numbers displayed exactly as the record carries them: TAS is the stored
    // mean, IFI is the stored non-terminating mean, and the score 6.5 is NOT
    // rounded to an integer anywhere.
    expect(screen.getByText('TAS 4.5')).toBeInTheDocument();
    expect(screen.getByText('IFI 5.833333333333333')).toBeInTheDocument();
    expect(screen.getByText('39.5/49')).toBeInTheDocument();
    expect(screen.getByText('6.5')).toBeInTheDocument();
    expect(screen.getByText('Judged by qwen2.5:7b')).toBeInTheDocument();
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
  });

  it('renders nothing at all for a null record — the run did not judge', () => {
    const { container } = render(<JudgePanel result={null} locale="en" />);

    expect(container.firstElementChild).toBeNull();
  });
});
