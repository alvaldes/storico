import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { VersionSelector } from '@/components/react/VersionSelector';
import { useTranslations } from '@/i18n/utils';
import type { StoryVersion } from '@/types/story';

const t = useTranslations('en');

function makeVersion(overrides: Partial<StoryVersion> = {}): StoryVersion {
  return {
    id: 'ext-1',
    versionNumber: 1,
    status: 'completed',
    modelUsed: 'llama3.2',
    provider: 'ollama',
    temperature: 0.1,
    createdAt: '2026-09-30T10:00:00Z',
    completedAt: '2026-09-30T10:01:00Z',
    errorInfo: null,
    isCurrent: false,
    hasOutput: true,
    ...overrides,
  };
}

/** v1 and v2 completed (v2 current), v3 failed on top — the honest-history shape. */
const versions: StoryVersion[] = [
  makeVersion({
    id: 'ext-3',
    versionNumber: 3,
    status: 'failed',
    hasOutput: false,
    errorInfo: 'Ollama unreachable',
    createdAt: '2026-10-02T10:00:00Z',
  }),
  makeVersion({ id: 'ext-2', versionNumber: 2, isCurrent: true, createdAt: '2026-10-01T10:00:00Z' }),
  makeVersion({ id: 'ext-1', versionNumber: 1, createdAt: '2026-09-30T10:00:00Z' }),
];

describe('VersionSelector', () => {
  it('lists every version with exactly the current one marked', () => {
    render(<VersionSelector versions={versions} selectedId="ext-2" onSelect={() => {}} />);

    const selector = screen.getByRole('combobox', { name: t.versionSelector.label });
    const options = [...selector.querySelectorAll('option')];
    expect(options).toHaveLength(3);
    const marked = options.filter((o) => o.textContent?.includes(t.versionSelector.current));
    expect(marked).toHaveLength(1);
    expect(marked[0]?.textContent).toContain('2');
  });

  it('offers a failed version with its model and date, and keeps its reason out of the option', () => {
    // The reason is deliberately NOT part of the option label. `error_info` is
    // arbitrary-length prose (a Postgres refusal can run to a full sentence), and a
    // native `<select>` sizes itself to its widest option: embedded there, it blew
    // the control past its container and clipped it mid-word. The full reason is
    // rendered below by the story page's no-output card, where it can wrap.
    render(<VersionSelector versions={versions} selectedId="ext-2" onSelect={() => {}} />);

    const selector = screen.getByRole('combobox', { name: t.versionSelector.label });
    const failed = [...selector.querySelectorAll('option')].find((o) => o.value === 'ext-3');
    expect(failed).toBeDefined();
    expect(failed?.textContent).toContain('v3');
    expect(failed?.textContent).toContain(t.versionSelector.failed);
    expect(failed?.textContent).toContain('llama3.2');
    expect(failed?.textContent).toContain(
      new Date('2026-10-02T10:00:00Z').toLocaleDateString('en-US'),
    );
    expect(failed?.textContent).not.toContain('Ollama unreachable');
    // "Offered" means selectable: the failed version must be reachable so its
    // no-output state can be shown instead of an empty board.
    expect(failed?.disabled).toBe(false);
  });

  it('keeps every option short enough to fit, however long the failure reason is', () => {
    // The regression this pins: a 200-char Postgres error used to become the option
    // label, so the control grew past the content column and clipped mid-sentence.
    const longReason =
      'Unexpected error after 3 attempts: (EMAXCONNSESSION) max clients reached in session ' +
      'mode - max clients are limited to pool_size: 15';
    const failedVersion = makeVersion({
      id: 'ext-9',
      versionNumber: 9,
      status: 'failed',
      hasOutput: false,
      errorInfo: longReason,
    });
    render(
      <VersionSelector versions={[failedVersion]} selectedId="ext-9" onSelect={() => {}} />,
    );

    const selector = screen.getByRole('combobox', { name: t.versionSelector.label });
    const option = selector.querySelector('option');
    expect(option?.textContent).not.toContain('EMAXCONNSESSION');
    expect(option?.textContent).not.toContain('pool_size');
    // The identity is what remains: version number, status, model, date.
    expect(option?.textContent?.length ?? 0).toBeLessThan(80);
  });

  it('reports the selected version to the caller', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<VersionSelector versions={versions} selectedId="ext-2" onSelect={onSelect} />);

    // The failed version is the selectable non-current entry: a frozen completed
    // version is listed but deliberately disabled until per-version task reads
    // land with the store work (W6-B).
    await user.selectOptions(
      screen.getByRole('combobox', { name: t.versionSelector.label }),
      'ext-3',
    );

    expect(onSelect).toHaveBeenCalledWith('ext-3');
  });

  it('offers a frozen completed version as selectable — the store version-aware read shows its own tasks', async () => {
    // W6-B1 lifts W6-A's restriction: once the store re-reads tasks with the
    // selected version's extraction_id, selecting a frozen completed version
    // displays that version's own tasks, so it is no longer a lie.
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<VersionSelector versions={versions} selectedId="ext-2" onSelect={onSelect} />);

    const selector = screen.getByRole('combobox', { name: t.versionSelector.label });
    const frozen = [...selector.querySelectorAll('option')].find((o) => o.value === 'ext-1');
    expect(frozen?.disabled).toBe(false);

    await user.selectOptions(selector, 'ext-1');
    expect(onSelect).toHaveBeenCalledWith('ext-1');
  });
});
