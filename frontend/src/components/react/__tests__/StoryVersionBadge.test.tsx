import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { StoryVersionBadge, versionCountLabel } from '@/components/react/StoryVersionBadge';
import type { StoryVersionSummary } from '@/types/story';

/* ── Shared version badge (versioning-visibility, WU3b) ──
   One component, three surfaces: StoriesList story cards and the Dashboard's
   recent-stories rows. The behaviour is exactly what WU3 shipped inline. */

function makeSummary(overrides: Partial<StoryVersionSummary> = {}): StoryVersionSummary {
  return {
    count: 3,
    currentNumber: 2,
    latestNumber: 2,
    latestStatus: 'completed',
    ...overrides,
  };
}

describe('StoryVersionBadge', () => {
  it('marks the current version when a completed run exists', () => {
    render(<StoryVersionBadge summary={makeSummary()} locale="en" />);

    expect(screen.getByText('v2 · current')).toBeInTheDocument();
  });

  it('shows the newest version without the current marker when no run completed', () => {
    render(
      <StoryVersionBadge
        summary={makeSummary({ currentNumber: null, latestStatus: 'failed' })}
        locale="en"
      />,
    );

    // The badge names the newest run, but never claims it is current.
    expect(screen.getByText('v2')).toBeInTheDocument();
    expect(screen.queryByText('v2 · current')).not.toBeInTheDocument();
    expect(screen.queryByText('current')).not.toBeInTheDocument();
  });

  it('renders nothing for a story with no runs (summary null or absent)', () => {
    const { container: nullContainer } = render(<StoryVersionBadge summary={null} locale="en" />);

    // Neither a badge nor any count text: nothing is invented for a story
    // that never ran.
    expect(nullContainer).toBeEmptyDOMElement();
    expect(screen.queryByText(/^v\d/)).not.toBeInTheDocument();
    expect(screen.queryByText(/version/i)).not.toBeInTheDocument();
  });

  it('renders nothing when the summary is absent', () => {
    const { container } = render(<StoryVersionBadge locale="en" />);

    expect(container).toBeEmptyDOMElement();
  });

  it('uses the singular count label for exactly one version and plural otherwise', () => {
    expect(versionCountLabel(1, 'en')).toBe('1 version');
    expect(versionCountLabel(3, 'en')).toBe('3 versions');
    expect(versionCountLabel(1, 'es')).toBe('1 versión');
    expect(versionCountLabel(3, 'es')).toBe('3 versiones');
  });
});
