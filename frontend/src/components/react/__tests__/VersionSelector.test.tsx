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

  it('offers a failed version with its error info, model and date', () => {
    render(<VersionSelector versions={versions} selectedId="ext-2" onSelect={() => {}} />);

    const selector = screen.getByRole('combobox', { name: t.versionSelector.label });
    const failed = [...selector.querySelectorAll('option')].find((o) =>
      o.textContent?.includes('Ollama unreachable'),
    );
    expect(failed).toBeDefined();
    expect(failed?.textContent).toContain('llama3.2');
    expect(failed?.textContent).toContain(
      new Date('2026-10-02T10:00:00Z').toLocaleDateString('en-US'),
    );
    // "Offered" means selectable: the failed version must be reachable so its
    // no-output state can be shown instead of an empty board.
    expect(failed?.disabled).toBe(false);
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
});
